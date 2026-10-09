import 'dart:async';

import 'package:background_fetch/background_fetch.dart';
import 'package:flutter/material.dart';

import 'app_config.dart';
import 'screens/main_page.dart';
import 'services/background_sync_manager.dart';
import 'services/health_background_delivery.dart';
import 'services/notification_service.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await NotificationService.initialize();
  // A tap that launched the app is picked up by MainPage, which resumes the
  // transfer and tells the user so.
  await NotificationService.handleLaunchNotificationTap();
  await BackgroundSyncManager.initialize();
  await HealthBackgroundDelivery.initialize();
  unawaited(BackgroundSyncManager.runQuietSync());
  BackgroundFetch.registerHeadlessTask(backgroundFetchHeadlessTask);
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
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
