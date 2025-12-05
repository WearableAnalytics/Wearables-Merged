import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'health_sync_service.dart';

/// Handles notification permissions and reporting sync status to the user.
class NotificationService {
  NotificationService._();

  static final FlutterLocalNotificationsPlugin _plugin = FlutterLocalNotificationsPlugin();
  static bool _initialized = false;
  static Completer<void>? _initializingCompleter;

  static Future<void> initialize({bool requestPermissions = true}) async {
    if (_initialized) return;
    if (_initializingCompleter != null) {
      // Another initialization is in progress, await it.
      await _initializingCompleter!.future;
      return;
    }
    _initializingCompleter = Completer<void>();
    try {
      const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
      const iosInit = DarwinInitializationSettings();
      const settings = InitializationSettings(android: androidInit, iOS: iosInit);

      await _plugin.initialize(settings);
      _initialized = true;

      if (requestPermissions) {
        await _requestPermissions();
      }
      _initializingCompleter!.complete();
    } catch (e, st) {
      _initializingCompleter!.completeError(e, st);
      rethrow;
    } finally {
      _initializingCompleter = null;
    }
  }

  static Future<void> ensureInitializedForBackground() async {
    if (!_initialized) {
      await initialize(requestPermissions: false);
    }
  }

  static Future<void> _requestPermissions() async {
    await _plugin.resolvePlatformSpecificImplementation<IOSFlutterLocalNotificationsPlugin>()?.requestPermissions(
          alert: true,
          badge: true,
          sound: true,
        );

    await _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()?.requestNotificationsPermission();
  }

  static Future<void> showSyncResultNotification(HealthSyncResult result) async {
    try {
      await ensureInitializedForBackground();

      await _plugin.show(
        DateTime.now().millisecondsSinceEpoch ~/ 1000,
        'Health Data Sync',
        _messageForResult(result),
        _notificationDetails,
      );
    } catch (e) {
      debugPrint('Failed to show notification: $e');
    }
  }

  static Future<void> showSyncStartedNotification({String message = 'Starting background fetch...'}) async {
    try {
      await ensureInitializedForBackground();
      await _plugin.show(
        DateTime.now().millisecondsSinceEpoch ~/ 1000,
        'Health Data Sync',
        message,
        _notificationDetails,
      );
    } catch (e) {
      debugPrint('Failed to show start notification: $e');
    }
  }

  static Future<void> showTestNotification({String message = 'Hello from background fetch!'}) async {
    try {
      await ensureInitializedForBackground();
      await _plugin.show(
        DateTime.now().millisecondsSinceEpoch ~/ 1000,
        'Background Fetch Test',
        message,
        _notificationDetails,
      );
    } catch (e) {
      debugPrint('Failed to show test notification: $e');
    }
  }

  static const NotificationDetails _notificationDetails = NotificationDetails(
    android: AndroidNotificationDetails(
      'health_sync_channel',
      'Health Sync',
      channelDescription: 'Notifications about background health data syncs',
      importance: Importance.high,
      priority: Priority.high,
    ),
    iOS: DarwinNotificationDetails(),
  );

  static String _messageForResult(HealthSyncResult result) {
    switch (result.status) {
      case HealthSyncStatus.success:
        return 'Uploaded ${result.totalSent} new data points.';
      case HealthSyncStatus.partialSuccess:
        return 'Uploaded ${result.totalSent}/${result.totalAvailable} data points. Last error: ${result.lastError ?? "Unknown"}';
      case HealthSyncStatus.nothingToSend:
        return 'No new health data found since your last sync.';
      case HealthSyncStatus.permissionDenied:
        return 'Cannot sync health data until permissions are granted.';
      case HealthSyncStatus.failed:
        return 'Health data sync failed: ${result.lastError ?? "Unknown error"}.';
    }
  }
}
