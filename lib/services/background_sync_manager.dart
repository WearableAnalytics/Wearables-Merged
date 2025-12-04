import 'package:background_fetch/background_fetch.dart';
import 'package:flutter/foundation.dart';

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
          requiresStorageNotLow: false,
          requiresDeviceIdle: false,
          requiredNetworkType: NetworkType.NONE,
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
    await NotificationService.showTestNotification(
      message: 'Hello world from background fetch!',
    );
    BackgroundFetch.finish(taskId);
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
    await _onTestBackgroundFetch(task.taskId);
  }
}
