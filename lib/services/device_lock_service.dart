import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Thin wrapper around a platform channel to detect if protected data
/// is currently accessible (iOS). On Android it always returns true.
class DeviceLockService {
  DeviceLockService._();

  static const _channel = MethodChannel(
    'com.cherep.device_state/protected_data',
  );

  static Future<bool> isProtectedDataAvailable() async {
    try {
      final available = await _channel.invokeMethod<bool>(
        'isProtectedDataAvailable',
      );
      final unlocked = available ?? true;
      debugPrint('Device lock status: ${unlocked ? "unlocked" : "locked"}');
      return unlocked;
    } catch (_) {
      debugPrint('Device lock status: locked (platform check failed)');
      // If the platform call fails, assume data is unavailable to be safe.
      return false;
    }
  }
}
