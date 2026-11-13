import 'dart:async';

import 'package:background_fetch/background_fetch.dart';
import 'package:flutter/material.dart';

import 'app_config.dart';
import 'screens/main_page.dart';
import 'services/background_sync_manager.dart';
import 'services/health_background_delivery.dart';
import 'services/notification_service.dart';
import 'state/app_state.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  BackgroundFetch.registerHeadlessTask(backgroundFetchHeadlessTask);
  // Render the UI immediately (against hangs)
  runApp(const MyApp());
  unawaited(_initializeServices());
}

Future<void> _initializeServices() async {
  try {
    await NotificationService.initialize();
    // A tap that launched the app is picked up by MainPage, which resumes the
    // transfer and tells the user so.
    await NotificationService.handleLaunchNotificationTap();
  } catch (e, st) {
    debugPrint('Notification startup failed: $e\n$st');
  }
  try {
    await BackgroundSyncManager.initialize();
    await HealthBackgroundDelivery.initialize();
    unawaited(BackgroundSyncManager.runQuietSync());
  } catch (e, st) {
    debugPrint('Background sync startup failed: $e\n$st');
  }
}

class MyApp extends StatefulWidget {
  const MyApp({super.key, this.state});

  final AppState? state;

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> with WidgetsBindingObserver {
  late final AppState _state = widget.state ?? AppState();

  @override
  void initState() {
    super.initState();
    // Registered before MaterialApp mounts (wearables://oauth-callback)
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    if (widget.state == null) _state.dispose();
    super.dispose();
  }

  @override
  Future<bool> didPushRouteInformation(RouteInformation routeInformation) async {
    final uri = routeInformation.uri;
    if (uri.scheme == 'wearables' ||
        uri.host == 'oauth-callback' ||
        uri.path.contains('oauth-callback') ||
        uri.path.isEmpty ||
        uri.path == '/') {
      _state.notifyOAuthCallback();
      return true;
    }
    return super.didPushRouteInformation(routeInformation);
  }

  @override
  Future<bool> didPushRoute(String route) async {
    if (route.contains('oauth-callback') || route == '/') {
      _state.notifyOAuthCallback();
      return true;
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      onGenerateInitialRoutes: (_) => [
        MaterialPageRoute<void>(builder: (_) => MainPage(state: _state)),
      ],
      onGenerateRoute: (_) => null,
    );
  }
}

/// iOS entry point for background launches (HealthKit wake-ups, background
/// fetch), started by AppDelegate when no scene and so no UI engine exists.
@pragma('vm:entry-point')
Future<void> backgroundMain() async {
  WidgetsFlutterBinding.ensureInitialized();
  await NotificationService.initialize(requestPermissions: false);
  await BackgroundSyncManager.initialize();
  await HealthBackgroundDelivery.initialize();
  unawaited(BackgroundSyncManager.runQuietSync());
}

@pragma('vm:entry-point')
void backgroundFetchHeadlessTask(task) async {
  WidgetsFlutterBinding.ensureInitialized();
  await NotificationService.initialize(requestPermissions: false);
  await BackgroundSyncManager.handleHeadlessTask(task);
}
