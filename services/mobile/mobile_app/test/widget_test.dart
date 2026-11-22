import 'dart:io';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:charite_wearables/storage_service.dart';
import 'package:charite_wearables/services/polar_band_sync.dart';
import 'package:charite_wearables/screens/upload_history_page.dart';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:charite_wearables/screens/main_page.dart';
import 'package:charite_wearables/services/health_sync_service.dart';
import 'package:charite_wearables/services/notification_service.dart';
import 'package:charite_wearables/services/sync_activity_notifier.dart';
import 'package:charite_wearables/state/app_state.dart';
import 'package:charite_wearables/theme/app_theme.dart';

const _studyCode = 'eyJhbGciOiJIUzI1NiJ9.eyJjYXNlSWQiOiJ4In0.c2lnbmF0dXJlLXNhbXBsZQ';
// {"caseId":"x","exp":1700000000}, expired in Nov 2023.
const _expiredCode =
    'eyJhbGciOiJIUzI1NiJ9.eyJjYXNlSWQiOiJ4IiwiZXhwIjoxNzAwMDAwMDAwfQ.c2lnbmF0dXJlLXNhbXBsZQ';

/// Loads real fonts so screenshots are readable (tests use a box font).
/// Set SCREENSHOT_FONT to a .ttf to render text; icons come from the SDK.
Future<void> _loadFonts() async {
  final flutterRoot = Platform.environment['FLUTTER_ROOT'];
  final font = Platform.environment['SCREENSHOT_FONT'];
  if (font != null && File(font).existsSync()) {
    final bytes = File(font).readAsBytesSync();
    for (final family in ['Roboto', 'FlutterTest']) {
      await (FontLoader(family)
            ..addFont(Future.value(ByteData.view(bytes.buffer))))
          .load();
    }
  }
  final symbols = File(
    '${Platform.environment['HOME']}/.pub-cache/hosted/pub.dev/material_symbols_icons-4.2960.0/lib/fonts/MaterialSymbolsSharp.ttf',
  );
  if (symbols.existsSync()) {
    final bytes = symbols.readAsBytesSync();
    await (FontLoader('packages/material_symbols_icons/MaterialSymbolsSharp')
          ..addFont(Future.value(ByteData.view(bytes.buffer))))
        .load();
  }
  if (flutterRoot != null) {
    final icons = File(
      '$flutterRoot/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf',
    );
    if (icons.existsSync()) {
      final bytes = icons.readAsBytesSync();
      await (FontLoader('MaterialIcons')
            ..addFont(Future.value(ByteData.view(bytes.buffer))))
          .load();
    }
  }
}

Future<AppState> _state(Map<String, Object> prefs) async {
  SharedPreferences.setMockInitialValues(prefs);
  final state = AppState();
  await state.load();
  return state;
}

Future<void> _pump(
  WidgetTester tester,
  AppState state, {
  bool settle = true,
}) async {
  tester.view.physicalSize = const Size(1179, 2556);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      home: MainPage(state: state),
    ),
  );
  Future<void> wait() => settle
      ? tester.pumpAndSettle()
      : tester.pump(const Duration(milliseconds: 600));
  await wait();
  // Let asset images decode before taking the screenshot.
  await tester.runAsync(() async {
    for (final element in find.byType(Image).evaluate()) {
      final image = element.widget as Image;
      await precacheImage(image.image, element);
    }
  });
  await wait();
}

/// Screenshots show live clock times, so they are only rendered on demand:
/// SCREENSHOT_FONT=... flutter test --update-goldens test/widget_test.dart
Future<void> _shot(String path) async {
  if (Platform.environment['SCREENSHOT_FONT'] == null) return;
  await expectLater(find.byType(MainPage), matchesGoldenFile(path));
}

void main() {
  setUpAll(() async {
    PackageInfo.setMockInitialValues(
      appName: 'Wearables',
      packageName: 'de.charite.wearables.app',
      version: '2.1.0',
      buildNumber: '5',
      buildSignature: '',
    );
    await _loadFonts();
  });

  testWidgets('first use shows the welcome flow', (tester) async {
    final state = await tester.runAsync(() => _state({}));
    await _pump(tester, state!);
    expect(find.text('Scan QR code'), findsOneWidget);
    expect(find.text('Enter code manually'), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
    await _shot('screenshots/01_welcome.png');
  });

  testWidgets('Home distinguishes Polar consent from paused phone sharing', (tester) async {
    final previous = SharedPreferencesAsyncPlatform.instance;
    SharedPreferencesAsyncPlatform.instance = InMemorySharedPreferencesAsync.empty();
    addTearDown(() => SharedPreferencesAsyncPlatform.instance = previous);
    final state = await tester.runAsync(() => _state({
      'device_id': _studyCode, 'local_health_sync_enabled': false,
    }));
    await SharedPreferencesAsync().setString(StorageService.polarBandConsentKey, jsonEncode({
      'owner': sha256.convert(utf8.encode(_studyCode)).toString(),
      'id': 'test-grant', 'endpoint': HealthSyncService().endpointFor(_studyCode).toString(), 'metrics': ['heartRate'],
    }));
    await _pump(tester, state!);
    expect(find.text('Polar auto-sync enabled'), findsOneWidget);
    expect(find.text('Health Connect sharing'), findsOneWidget);
    expect(find.text('Paused'), findsOneWidget);
    await SharedPreferencesAsync().setString('polar_status_test-grant',
        jsonEncode({'detail': 'Band setup changed', 'paused': true}));
    PolarBandSync.startForeground();
    addTearDown(PolarBandSync.stopForeground);
    await tester.pumpAndSettle();
    expect(find.text('Polar auto-sync paused'), findsOneWidget);
    await tester.tap(find.text('Polar device'));
    await tester.pumpAndSettle();
    expect(find.text('Band setup changed'), findsOneWidget);
    expect(find.text('Automatic Polar sharing is on'), findsNothing);
    await tester.tap(find.text('Turn off'));
    await tester.pumpAndSettle();
    expect(find.text('Manual live recording'), findsOneWidget);
    expect(find.text('Heart rate'), findsNothing);
    await tester.tap(find.text('Manual live recording'));
    await tester.pumpAndSettle();
    expect(find.text('Heart rate'), findsOneWidget);
    expect(find.text('Skin temperature'), findsOneWidget);
    expect(find.text('Pulse interval'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Polar auto-sync enabled'), findsNothing);
  });

  testWidgets('open history follows new local receipts and keeps checked progress on replay', (tester) async {
    SharedPreferences.setMockInitialValues({'device_id': _studyCode});
    await tester.pumpWidget(const MaterialApp(home: UploadHistoryPage(token: _studyCode)));
    await tester.pumpAndSettle();
    expect(find.textContaining('No uploads'), findsOneWidget);
    final receipt = {'acceptanceId':'fixture', 'readingCount': 5, 'storedConfirmedCount': 0};
    await StorageService.saveUploadReceipt(_studyCode, receipt);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pumpAndSettle();
    expect(find.textContaining('Storage confirmed: 0 of 5'), findsOneWidget);
    await StorageService.saveUploadReceipt(_studyCode, {...receipt,'checkedAt':'2026-11-22T20:00:00Z', 'storedConfirmedCount':5});
    await StorageService.saveUploadReceipt(_studyCode, receipt);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pumpAndSettle();
    expect(find.textContaining('Storage confirmed: 5 of 5'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('linked shows connected status and tabs', (tester) async {
    final last = DateTime.now().subtract(const Duration(hours: 2));
    final state = await tester.runAsync(() => _state({
          'device_id': _studyCode,
          'last_data_send_time': last.millisecondsSinceEpoch,
        }));
    await _pump(tester, state!);
    expect(find.text('Linked to your study'), findsOneWidget);
    expect(find.byType(NavigationBar), findsOneWidget);
    await _shot('screenshots/02_connected.png');

    await tester.tap(find.text('My data'));
    await tester.pumpAndSettle();
    await _shot('screenshots/03_my_data.png');

    await tester.tap(find.text('Account'));
    await tester.pumpAndSettle();
    expect(find.textContaining('••••••'), findsOneWidget);
    await tester.tap(find.text('More settings'));
    await tester.pumpAndSettle();
    expect(find.text('Share data from'), findsOneWidget);
    await _shot('screenshots/04_account.png');
  });

  testWidgets('status badge changes colour while sending and on error',
      (tester) async {
    final state = await tester.runAsync(() => _state({
          'device_id': _studyCode,
          'last_data_send_time': DateTime.now().millisecondsSinceEpoch,
        }));
    final scope = SyncActivityNotifier.startSync();
    SyncActivityNotifier.reportProgress(0.42);
    await _pump(tester, state!, settle: false);
    expect(find.text('Sharing your data…'), findsOneWidget);
    expect(find.text('42 %'), findsOneWidget);
    await _shot('screenshots/05_sending.png');

    SyncActivityNotifier.reportResult(SyncOutcome.failure);
    scope.close();
    await tester.pumpAndSettle();
    expect(find.text('Last upload failed'), findsOneWidget);
    await _shot('screenshots/06_error.png');
  });

  testWidgets('interrupted sync shows "not fully shared yet"', (tester) async {
    SyncActivityNotifier.lastResult.value = null;
    final upTo = DateTime(2026, 3, 28);
    final state = await tester.runAsync(() => _state({
          'device_id': _studyCode,
          'last_data_send_time': upTo.millisecondsSinceEpoch,
        }));
    await _pump(tester, state!);
    expect(find.text('Not fully shared yet'), findsOneWidget);
    expect(find.textContaining('28 Mar 2026'), findsWidgets);
    await _shot('screenshots/07_incomplete.png');
  });

  testWidgets('expired code asks to scan the QR code again', (tester) async {
    SyncActivityNotifier.lastResult.value = null;
    final state = await tester.runAsync(() => _state({
          'device_id': _expiredCode,
          'last_data_send_time': DateTime.now().millisecondsSinceEpoch,
        }));
    await _pump(tester, state!);
    expect(find.text('Personal code expired'), findsOneWidget);
    expect(find.text('Scan QR code'), findsOneWidget);
    expect(find.text('Share now'), findsNothing);
    expect(find.text('Paused'), findsOneWidget);
    await _shot('screenshots/09_code_expired.png');
  });

  testWidgets('opening a notification confirms the resumed transfer',
      (tester) async {
    SyncActivityNotifier.lastResult.value = null;
    final state = _FakeSyncState();
    await tester.runAsync(() async {
      SharedPreferences.setMockInitialValues({
        'device_id': _studyCode,
        'last_data_send_time': DateTime.now().millisecondsSinceEpoch,
      });
      await state.load();
    });
    await _pump(tester, state);
    await tester.tap(find.text('Account'));
    await tester.pumpAndSettle();

    NotificationService.debugSimulateOpen();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(
      find.text('Welcome back. Your data transfer has resumed.'),
      findsOneWidget,
    );
    expect(find.text('Linked to your study'), findsOneWidget);
    expect(state.syncCalls, 1);
    await _shot('screenshots/08_resumed.png');
  });
}

/// Records sync requests instead of touching HealthKit.
class _FakeSyncState extends AppState {
  int syncCalls = 0;

  @override
  Future<HealthSyncResult?> syncNow() async {
    syncCalls++;
    return null;
  }
}
