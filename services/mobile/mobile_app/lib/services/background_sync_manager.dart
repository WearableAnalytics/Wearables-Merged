import 'package:background_fetch/background_fetch.dart';
import 'package:flutter/foundation.dart';

import 'notification_service.dart';
import 'health_sync_service.dart';
import 'device_lock_service.dart';

/// Configures `background_fetch` and wires it to the sync + notification flow.
class BackgroundSyncManager {
  BackgroundSyncManager._();

  static bool _configured = false;
  static final HealthSyncService _healthSyncService = HealthSyncService();

  static Future<void> initialize() async {
    if (_configured) return;

    try {
      final status = await BackgroundFetch.configure(
        BackgroundFetchConfig(
          // Aim for a ~6h cadence; iOS still schedules opportunistically.
          minimumFetchInterval: 360,
          stopOnTerminate: false,
          enableHeadless: true,
          startOnBoot: true,
          requiresBatteryNotLow: false,
          requiresCharging: false,
          requiresStorageNotLow: false,
          requiresDeviceIdle: false,
          requiredNetworkType: NetworkType.ANY,
        ),
        _onTestBackgroundFetch,
        _onBackgroundTimeout,
      );
      debugPrint('BackgroundFetch configured. Status: $status');
      if (status == BackgroundFetch.STATUS_DENIED || status == BackgroundFetch.STATUS_RESTRICTED) {
        debugPrint('BackgroundFetch unavailable (denied or restricted by OS).');
      } else {
        await BackgroundFetch.start();
        debugPrint('BackgroundFetch started.');
      }
      _configured = true;
    } catch (e) {
      debugPrint('BackgroundFetch configuration failed: $e');
    }
  }

  static Future<void> _onTestBackgroundFetch(String taskId) async {
    debugPrint('[BackgroundFetch] Event received $taskId');
    await _runHealthSync(taskId);
  }

  static Future<void> _onBackgroundTimeout(String taskId) async {
    debugPrint('[BackgroundFetch] TASK TIMEOUT taskId: $taskId');
    BackgroundFetch.finish(taskId);
  }

  static Future<void> handleHeadlessTask(HeadlessTask task) async {
    if (task.timeout) {
      debugPrint('[BackgroundFetch] Headless task timed-out: ${task.taskId}');
      BackgroundFetch.finish(task.taskId);
      return;
    }
    await _runHealthSync(task.taskId);
  }

  static Future<void> _runHealthSync(String taskId) async {
    try {
      final protectedDataAvailable = await DeviceLockService.isProtectedDataAvailable();
      if (!protectedDataAvailable) {
        await NotificationService.showSyncResultNotification(_protectedDataLockedResult());
        return;
      }

      await NotificationService.showSyncStartedNotification(
        message: 'Starting data gathering for background sync...',
      );

      final result = await _healthSyncService.sendSinceLastSync(
        // In headless/background we must still ensure permissions are granted;
        // `requestPermissions` will no-op if already granted.
        requestPermissions: true,
      );

      await NotificationService.showSyncResultNotification(result);
    } catch (e) {
      debugPrint('[BackgroundFetch] Health sync failed: $e');
      await NotificationService.showSyncResultNotification(
        HealthSyncResult(
          status: HealthSyncStatus.failed,
          totalSent: 0,
          totalAvailable: 0,
          rangeStart: DateTime.now(),
          rangeEnd: DateTime.now(),
          lastError: 'Background sync failed: $e',
        ),
      );
    } finally {
      BackgroundFetch.finish(taskId);
    }
  }

  static HealthSyncResult _protectedDataLockedResult() {
    final now = DateTime.now();
    return HealthSyncResult(
      status: HealthSyncStatus.protectedDataUnavailable,
      totalSent: 0,
      totalAvailable: 0,
      rangeStart: now,
      rangeEnd: now,
      lastError: 'Protected data unavailable; unlock the device and open the app to sync.',
    );
  }
}
