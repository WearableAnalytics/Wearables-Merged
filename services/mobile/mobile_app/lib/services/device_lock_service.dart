import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Cross-platform wrapper for checking whether the device is currently locked.
/// On iOS this uses a native method channel; on other platforms it always
/// returns true (unlocked) because lock state is not relevant for our usage.
class DeviceLockService {
  DeviceLockService._();

  static const _channel = MethodChannel(
    'com.cherep.device_state/lock_state',
  );

  static Future<bool> isDeviceUnlocked() async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.iOS) {
      return true;
    }

    try {
      final locked = await _channel.invokeMethod<bool>('isDeviceLocked');
      final isLocked = locked ?? false;
      debugPrint('Device lock status: ${isLocked ? "locked" : "unlocked"}');
      return !isLocked;
    } catch (_) {
      debugPrint('Device lock status: locked (platform check failed)');
      // If the platform call fails, assume the device is locked to be safe.
      return false;
    }
  }
}
