import 'package:shared_preferences/shared_preferences.dart';
import 'dart:io';
import 'dart:math';

// Storage utility functions
class StorageService {
  static const String _deviceIdKey = 'device_id';
  static const String _lastDataSendKey = 'last_data_send_time';
  static const String _initialSyncStartKey = 'initial_sync_start';

  /// Default look-back for the first upload when no start date was chosen.
  static const Duration defaultInitialWindow = Duration(days: 30);

  // Generate and store a unique device ID
  static Future<String> getOrCreateDeviceId() async {
    final prefs = await SharedPreferences.getInstance();
    String? deviceId = prefs.getString(_deviceIdKey);

    if (deviceId == null) {
      // Generate a unique device ID
      final random = Random.secure();
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final randomPart = random.nextInt(999999).toString().padLeft(6, '0');
      deviceId =
          '${Platform.isIOS ? 'iOS' : 'Android'}_${timestamp}_$randomPart';

      // Store it for future use
      await prefs.setString(_deviceIdKey, deviceId);
    }

    return deviceId;
  }

  // Get the last time data was sent
  static Future<DateTime?> getLastDataSendTime() async {
    final prefs = await SharedPreferences.getInstance();
    final timestamp = prefs.getInt(_lastDataSendKey);
    return timestamp != null
        ? DateTime.fromMillisecondsSinceEpoch(timestamp)
        : null;
  }

  // Update the last data send time
  static Future<void> updateLastDataSendTime([DateTime? time]) async {
    final prefs = await SharedPreferences.getInstance();
    final timestamp = (time ?? DateTime.now()).millisecondsSinceEpoch;
    await prefs.setInt(_lastDataSendKey, timestamp);
  }

  // Set a custom device ID (for testing)
  static Future<void> setCustomDeviceId(String deviceId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_deviceIdKey, deviceId);
  }

  /// Removes the stored "last data send" timestamp so next sync acts fresh.
  static Future<void> clearLastDataSendTime() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_lastDataSendKey);
  }

  /// Case tokens from the study QR code are JWTs; auto-generated IDs are not.
  static bool isStudyCode(String? value) =>
      value != null && value.split('.').length == 3;

  static Future<bool> hasStudyCode() async {
    final prefs = await SharedPreferences.getInstance();
    return isStudyCode(prefs.getString(_deviceIdKey));
  }

  /// Start of the period shared on the first upload (or after a reset).
  static Future<DateTime> getInitialSyncStart() async {
    final prefs = await SharedPreferences.getInstance();
    final timestamp = prefs.getInt(_initialSyncStartKey);
    if (timestamp != null) {
      return DateTime.fromMillisecondsSinceEpoch(timestamp);
    }
    final now = DateTime.now();
    final start = now.subtract(defaultInitialWindow);
    return DateTime(start.year, start.month, start.day);
  }

  static Future<void> setInitialSyncStart(DateTime start) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_initialSyncStartKey, start.millisecondsSinceEpoch);
  }
}
