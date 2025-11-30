import 'package:shared_preferences/shared_preferences.dart';
import 'dart:io';
import 'dart:math';

// Storage utility functions
class StorageService {
  static const String _deviceIdKey = 'device_id';
  static const String _lastDataSendKey = 'last_data_send_time';

  // Generate and store a unique device ID
  static Future<String> getOrCreateDeviceId() async {
    final prefs = await SharedPreferences.getInstance();
    String? deviceId = prefs.getString(_deviceIdKey);
    
    if (deviceId == null) {
      // Generate a unique device ID
      final random = Random.secure();
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final randomPart = random.nextInt(999999).toString().padLeft(6, '0');
      deviceId = '${Platform.isIOS ? 'iOS' : 'Android'}_${timestamp}_$randomPart';
      
      // Store it for future use
      await prefs.setString(_deviceIdKey, deviceId);
    }
    
    return deviceId;
  }

  // Get the last time data was sent
  static Future<DateTime?> getLastDataSendTime() async {
    final prefs = await SharedPreferences.getInstance();
    final timestamp = prefs.getInt(_lastDataSendKey);
    return timestamp != null ? DateTime.fromMillisecondsSinceEpoch(timestamp) : null;
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
}
