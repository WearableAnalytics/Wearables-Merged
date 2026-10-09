import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import 'health_sync_service.dart';

/// Handles notification permissions and reporting sync status to the user.
class NotificationService {
  NotificationService._();

  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
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
    debugPrint(
      'NotificationService.initialize(requestPermissions: $requestPermissions)',
    );
    // Always keep the most recent tap handler, even if already initialized by a headless task.
    if (onNotificationTap != null) {
      _onNotificationTap = onNotificationTap;
    }
    if (_initialized) {
      debugPrint(
        'NotificationService.initialize: already initialized, handler updated.',
      );
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
      debugPrint(
        'NotificationService.handleLaunchNotificationTap: not initialized; skipping',
      );
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
    await _plugin
        .resolvePlatformSpecificImplementation<
          IOSFlutterLocalNotificationsPlugin
        >()
        ?.requestPermissions(alert: true, badge: true, sound: true);

    await _plugin
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >()
        ?.requestNotificationsPermission();
  }

  static const _title = 'Charité Wearables';
  static const _reminderId = 9001;
  static const reminderAfter = Duration(days: 3);

  /// Set when the user opens the app from one of our notifications. The UI
  /// consumes it to resume the data transfer and confirm that to the user.
  static final ValueNotifier<int> openedFromNotification = ValueNotifier(0);
  static bool _pendingOpen = false;

  @visibleForTesting
  static void debugSimulateOpen() {
    _pendingOpen = true;
    openedFromNotification.value++;
  }

  /// True once per notification tap, also for taps that cold-started the app.
  static bool consumePendingOpen() {
    final pending = _pendingOpen;
    _pendingOpen = false;
    return pending;
  }

  /// Schedules a friendly reminder for [reminderAfter] after the last upload,
  /// replacing any earlier one. Called after every sync and app start.
  static Future<void> scheduleInactivityReminder(DateTime? lastUpload) async {
    try {
      await ensureInitializedForBackground();
      await _plugin.cancel(_reminderId);
      _ensureTimeZones();
      final now = DateTime.now();
      var when = (lastUpload ?? now).add(reminderAfter);
      // Already overdue: remind once later today instead of right away.
      if (!when.isAfter(now)) when = now.add(const Duration(hours: 4));
      await _plugin.zonedSchedule(
        _reminderId,
        _title,
        'We have not received new health data for a few days. '
            'Open the app to continue sharing.',
        tz.TZDateTime.from(when, tz.UTC),
        _notificationDetails,
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      );
    } catch (e) {
      debugPrint('Failed to schedule reminder: $e');
    }
  }

  static Future<void> cancelInactivityReminder() async {
    try {
      await ensureInitializedForBackground();
      await _plugin.cancel(_reminderId);
    } catch (_) {}
  }

  /// Shown only when sharing needs the user, never for routine uploads.
  static Future<void> showActionNeeded(HealthSyncResult result) async {
    final message = switch (result.status) {
      HealthSyncStatus.permissionDenied =>
        'Access to Apple Health is needed to continue sharing. '
            'Open the app to review the permission.',
      _ => null,
    };
    if (message == null) return;
    try {
      await ensureInitializedForBackground();
      await _plugin.show(_actionId, _title, message, _notificationDetails);
    } catch (e) {
      debugPrint('Failed to show notification: $e');
    }
  }

  static const _actionId = 9002;
  static bool _tzReady = false;

  static void _ensureTimeZones() {
    if (_tzReady) return;
    tzdata.initializeTimeZones();
    _tzReady = true;
  }

  static const NotificationDetails _notificationDetails = NotificationDetails(
    android: AndroidNotificationDetails(
      'health_sync_channel',
      'Data sharing',
      channelDescription: 'Reminders about sharing your health data',
      importance: Importance.defaultImportance,
      priority: Priority.defaultPriority,
    ),
    iOS: DarwinNotificationDetails(threadIdentifier: 'data-sharing'),
  );

  static void _handleNotificationResponse(NotificationResponse response) {
    debugPrint(
      'NotificationService._handleNotificationResponse: '
      'id=${response.id}, actionId=${response.actionId}, type=${response.notificationResponseType}, '
      'payload=${response.payload}',
    );
    // Only trigger on user taps (ignore dismisses or other response types).
    if (response.notificationResponseType ==
        NotificationResponseType.selectedNotification) {
      _pendingOpen = true;
      openedFromNotification.value++;
      final handler = _onNotificationTap;
      if (handler != null) {
        debugPrint(
          'NotificationService._handleNotificationResponse: invoking tap handler',
        );
        unawaited(handler());
      } else {
        debugPrint(
          'NotificationService._handleNotificationResponse: no tap handler registered',
        );
      }
    }
  }
}
