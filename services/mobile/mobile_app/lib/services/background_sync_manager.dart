import 'package:background_fetch/background_fetch.dart';
import 'package:flutter/foundation.dart';

import 'health_sync_service.dart';
import 'notification_service.dart';

/// Configures `background_fetch` and wires it to the sync + notification flow.
class BackgroundSyncManager {
  BackgroundSyncManager._();

  static bool _configured = false;

  static Future<void> initialize() async {
    if (_configured) return;

    try {
      final status = await BackgroundFetch.configure(
        BackgroundFetchConfig(
          minimumFetchInterval: 15,
          stopOnTerminate: false,
          enableHeadless: true,
          startOnBoot: true,
          requiresBatteryNotLow: false,
          requiresCharging: false,
          requiresDeviceIdle: false,
          requiredNetworkType: NetworkType.ANY,
        ),
        _onBackgroundFetch,
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

  static Future<void> _onBackgroundFetch(String taskId) async {
    await _performSync(taskId);
  }

  static Future<void> _onBackgroundTimeout(String taskId) async {
    debugPrint('BackgroundFetch timeout: $taskId');
    BackgroundFetch.finish(taskId);
  }

  static Future<void> handleHeadlessTask(HeadlessTask task) async {
    if (task.timeout) {
      BackgroundFetch.finish(task.taskId);
      return;
    }
    await _performSync(task.taskId);
  }

  static Future<void> _performSync(String taskId) async {
    try {
      debugPrint('Background fetch triggered: $taskId');
      await NotificationService.showSyncStartedNotification();
      final result = await HealthSyncService().sendSinceLastSync(requestPermissions: false);
      debugPrint('Background fetch completed: $taskId with status ${result.status}');
      await NotificationService.showSyncResultNotification(result);
    } catch (e) {
      debugPrint('Background sync failed: $e');
    } finally {
      BackgroundFetch.finish(taskId);
    }
  }
}
