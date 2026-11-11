import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:charite_wearables/screens/main_page.dart';
import 'package:charite_wearables/services/cloud_connector_service.dart';
import 'package:charite_wearables/state/app_state.dart';
import 'package:charite_wearables/storage_service.dart';
import 'package:charite_wearables/theme/app_theme.dart';

// JWT with payload: {"patientId":"patient-42","caseId":"case-42"}
const _studyCodeWithPatient =
    'eyJhbGciOiJIUzI1NiJ9.eyJwYXRpZW50SWQiOiJwYXRpZW50LTQyIiwiY2FzZUlkIjoiY2FzZS00MiJ9.c2ln';

class _RealHttp extends HttpOverrides {}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    PackageInfo.setMockInitialValues(
      appName: 'Wearables',
      packageName: 'de.charite.wearables.app',
      version: '2.1.0',
      buildNumber: '5',
      buildSignature: '',
    );
  });

  test('extracts patientId from study code JWT and builds Garmin OAuth URL', () {
    expect(
      StorageService.patientIdFromCode(_studyCodeWithPatient),
      'patient-42',
    );
    final service = CloudConnectorService(
      baseUri: Uri.parse('https://wearables.charite.de/cloud'),
    );
    final loginUri = service.buildOAuthLoginUri(_studyCodeWithPatient);
    expect(
      loginUri.toString(),
      'https://wearables.charite.de/cloud/auth/garmin/login?patient_id=patient-42',
    );
  });

  group('CloudConnectorService HTTP protocol', () {
    late HttpServer server;
    late CloudConnectorService service;
    late StreamSubscription<HttpRequest> subscription;

    setUp(() async {
      server = await HttpOverrides.runWithHttpOverrides(
        () => HttpServer.bind(InternetAddress.loopbackIPv4, 0),
        _RealHttp(),
      );
      service = CloudConnectorService(
        baseUri: Uri.parse('http://127.0.0.1:${server.port}/cloud'),
        clientFactory: () => HttpOverrides.runWithHttpOverrides(
          () => HttpClient(),
          _RealHttp(),
        ),
      );
    });

    tearDown(() async {
      await subscription.cancel();
      await server.close(force: true);
    });

    test('fetches Garmin connection status and disconnects on server', () async {
      var connectedOnServer = true;
      String? deletedPath;

      subscription = server.listen((request) async {
        expect(
          request.headers.value(HttpHeaders.authorizationHeader),
          'Bearer $_studyCodeWithPatient',
        );
        if (request.method == 'GET' &&
            request.uri.path == '/cloud/connections') {
          expect(request.uri.queryParameters['provider'], 'garmin');
          request.response.statusCode = 200;
          request.response.write(
            jsonEncode({
              'connections': connectedOnServer
                  ? [
                      {
                        'provider': 'garmin',
                        'patient_id': 'patient-42',
                        'provider_user_id': 'garmin-user-99',
                        'permissions': ['ACTIVITY_EXPORT', 'HEALTH_EXPORT'],
                        'linked_at': '2026-11-06T10:00:00Z',
                      },
                    ]
                  : [],
            }),
          );
          await request.response.close();
          return;
        }
        if (request.method == 'DELETE') {
          deletedPath = request.uri.path;
          connectedOnServer = false;
          request.response.statusCode = 200;
          request.response.write(
            jsonEncode({
              'status': 'disconnected',
              'provider': 'garmin',
              'patient_id': 'patient-42',
            }),
          );
          await request.response.close();
          return;
        }
        request.response.statusCode = 404;
        await request.response.close();
      });

      final status = await service.fetchConnectionStatus(_studyCodeWithPatient);
      expect(status.connected, isTrue);
      expect(status.providerUserId, 'garmin-user-99');
      expect(status.permissions, ['ACTIVITY_EXPORT', 'HEALTH_EXPORT']);

      await service.disconnect(_studyCodeWithPatient);
      expect(deletedPath, '/cloud/connections/garmin/patient-42');

      final after = await service.fetchConnectionStatus(_studyCodeWithPatient);
      expect(after.connected, isFalse);
    });
  });

  testWidgets(
    'supports connecting Garmin Cloud, switching between parallel and cloud-only, and disconnecting on server',
    (tester) async {
      tester.view.physicalSize = const Size(1179, 2556);
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.reset);

      Uri? launchedUri;
      final fakeCloud = _FakeCloudConnectorService();

      late AppState state;
      await tester.runAsync(() async {
        SharedPreferences.setMockInitialValues({
          'device_id': _studyCodeWithPatient,
          'last_data_send_time': DateTime.now().millisecondsSinceEpoch,
        });
        state = AppState(
          cloudService: fakeCloud,
          urlLauncher: (uri) async {
            launchedUri = uri;
            return true;
          },
        );
        await state.load();
      });

      await tester.pumpWidget(
        MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: buildAppTheme(),
          home: MainPage(state: state),
        ),
      );
      await tester.pumpAndSettle();

      // Navigate to Account tab
      await tester.tap(find.text('Account'));
      await tester.pumpAndSettle();

      expect(find.text('Garmin Connect (Cloud)'), findsOneWidget);
      expect(find.text('Connect Garmin Cloud'), findsOneWidget);

      // Scroll down to "Connect Garmin Cloud" and tap it -> launches OAuth URL
      await tester.ensureVisible(find.text('Connect Garmin Cloud'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Connect Garmin Cloud'));
      await tester.pumpAndSettle();
      expect(
        launchedUri.toString(),
        'https://wearables.charite.de/cloud/auth/garmin/login?patient_id=patient-42&return_url=wearables%3A%2F%2Foauth-callback',
      );

      // Simulate server has access
      fakeCloud.serverConnected = true;
      await tester.ensureVisible(
        find.byTooltip('Check Garmin connection status'),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Check Garmin connection status'));
      await tester.pumpAndSettle();

      // Dialog prompts
      expect(find.text('Garmin Cloud connected'), findsOneWidget);
      expect(find.text('Garmin Cloud only'), findsOneWidget);

      // Choose "Garmin Cloud only" first
      await tester.tap(find.text('Garmin Cloud only'));
      await tester.pumpAndSettle();

      expect(state.garminConnected, isTrue);
      expect(state.localHealthSyncEnabled, isFalse);
      expect(state.isCloudOnlyMode, isTrue);

      // Verify Home tab reflects cloud-only mode 
      await tester.tap(find.text('Home'));
      await tester.pumpAndSettle();
      expect(find.text('Check Garmin status'), findsOneWidget);
      expect(find.text('Garmin Cloud'), findsOneWidget);

      // Enable local health sync in parallel
      await tester.tap(find.text('Account'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byType(Switch));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Switch));
      await tester.pumpAndSettle();

      expect(state.localHealthSyncEnabled, isTrue);
      expect(state.isParallelSyncMode, isTrue);

      // Remove Garmin Cloud connection -> communicates with server
      await tester.ensureVisible(find.text('Remove Garmin Cloud connection'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Remove Garmin Cloud connection'));
      await tester.pumpAndSettle();
      expect(find.text('Remove Garmin Cloud connection?'), findsOneWidget);

      await tester.tap(find.text('Remove'));
      await tester.pumpAndSettle();

      expect(fakeCloud.disconnectCalls, 1);
      expect(state.garminConnected, isFalse);
      expect(find.text('Connect Garmin Cloud'), findsOneWidget);
    },
  );

  test('restoreCloudConnections queries server and restores active connections', () async {
    SharedPreferences.setMockInitialValues({'device_id': _studyCodeWithPatient});
    final fakeCloud = _FakeCloudConnectorService()..serverConnected = true;
    final state = AppState(cloudService: fakeCloud);
    await state.load();
    expect(state.isCloudConnected('garmin'), isFalse);

    final restored = await state.restoreCloudConnections();
    expect(restored.length, 1);
    expect(restored.first.id, 'garmin');
    expect(state.isCloudConnected('garmin'), isTrue);
    expect(state.cloudUserId('garmin'), 'garmin-user-99');
  });
}

class _FakeCloudConnectorService extends CloudConnectorService {
  bool serverConnected = false;
  int disconnectCalls = 0;

  @override
  Future<CloudConnectionStatus> fetchConnectionStatus(
    String deviceId, {
    String provider = 'garmin',
  }) async {
    return CloudConnectionStatus(
      connected: serverConnected,
      provider: provider,
      patientId: patientIdFor(deviceId),
      providerUserId: serverConnected ? 'garmin-user-99' : null,
      linkedAt: serverConnected ? DateTime.utc(2026, 11, 6, 10) : null,
    );
  }

  @override
  Future<void> disconnect(
    String deviceId, {
    String provider = 'garmin',
  }) async {
    disconnectCalls++;
    serverConnected = false;
  }
}
