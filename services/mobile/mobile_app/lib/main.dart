import 'dart:async';

import 'package:background_fetch/background_fetch.dart';
import 'package:flutter/material.dart';

import 'screens/main_page.dart';
import 'services/background_sync_manager.dart';
import 'services/health_sync_service.dart';
import 'services/notification_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  NotificationService.registerOnNotificationTap(
    BackgroundSyncManager.handleNotificationTap,
  );
  await NotificationService.initialize(
    onNotificationTap: BackgroundSyncManager.handleNotificationTap,
  );
  await NotificationService.handleLaunchNotificationTap();
  await BackgroundSyncManager.initialize();
  _kickOffInitialForegroundSync();
  BackgroundFetch.registerHeadlessTask(backgroundFetchHeadlessTask);
  runApp(const MyApp());
}

void _kickOffInitialForegroundSync() {
  unawaited(() async {
    try {
      final result = await HealthSyncService().sendSinceLastSync(
        requestPermissions: true,
      );
      debugPrint(
        'Initial foreground sync completed: ${result.status} (sent ${result.totalSent}/${result.totalAvailable}).',
      );
    } catch (e, st) {
      debugPrint('Initial foreground sync failed: $e');
      debugPrint('$st');
    }
  }());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Wearables Health Monitor',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue),
        useMaterial3: true,
        appBarTheme: const AppBarTheme(centerTitle: true, elevation: 2),
      ),
      // MainPage is defined in lib/screens/main_page.dart
      home: const MainPage(),
    );
  }
}

@pragma('vm:entry-point')
void backgroundFetchHeadlessTask(HeadlessTask task) async {
  WidgetsFlutterBinding.ensureInitialized();
  await NotificationService.initialize(requestPermissions: false);
  await BackgroundSyncManager.handleHeadlessTask(task);
}

Future<void> _runForegroundSyncFromNotification() async {
  // Kept for backwards compatibility; delegate to the centralized handler.
  await BackgroundSyncManager.handleNotificationTap();
}
