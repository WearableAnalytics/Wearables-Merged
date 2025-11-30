import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:health/health.dart';
import 'dart:convert';
import 'health_data_types.dart';
import 'dart:io';
import 'storage_service.dart';
import 'data_view_page.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // BackgroundFetch.registerHeadlessTask(backgroundFetchHeadlessTask);
  runApp(const MyApp());
}

// void backgroundFetchHeadlessTask(HeadlessTask task) async {
//   final String taskId = task.taskId;
//   final bool isTimeout = task.timeout;

//   if (isTimeout) {
//     BackgroundFetch.finish(taskId);
//     return;
//   }

//   try {
//     await uploadHealthDataInBackground();
//   } catch (_) { }
//   finally {
//     BackgroundFetch.finish(taskId);
//   }
// }

// Future<void> startBackgroundFetch() async {
//   await BackgroundFetch.configure(
//     BackgroundFetchConfig(
//       minimumFetchInterval: 15,
//       stopOnTerminate: false,
//       enableHeadless: true,
//       startOnBoot: true,
//       requiresBatteryNotLow: false,
//       requiresCharging: false,
//       requiresDeviceIdle: false,
//       requiredNetworkType: NetworkType.ANY,
//     ),
//     (String taskId) async {
//       try {
//         await uploadHealthDataInBackground();
//       } catch (_) { }
//       finally {
//         BackgroundFetch.finish(taskId);
//       }
//     },
//     (String taskId) async {
//       BackgroundFetch.finish(taskId);
//     },
//   );
// }

// Future<void> uploadHealthDataInBackground() async {
//   final health = Health();

//   try {
//     await health.configure();
//   } catch (e) {
//     return;
//   }

//   // Get device ID and last send time
//   final deviceId = await StorageService.getOrCreateDeviceId();
//   final lastSendTime = await StorageService.getLastDataSendTime();
  
//   final types = allRequestedHealthDataTypes;
//   final now = DateTime.now();
  
//   // Use last send time as starting point, or default to 15 minutes ago
//   final from = lastSendTime ?? now.subtract(Duration(minutes: 15));

//   List<HealthDataPoint> healthData = [];
//   try {
//     healthData = await health.getHealthDataFromTypes(
//       startTime: from,
//       endTime: now,
//       types: types,
//     );
//   } catch (e) {
//     return;
//   }

//   // Only send if we have new data
//   if (healthData.isEmpty) {
//     return;
//   }

//   Map<String, dynamic> payload = {
//     'deviceInfo': {
//       'platform': Platform.isIOS ? 'iOS' : 'Android',
//       'deviceId': deviceId,
//       'authorizationToken': 'your_auth_token_here',
//     },
//     'batchInfo': {
//       'batchId': DateTime.now().millisecondsSinceEpoch.toString(),
//       'collectionStart': from.toIso8601String(),
//       'collectionEnd': now.toIso8601String(),
//       'dataPointCount': healthData.length,
//       'lastSendTime': lastSendTime?.toIso8601String(),
//     },
//     'measurements': _formatHealthDataByType(healthData),
//     'timestamp': now.toIso8601String(),
//   };

//   try {
//     final client = HttpClient();
//     client.connectionTimeout = Duration(seconds: 20);
//     final request = await client.postUrl(
//       Uri.parse("https://dev.cherep.co/tubify/api/Route/walking"),
//     );
//     request.headers.set(HttpHeaders.contentTypeHeader, 'application/json');
//     request.headers.set('X-App-Key', 'd85a90b6f2d15b7461c26d3d4843d6494c6995cbba937b2e283150cb67764541');
//     request.add(utf8.encode(jsonEncode(payload)));
//     final response = await request.close().timeout(Duration(seconds: 20));
    
//     // Only update last send time if request was successful (status 200-299)
//     if (response.statusCode >= 200 && response.statusCode < 300) {
//       await StorageService.updateLastDataSendTime(now);
//     }
    
//     await response.drain();
//     client.close(force: true);
//   } catch (_) { 
//     // If sending fails, don't update the last send time so we can retry with the same data
//   }
// }

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Wearables Health Monitor',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue),
        useMaterial3: true,
        appBarTheme: const AppBarTheme(
          centerTitle: true,
          elevation: 2,
        ),
      ),
      home: const MainPage(),
    );
  }
}

class MainPage extends StatefulWidget {
  const MainPage({super.key});

  @override
  State<MainPage> createState() => _MainPageState();
}

class _MainPageState extends State<MainPage> {
  final health = Health();
  DateTime? _lastSendTime;
  final TextEditingController _deviceIdController = TextEditingController();

  Future<void> _loadDeviceInfo() async {
    final deviceId = await StorageService.getOrCreateDeviceId();
    final lastSendTime = await StorageService.getLastDataSendTime();
    
    setState(() {
      _lastSendTime = lastSendTime;
      _deviceIdController.text = deviceId;
    });
  }

  Future<void> _updateDeviceId() async {
    final newDeviceId = _deviceIdController.text.trim();
    if (newDeviceId.isNotEmpty) {
      await StorageService.setCustomDeviceId(newDeviceId);
      await _loadDeviceInfo();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Device ID updated successfully'),
          duration: Duration(seconds: 2),
        ),
      );
    }
  }

  Future<void> _sendRecentHealthData() async {
    try {
      await health.configure();

      var types = allRequestedHealthDataTypes;
      var permissions = permissionsFor(types);
      bool requested = await health.requestAuthorization(
        types,
        permissions: permissions,
      );

      if (!requested) {
        _showErrorMessage('Authorization not granted');
        return;
      }

      // Get device ID and last send time
      final deviceId = await StorageService.getOrCreateDeviceId();
      final lastSendTime = await StorageService.getLastDataSendTime();

      var now = DateTime.now();
      // Use last send time as starting point, or default to 7 days ago if never sent
      var from = lastSendTime ?? now.subtract(const Duration(days: 7));

      List<HealthDataPoint> healthData = await health.getHealthDataFromTypes(
        startTime: from,
        endTime: now,
        types: types,
      );

      if (healthData.isEmpty) {
        _showErrorMessage('No health data found in the selected time period');
        return;
      }

      // Show loading message
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Sending health data to server...'),
          duration: Duration(seconds: 3),
        ),
      );

      // Send data in chunks to avoid 413 "Request Entity Too Large" error
      const int chunkSize = 500; // Limit chunks to 500 data points each
      List<List<HealthDataPoint>> chunks = [];
      
      for (int i = 0; i < healthData.length; i += chunkSize) {
        int end = (i + chunkSize < healthData.length) ? i + chunkSize : healthData.length;
        chunks.add(healthData.sublist(i, end));
      }

      int totalSent = 0;
      String? lastError;

      for (int chunkIndex = 0; chunkIndex < chunks.length; chunkIndex++) {
        var chunk = chunks[chunkIndex];
        
        try {
          var midnight = DateTime(now.year, now.month, now.day);
          int? steps = await health.getTotalStepsInInterval(midnight, now);

          Map<String, dynamic> payload = {
            'deviceInfo': {
              'platform': Platform.isIOS ? 'iOS' : 'Android',
              'deviceId': deviceId,
              'authorizationToken': 'your_auth_token_here',
            },
            'batchInfo': {
              'batchId': '${DateTime.now().millisecondsSinceEpoch}_${chunkIndex + 1}',
              'chunkNumber': chunkIndex + 1,
              'totalChunks': chunks.length,
              'collectionStart': from.toIso8601String(),
              'collectionEnd': now.toIso8601String(),
              'lastSendTime': lastSendTime?.toIso8601String(),
              'dataPointCount': chunk.length,
            },
            'measurements': _formatHealthDataByType(chunk),
            'sourceName': chunk.isNotEmpty ? chunk.first.sourceName : 'N/A',
            'sourcePlatform': chunk.isNotEmpty ? chunk.first.sourcePlatform.toString() : 'N/A',
            'totalStepsToday': steps,
            'timestamp': DateTime.now().toIso8601String(),
          };

          final client = HttpClient();
          client.connectionTimeout = const Duration(seconds: 30);
          final request = await client.postUrl(
            Uri.parse("https://wearables.cherep.co/import/ingest"),
          );
          request.headers.set(HttpHeaders.contentTypeHeader, 'application/json');
          request.add(utf8.encode(jsonEncode(payload)));
          final response = await request.close().timeout(const Duration(seconds: 30));

          final responseBody = await response.transform(utf8.decoder).join();
          
          if (response.statusCode >= 200 && response.statusCode < 300) {
            totalSent += chunk.length;
          } else {
            lastError = 'Chunk ${chunkIndex + 1} failed\nStatus: ${response.statusCode}\nResponse: $responseBody';
          }
          
          client.close(force: true);
          
          // Small delay between chunks to be respectful to the server
          if (chunkIndex < chunks.length - 1) {
            await Future.delayed(const Duration(milliseconds: 500));
          }
          
        } catch (e) {
          lastError = 'Error sending chunk ${chunkIndex + 1}: $e';
        }
      }

      // Update last send time only if at least some data was sent successfully
      if (totalSent > 0) {
        await StorageService.updateLastDataSendTime(DateTime.now());
        await _loadDeviceInfo(); // Refresh the UI with new last send time
        
        if (lastError != null) {
          _showSuccessMessage('Partially successful!\n\n$totalSent out of ${healthData.length} data points uploaded\n\nLast error: $lastError');
        } else {
          _showSuccessMessage('Data sent successfully!\n\n$totalSent data points uploaded in ${chunks.length} chunks');
        }
      } else {
        _showErrorMessage('Failed to send any data\n\nLast error: ${lastError ?? "Unknown error"}');
      }
      
    } catch (e) {
      _showErrorMessage('Error sending data to server: $e');
    }
  }

  void _showSuccessMessage(String message) {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          icon: const Icon(Icons.check_circle, color: Colors.green, size: 48),
          title: const Text('Success'),
          content: Text(message),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('OK'),
            ),
          ],
        );
      },
    );
  }

  void _showErrorMessage(String message) {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          icon: const Icon(Icons.error, color: Colors.red, size: 48),
          title: const Text('Error'),
          content: SingleChildScrollView(
            child: SelectableText(message),
          ),
          actions: [
            TextButton.icon(
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: message));
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('Error details copied to clipboard'),
                      duration: Duration(seconds: 2),
                    ),
                  );
                }
              },
              icon: const Icon(Icons.copy, size: 16),
              label: const Text('Copy'),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('OK'),
            ),
          ],
        );
      },
    );
  }

  String _formatDateTime(DateTime dateTime) {
    return '${dateTime.day}/${dateTime.month}/${dateTime.year} ${dateTime.hour.toString().padLeft(2, '0')}:${dateTime.minute.toString().padLeft(2, '0')}';
  }

  @override
  void initState() {
    super.initState();
    // startBackgroundFetch();
    _loadDeviceInfo();
  }

  @override
  void dispose() {
    _deviceIdController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Health Monitor'),
        actions: [
          IconButton(
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (context) => const DataViewPage()),
              );
            },
            icon: const Icon(Icons.analytics),
            tooltip: 'View Health Data',
          ),
        ],
      ),
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Theme.of(context).colorScheme.primaryContainer.withOpacity(0.1),
              Theme.of(context).colorScheme.surface,
            ],
          ),
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Header
                Card(
                  elevation: 4,
                  child: Padding(
                    padding: const EdgeInsets.all(24.0),
                    child: Column(
                      children: [
                        Icon(
                          Icons.health_and_safety,
                          size: 48,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                        const SizedBox(height: 16),
                        Text(
                          'Wearables Health Monitor',
                          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Send your health data to the cloud',
                          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: Theme.of(context).colorScheme.onSurfaceVariant,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 24),

                // Device Info Card
                Card(
                  elevation: 2,
                  child: Padding(
                    padding: const EdgeInsets.all(20.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(
                              Icons.smartphone,
                              color: Theme.of(context).colorScheme.primary,
                            ),
                            const SizedBox(width: 8),
                            Text(
                              'Device Settings',
                              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        
                        // Device ID input field
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Device ID',
                              style: Theme.of(context).textTheme.labelMedium,
                            ),
                            const SizedBox(height: 8),
                            Row(
                              children: [
                                Expanded(
                                  child: TextField(
                                    controller: _deviceIdController,
                                    decoration: const InputDecoration(
                                      border: OutlineInputBorder(),
                                      isDense: true,
                                      hintText: 'Enter device ID',
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                ElevatedButton.icon(
                                  onPressed: _updateDeviceId,
                                  icon: const Icon(Icons.save, size: 18),
                                  label: const Text('Update'),
                                  style: ElevatedButton.styleFrom(
                                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                        
                        const SizedBox(height: 16),
                        Row(
                          children: [
                            Icon(
                              Icons.schedule,
                              size: 16,
                              color: Theme.of(context).colorScheme.onSurfaceVariant,
                            ),
                            const SizedBox(width: 8),
                            Text(
                              'Last sync: ${_lastSendTime != null ? _formatDateTime(_lastSendTime!) : "Never"}',
                              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                color: Theme.of(context).colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),

                const Spacer(),

                // Main Action Button
                Card(
                  elevation: 4,
                  child: Padding(
                    padding: const EdgeInsets.all(4.0),
                    child: ElevatedButton(
                      onPressed: _sendRecentHealthData,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Theme.of(context).colorScheme.primary,
                        foregroundColor: Theme.of(context).colorScheme.onPrimary,
                        padding: const EdgeInsets.symmetric(vertical: 20),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                        elevation: 0,
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(Icons.cloud_upload, size: 24),
                          const SizedBox(width: 12),
                          Text(
                            'Send Health Data',
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w600,
                              color: Theme.of(context).colorScheme.onPrimary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),

                const SizedBox(height: 16),

                Text(
                  'Uploads new health data since last sync (or last 7 days if first time)',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                  textAlign: TextAlign.center,
                ),

                const SizedBox(height: 24),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

Map<String, dynamic> _formatHealthDataByType(List<HealthDataPoint> healthData) {
  Map<String, List<Map<String, dynamic>>> categorizedData = {
    'instantaneous': [],
    'cumulative': [],
    'duration': [],
  };

  for (var data in healthData) {
    String category = _categorizeHealthDataType(data.type);
    Map<String, dynamic> formattedPoint = {};

    switch (category) {
      case 'instantaneous':
        formattedPoint = {
          'type': data.type.toString().replaceAll('HealthDataType.', ''),
          'value': _parseValue(data.value),
          'unit': data.unit.toString().replaceAll('HealthDataUnit.', ''),
          'timestamp': data.dateFrom.toIso8601String(),
        };
        break;

      case 'cumulative':
        formattedPoint = {
          'type': data.type.toString().replaceAll('HealthDataType.', ''),
          'value': _parseValue(data.value),
          'unit': data.unit.toString().replaceAll('HealthDataUnit.', ''),
          'periodStart': data.dateFrom.toIso8601String(),
          'periodEnd': data.dateTo.toIso8601String(),
          'duration': data.dateTo.difference(data.dateFrom).inSeconds,
        };
        break;

      case 'duration':
        formattedPoint = {
          'type': data.type.toString().replaceAll('HealthDataType.', ''),
          'value': _parseDurationValue(data),
          'unit': data.unit.toString().replaceAll('HealthDataUnit.', ''),
          'startTime': data.dateFrom.toIso8601String(),
          'endTime': data.dateTo.toIso8601String(),
          'durationMinutes': data.dateTo.difference(data.dateFrom).inMinutes,
        };
        
        // Add workout-specific details if this is workout data
        if (data.type == HealthDataType.WORKOUT) {
          var workoutDetails = _extractWorkoutDetails(data.value);
          if (workoutDetails != null) {
            formattedPoint.addAll(workoutDetails);
          }
        }
        break;
    }

    categorizedData[category]!.add(formattedPoint);
  }

  return categorizedData;
}

String _categorizeHealthDataType(HealthDataType type) {
  switch (type) {
    case HealthDataType.HEART_RATE:
    case HealthDataType.RESTING_HEART_RATE:
    case HealthDataType.WALKING_HEART_RATE:
    case HealthDataType.BLOOD_OXYGEN:
    case HealthDataType.BLOOD_PRESSURE_SYSTOLIC:
    case HealthDataType.BLOOD_PRESSURE_DIASTOLIC:
    case HealthDataType.BLOOD_GLUCOSE:
    case HealthDataType.BODY_TEMPERATURE:
    case HealthDataType.RESPIRATORY_RATE:
      return 'instantaneous';
    case HealthDataType.STEPS:
    case HealthDataType.DISTANCE_WALKING_RUNNING:
    case HealthDataType.FLIGHTS_CLIMBED:
    case HealthDataType.ACTIVE_ENERGY_BURNED:
    case HealthDataType.BASAL_ENERGY_BURNED:
      return 'cumulative';
    case HealthDataType.SLEEP_ASLEEP:
    case HealthDataType.SLEEP_AWAKE:
    case HealthDataType.SLEEP_DEEP:
    case HealthDataType.SLEEP_LIGHT:
    case HealthDataType.SLEEP_REM:
    case HealthDataType.WORKOUT:
    case HealthDataType.MINDFULNESS:
      return 'duration';

    default:
      return 'instantaneous';
  }
}

dynamic _parseValue(dynamic value) {
  try {
    if (value != null) {
      try {
        final numericValue = (value as dynamic).numericValue;
        if (numericValue != null) {
          return numericValue is double &&
                  numericValue == numericValue.roundToDouble()
              ? numericValue.round()
              : numericValue;
        }
      } catch (_) { }

      try {
        final val = (value as dynamic).value;
        if (val != null && val is num) {
          return val is double && val == val.roundToDouble()
              ? val.round()
              : val;
        }
      } catch (_) { }
    }
  } catch (_) { }
  if (value is String) {
    final doubleValue = double.tryParse(value);
    if (doubleValue != null) {
      return doubleValue == doubleValue.roundToDouble()
          ? doubleValue.round()
          : doubleValue;
    }
  }
  if (value is num) {
    return value is double && value == value.roundToDouble()
        ? value.round()
        : value;
  }
  if (value != null) {
    final valueStr = value.toString();
    final regex = RegExp(r'numeric_value[\":\s]*([0-9]+\.?[0-9]*)');
    final match = regex.firstMatch(valueStr);
    if (match != null) {
      final numericStr = match.group(1);
      if (numericStr != null) {
        try {
          final doubleValue = double.parse(numericStr);
          return doubleValue == doubleValue.roundToDouble()
              ? doubleValue.round()
              : doubleValue;
        } catch (e) {
          // Return original value if parsing fails
        }
      }
    }
  }

  return value;
}

dynamic _parseDurationValue(HealthDataPoint data) {
  // For all duration-based measurements (sleep, workout, mindfulness, etc.),
  // return the duration in minutes as the primary numeric value
  // This ensures the backend always receives a valid float
  return data.dateTo.difference(data.dateFrom).inMinutes.toDouble();
}

Map<String, dynamic>? _extractWorkoutDetails(dynamic value) {
  if (value == null) return null;
  
  try {
    final valueStr = value.toString();
    
    // Extract workout activity type
    final activityRegex = RegExp(r'workout_activity_type[\":\s]*([A-Z_]+)');
    final activityMatch = activityRegex.firstMatch(valueStr);
    
    // Extract total energy burned
    final energyRegex = RegExp(r'total_energy_burned[\":\s]*([0-9]+\.?[0-9]*)');
    final energyMatch = energyRegex.firstMatch(valueStr);
    
    // Extract total distance
    final distanceRegex = RegExp(r'total_distance[\":\s]*([0-9]+\.?[0-9]*)');
    final distanceMatch = distanceRegex.firstMatch(valueStr);
    
    // Extract energy unit
    final energyUnitRegex = RegExp(r'total_energy_burned_unit[\":\s]*([A-Z]+)');
    final energyUnitMatch = energyUnitRegex.firstMatch(valueStr);
    
    // Extract distance unit
    final distanceUnitRegex = RegExp(r'total_distance_unit[\":\s]*([A-Z]+)');
    final distanceUnitMatch = distanceUnitRegex.firstMatch(valueStr);
    
    Map<String, dynamic> details = {};
    
    if (activityMatch != null) {
      details['workoutActivityType'] = activityMatch.group(1);
    }
    
    if (energyMatch != null) {
      final energyValue = double.tryParse(energyMatch.group(1) ?? '');
      if (energyValue != null) {
        details['totalEnergyBurned'] = energyValue;
      }
    }
    
    if (distanceMatch != null) {
      final distanceValue = double.tryParse(distanceMatch.group(1) ?? '');
      if (distanceValue != null) {
        details['totalDistance'] = distanceValue;
      }
    }
    
    if (energyUnitMatch != null) {
      details['totalEnergyBurnedUnit'] = energyUnitMatch.group(1);
    }
    
    if (distanceUnitMatch != null) {
      details['totalDistanceUnit'] = distanceUnitMatch.group(1);
    }
    
    return details.isNotEmpty ? details : null;
  } catch (e) {
    return null;
  }
}
