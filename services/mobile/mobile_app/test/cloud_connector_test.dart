import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:charite_wearables/main.dart' as app_main;
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

    test('initiates OAuth login via authenticated POST and rejects 401', () async {
      subscription = server.listen((request) async {
        if (request.method == 'POST' &&
            request.uri.path == '/cloud/auth/garmin/login') {
          final auth = request.headers.value(HttpHeaders.authorizationHeader);
          if (auth != 'Bearer $_studyCodeWithPatient') {
            request.response.statusCode = 401;
            await request.response.close();
            return;
          }
          request.response.statusCode = 200;
          request.response.write(
            jsonEncode({
              'provider': 'garmin',
              'patient_id': 'patient-42',
              'state': 'pkce-state-1',
              'authorization_url':
                  'https://connect.garmin.com/oauth2Confirm?state=pkce-state-1',
            }),
          );
          await request.response.close();
          return;
        }
        request.response.statusCode = 404;
        await request.response.close();
      });

      final authUri = await service.initiateOAuthLogin(
        _studyCodeWithPatient,
        provider: 'garmin',
      );
      expect(
        authUri.toString(),
        'https://connect.garmin.com/oauth2Confirm?state=pkce-state-1',
      );

      await expectLater(
        () => service.initiateOAuthLogin('bad.jwt.token', provider: 'garmin'),
        throwsA(
          isA<CloudConnectorException>().having((e) => e.statusCode, 'statusCode', 401),
        ),
      );
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

      // Unconnected providers are collapsed inside the dropdown initially
      expect(find.text('Connect cloud provider'), findsOneWidget);
      expect(find.text('Connect Garmin Cloud'), findsNothing);
      expect(find.text('Garmin Connect (Cloud)'), findsNothing);
      expect(find.text('Remove all cloud connections'), findsNothing);

      // Expand the cloud provider dropdown
      await tester.ensureVisible(find.text('Connect cloud provider'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Connect cloud provider'));
      await tester.pumpAndSettle();
      expect(find.text('Connect Garmin Cloud'), findsOneWidget);

      // Tap "Connect Garmin Cloud" -> launches OAuth URL
      await tester.ensureVisible(find.text('Connect Garmin Cloud'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Connect Garmin Cloud'));
      await tester.pumpAndSettle();
      expect(
        launchedUri.toString(),
        'https://wearables.charite.de/cloud/auth/garmin/login?patient_id=patient-42&return_url=wearables%3A%2F%2Foauth-callback',
      );

      // Refresh icon should be hidden while not connected
      expect(find.byTooltip('Check Garmin connection status'), findsNothing);

      // Simulate server has access and app resumes from OAuth browser
      fakeCloud.connectedProviders.add('garmin');
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      // Dialog prompts
      expect(find.text('Garmin Cloud connected'), findsOneWidget);
      expect(find.text('Garmin Cloud only'), findsOneWidget);

      // Choose "Garmin Cloud only" first
      await tester.tap(find.text('Garmin Cloud only'));
      await tester.pumpAndSettle();

      expect(state.garminConnected, isTrue);
      expect(find.byTooltip('Check Garmin connection status'), findsOneWidget);
      expect(state.localHealthSyncEnabled, isFalse);
      expect(state.isCloudOnlyMode, isTrue);
      // Only 1 active connection -> global disconnect all should stay hidden
      expect(find.text('Remove all cloud connections'), findsNothing);
      expect(find.text('Connect another cloud provider'), findsOneWidget);

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
      expect(find.text('Connect cloud provider'), findsOneWidget);
      expect(find.text('Garmin Connect (Cloud)'), findsNothing);
    },
  );

  test('restoreCloudConnections reconciles active and inactive connections', () async {
    SharedPreferences.setMockInitialValues({
      'device_id': _studyCodeWithPatient,
      'polar_cloud_connected': true,
      'polar_cloud_user_id': 'stale-polar-user',
    });
    final fakeCloud = _FakeCloudConnectorService()
      ..connectedProviders.add('garmin');
    final state = AppState(cloudService: fakeCloud);
    await state.load();
    expect(state.isCloudConnected('garmin'), isFalse);
    expect(state.isCloudConnected('polar'), isTrue);

    final restored = await state.restoreCloudConnections();
    expect(restored.length, 1);
    expect(restored.first.id, 'garmin');
    expect(state.isCloudConnected('garmin'), isTrue);
    expect(state.cloudUserId('garmin'), 'garmin-user-99');
    // Stale polar flag should be cleared when server returns disconnected
    expect(state.isCloudConnected('polar'), isFalse);
    expect(await StorageService.isCloudConnected('polar'), isFalse);
  });

  test('linking a different patient clears cached cloud connections', () async {
    const otherPatientCode =
        'eyJhbGciOiJIUzI1NiJ9.eyJwYXRpZW50SWQiOiJwYXRpZW50LTk5IiwiY2FzZUlkIjoiY2FzZS05OSJ9.c2ln';
    SharedPreferences.setMockInitialValues({
      'device_id': _studyCodeWithPatient,
      'garmin_cloud_connected': true,
      'garmin_cloud_user_id': 'garmin-user-99',
    });
    final fakeCloud = _FakeCloudConnectorService();
    final state = AppState(cloudService: fakeCloud);
    await state.load();
    expect(state.garminConnected, isTrue);

    await state.linkStudyCode(otherPatientCode, resetLastSync: false);
    expect(state.garminConnected, isFalse);
    expect(await StorageService.isCloudConnected('garmin'), isFalse);
  });

  test('handles JWT 401 on connect and disconnect without locking local state', () async {
    SharedPreferences.setMockInitialValues({
      'device_id': _studyCodeWithPatient,
      'garmin_cloud_connected': true,
      'garmin_cloud_user_id': 'garmin-user-99',
    });
    final fakeCloud = _FakeCloudConnectorService()
      ..connectedProviders.add('garmin')
      ..rejectAuth = true;
    final state = AppState(cloudService: fakeCloud, urlLauncher: (_) async => true);
    await state.load();

    // Connecting with a reset JWT fails fast and marks code rejected
    await expectLater(
      () => state.startCloudConnect('polar'),
      throwsA(isA<CloudConnectorException>()),
    );
    expect(state.codeRejected, isTrue);
    expect(state.isCodeUnusable, isTrue);

    // Disconnecting with rejected/expired JWT does not hide server state
    final result = await state.disconnectCloud('garmin');
    expect(result.removedLocally, isFalse);
    expect(result.serverDisconnected, isFalse);
    expect(result.authRejected, isTrue);
    expect(state.garminConnected, isTrue);

    // Explicit local only removal clears device state when requested
    final forced = await state.disconnectCloud('garmin', localOnly: true);
    expect(forced.removedLocally, isTrue);
    expect(forced.serverDisconnected, isFalse);
    expect(state.garminConnected, isFalse);
    expect(await StorageService.isCloudConnected('garmin'), isFalse);
  });

  testWidgets(
    'shows global Remove all cloud connections when multiple providers are active',
    (tester) async {
      tester.view.physicalSize = const Size(1179, 2556);
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.reset);

      SharedPreferences.setMockInitialValues({
        'device_id': _studyCodeWithPatient,
        'garmin_cloud_connected': true,
        'garmin_cloud_user_id': 'garmin-user-99',
        'polar_cloud_connected': true,
        'polar_cloud_user_id': 'polar-user-77',
      });
      final fakeCloud = _FakeCloudConnectorService()
        ..connectedProviders.addAll(['garmin', 'polar']);
      final state = AppState(cloudService: fakeCloud);
      await state.load();

      await tester.pumpWidget(
        MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: buildAppTheme(),
          home: MainPage(state: state),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Account'));
      await tester.pumpAndSettle();

      // Both active providers shown outside the dropdown
      expect(find.text('Garmin Connect (Cloud)'), findsOneWidget);
      expect(find.text('Polar Flow (Cloud)'), findsOneWidget);
      // Global disconnect all is visible when >= 2 connections exist
      expect(find.text('Remove all cloud connections'), findsOneWidget);

      await tester.ensureVisible(find.text('Remove all cloud connections'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Remove all cloud connections'));
      await tester.pumpAndSettle();

      expect(find.text('Remove all cloud connections?'), findsOneWidget);
      await tester.tap(find.text('Remove all'));
      await tester.pumpAndSettle();

      expect(fakeCloud.disconnectCalls, 2);
      expect(state.hasAnyCloudConnection, isFalse);
      expect(find.text('Remove all cloud connections'), findsNothing);
      expect(find.text('Connect cloud provider'), findsOneWidget);
    },
  );

  testWidgets(
    'OAuth deep link wearables://oauth-callback does not push duplicate MainPage and updates UI immediately',
    (tester) async {
      SharedPreferences.setMockInitialValues({
        'device_id': _studyCodeWithPatient,
      });
      final fakeCloud = _FakeCloudConnectorService();
      final state = AppState(
        cloudService: fakeCloud,
        urlLauncher: (_) async => true,
      );
      await state.load();

      await tester.pumpWidget(app_main.MyApp(state: state));
      await tester.pumpAndSettle();

      // Navigate to Account tab and expand cloud providers dropdown
      await tester.tap(find.text('Account'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Connect cloud provider'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Connect cloud provider'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Connect Garmin Cloud'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Connect Garmin Cloud'));
      await tester.pumpAndSettle();

      // Simulate backend returning wearables://oauth-callback deep link
      fakeCloud.connectedProviders.add('garmin');
      await tester.binding.defaultBinaryMessenger.handlePlatformMessage(
        'flutter/navigation',
        const JSONMethodCodec().encodeMethodCall(
          const MethodCall('pushRouteInformation', {
            'location': 'wearables://oauth-callback?provider=garmin',
          }),
        ),
        (_) {},
      );
      await tester.pump(const Duration(milliseconds: 450));
      await tester.pumpAndSettle();

      // Still on a single MainPage
      expect(find.byType(MainPage), findsOneWidget);
      expect(find.byType(BackButton), findsNothing);
      expect(find.text('Garmin Cloud connected'), findsOneWidget);

      // Select Garmin Cloud only
      await tester.tap(find.text('Garmin Cloud only'));
      await tester.pumpAndSettle();

      // Account Data Sources updates immediately without restart
      expect(find.text('Garmin Connect (Cloud)'), findsOneWidget);
      expect(find.text('Remove Garmin Cloud connection'), findsOneWidget);
      // Garmin moved out of the dropdown -> remaining providers stay in the dropdown
      expect(find.text('Connect another cloud provider'), findsOneWidget);

      // Home tab updates immediately without restart
      await tester.tap(find.text('Home'));
      await tester.pumpAndSettle();
      expect(find.text('Check Garmin status'), findsOneWidget);
      expect(find.text('Garmin Cloud'), findsOneWidget);
    },
  );
}

class _FakeCloudConnectorService extends CloudConnectorService {
  final Set<String> connectedProviders = {};
  bool rejectAuth = false;
  int disconnectCalls = 0;

  @override
  Future<Uri> initiateOAuthLogin(
    String deviceId, {
    String provider = 'garmin',
    String? returnUrl = 'wearables://oauth-callback',
  }) async {
    if (rejectAuth) {
      throw const CloudConnectorException(
        'Invalid or expired token',
        statusCode: 401,
      );
    }
    return buildOAuthLoginUri(
      deviceId,
      provider: provider,
      returnUrl: returnUrl,
    );
  }

  @override
  Future<CloudConnectionStatus> fetchConnectionStatus(
    String deviceId, {
    String provider = 'garmin',
  }) async {
    if (rejectAuth) {
      throw const CloudConnectorException(
        'Invalid or expired token',
        statusCode: 401,
      );
    }
    final isConnected = connectedProviders.contains(provider);
    return CloudConnectionStatus(
      connected: isConnected,
      provider: provider,
      patientId: patientIdFor(deviceId),
      providerUserId: isConnected ? '$provider-user-99' : null,
      linkedAt: isConnected ? DateTime.utc(2026, 11, 6, 10) : null,
    );
  }

  @override
  Future<void> disconnect(
    String deviceId, {
    String provider = 'garmin',
  }) async {
    if (rejectAuth) {
      throw const CloudConnectorException(
        'Invalid or expired token',
        statusCode: 401,
      );
    }
    disconnectCalls++;
    connectedProviders.remove(provider);
  }
}
