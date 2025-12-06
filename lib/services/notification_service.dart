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
  static Future<void> Function()? _onNotificationTap;

  /// Allow late-binding the tap handler so background-only inits can still respond to taps.
  static void registerOnNotificationTap(Future<void> Function() handler) {
    _onNotificationTap = handler;
  }

  static Future<void> initialize({
    bool requestPermissions = true,
    Future<void> Function()? onNotificationTap,
  }) async {
    debugPrint('NotificationService.initialize(requestPermissions: $requestPermissions)');
    // Always keep the most recent tap handler, even if already initialized by a headless task.
    if (onNotificationTap != null) {
      _onNotificationTap = onNotificationTap;
    }
    if (_initialized) {
      debugPrint('NotificationService.initialize: already initialized, handler updated.');
      return;
    }
    if (_initializingCompleter != null) {
      // Another initialization is in progress, await it.
      await _initializingCompleter!.future;
      return;
    }
    _initializingCompleter = Completer<void>();
    try {
      const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
      const iosInit = DarwinInitializationSettings();
      final settings = InitializationSettings(
        android: androidInit,
        iOS: iosInit,
      );

      debugPrint('NotificationService.initialize: calling _plugin.initialize');
      await _plugin.initialize(
        settings,
        onDidReceiveNotificationResponse: _handleNotificationResponse,
      );
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
    debugPrint('NotificationService.ensureInitializedForBackground');
    if (!_initialized) {
      await initialize(requestPermissions: false);
    }
  }

  /// Checks if the app was launched from a notification tap and triggers the handler if so.
  static Future<void> handleLaunchNotificationTap() async {
    if (!_initialized) {
      debugPrint('NotificationService.handleLaunchNotificationTap: not initialized; skipping');
      return;
    }
    final details = await _plugin.getNotificationAppLaunchDetails();
    debugPrint(
      'NotificationService.handleLaunchNotificationTap: didLaunch=${details?.didNotificationLaunchApp}, '
      'responseType=${details?.notificationResponse?.notificationResponseType}',
    );
    final response = details?.notificationResponse;
    if (details?.didNotificationLaunchApp == true && response != null) {
      _handleNotificationResponse(response);
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
      debugPrint('NotificationService.showSyncResultNotification: ${result.status}');

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

  /// Returns true if the notification was shown (or we assume it was); false on error.
  static Future<bool> showSyncStartedNotification({String message = 'Starting background fetch...'}) async {
    try {
      await ensureInitializedForBackground();
      debugPrint('NotificationService.showSyncStartedNotification: $message');
      await _plugin.show(
        DateTime.now().millisecondsSinceEpoch ~/ 1000,
        'Health Data Sync',
        message,
        _notificationDetails,
      );
      return true;
    } catch (e) {
      debugPrint('Failed to show start notification: $e');
      return false;
    }
  }

  static Future<void> showTestNotification({String message = 'Hello from background fetch!'}) async {
    try {
      await ensureInitializedForBackground();
      debugPrint('NotificationService.showTestNotification: $message');
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
      case HealthSyncStatus.protectedDataUnavailable:
        return 'Phone locked. Unlock and open the app to finish syncing.';
      case HealthSyncStatus.failed:
        return 'Health data sync failed: ${result.lastError ?? "Unknown error"}.';
    }
  }

  static void _handleNotificationResponse(NotificationResponse response) {
    debugPrint(
      'NotificationService._handleNotificationResponse: '
      'id=${response.id}, actionId=${response.actionId}, type=${response.notificationResponseType}, '
      'payload=${response.payload}',
    );
    // Only trigger on user taps (ignore dismisses or other response types).
    if (response.notificationResponseType == NotificationResponseType.selectedNotification) {
      final handler = _onNotificationTap;
      if (handler != null) {
        debugPrint('NotificationService._handleNotificationResponse: invoking tap handler');
        unawaited(handler());
      } else {
        debugPrint('NotificationService._handleNotificationResponse: no tap handler registered');
      }
    }
  }
}
