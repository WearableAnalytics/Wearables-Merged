import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'background_sync_manager.dart';

/// Dart side of ios/Runner/HealthBackgroundDelivery.swift: iOS wakes the app
/// when HealthKit stores new data, and we upload it right away.
class HealthBackgroundDelivery {
  HealthBackgroundDelivery._();

  static const _channel = MethodChannel(
    'de.charite.wearables/health_background',
  );

  static Future<void> initialize() async {
    if (!Platform.isIOS) return;
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'newData') {
        await BackgroundSyncManager.runQuietSync();
      }
      return null;
    });
    try {
      // Tells the native side it can forward wake-ups that arrived early.
      await _channel.invokeMethod('ready');
    } catch (e) {
      debugPrint('HealthBackgroundDelivery unavailable: $e');
    }
  }
}
