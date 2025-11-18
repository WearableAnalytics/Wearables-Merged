import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:health/health.dart';
import 'dart:convert';
import 'health_data_types.dart';
import 'package:background_fetch/background_fetch.dart';
import 'dart:io';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  BackgroundFetch.registerHeadlessTask(backgroundFetchHeadlessTask);
  runApp(const MyApp());
}

void backgroundFetchHeadlessTask(HeadlessTask task) async {
  final String taskId = task.taskId;
  final bool isTimeout = task.timeout;

  if (isTimeout) {
    BackgroundFetch.finish(taskId);
    return;
  }

  try {
    await uploadHealthDataInBackground();
  } catch (_) { }
  finally {
    BackgroundFetch.finish(taskId);
  }
}

Future<void> startBackgroundFetch() async {
  await BackgroundFetch.configure(
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
    (String taskId) async {
      try {
        await uploadHealthDataInBackground();
      } catch (_) { }
      finally {
        BackgroundFetch.finish(taskId);
      }
    },
    (String taskId) async {
      BackgroundFetch.finish(taskId);
    },
  );
}

Future<void> uploadHealthDataInBackground() async {
  final health = Health();

  try {
    await health.configure();
  } catch (e) {
    return;
  }

  final types = allRequestedHealthDataTypes;
  final now = DateTime.now();
  final from = now.subtract(Duration(minutes: 15));

  List<HealthDataPoint> healthData = [];
  try {
    healthData = await health.getHealthDataFromTypes(
      startTime: from,
      endTime: now,
      types: types,
    );
  } catch (e) {
    return;
  }

  Map<String, dynamic> payload = {
    'deviceInfo': {
      'platform': Platform.isIOS ? 'iOS' : 'Android',
      'deviceId': 'unknown_device',
      'authorizationToken': 'your_auth_token_here',
    },
    'batchInfo': {
      'batchId': DateTime.now().millisecondsSinceEpoch.toString(),
      'collectionStart': from.toIso8601String(),
      'collectionEnd': now.toIso8601String(),
      'dataPointCount': healthData.length,
    },
    'measurements': _formatHealthDataByType(healthData),
    'timestamp': now.toIso8601String(),
  };

  Map<String, dynamic> payloadTest = {'send_from': 'wearables'};

  try {
    final client = HttpClient();
    client.connectionTimeout = Duration(seconds: 20);
    final request = await client.postUrl(
      Uri.parse("https://dev.cherep.co/tubify/api/Route/walking"),
    );
    request.headers.set(HttpHeaders.contentTypeHeader, 'application/json');
    request.headers.set('X-App-Key', 'd85a90b6f2d15b7461c26d3d4843d6494c6995cbba937b2e283150cb67764541');
    request.add(utf8.encode(jsonEncode(payloadTest)));
    final response = await request.close().timeout(Duration(seconds: 20));
    await response.drain();
    client.close(force: true);
  } catch (_) { }
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Demo',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
      ),
      home: const MyHomePage(title: 'Flutter Demo Home Page'),
    );
  }
}

class MyHomePage extends StatefulWidget {
  const MyHomePage({super.key, required this.title});

  final String title;

  @override
  State<MyHomePage> createState() => _MyHomePageState();
}

class _MyHomePageState extends State<MyHomePage> {
  final health = Health();

  DateTime _startDate = DateTime.now().subtract(Duration(days: 1));
  DateTime _endDate = DateTime.now();

  Future<void> _getHealthData() async {
    try {
      await health.configure();

      var types = allRequestedHealthDataTypes;
      var permissions = permissionsFor(types);
      bool requested = await health.requestAuthorization(
        types,
        permissions: permissions,
      );

      if (!requested) {
        _showMessage('Authorization not granted');
        return;
      }

      var now = DateTime.now();

      List<HealthDataPoint> healthData = await health.getHealthDataFromTypes(
        startTime: _startDate,
        endTime: _endDate,
        types: types,
      );

      var midnight = DateTime(now.year, now.month, now.day);
      int? steps = await health.getTotalStepsInInterval(midnight, now);

      Map<String, dynamic> healthJson = {
        'deviceInfo': {
          'platform': Platform.isIOS ? 'iOS' : 'Android',
          'deviceId': 'unknown_device',
          'authorizationToken': 'your_auth_token_here',
        },
        'batchInfo': {
          'collectionStart': _startDate.toIso8601String(),
          'collectionEnd': _endDate.toIso8601String(),
        },
        'measurements': _formatHealthDataByType(healthData),
        'sourceName': healthData.first.sourceName,
        'sourcePlatform': healthData.first.sourcePlatform.toString(),
        'totalStepsToday': steps,
        'timestamp': DateTime.now().toIso8601String(),
      };

      _showMessage(jsonEncode(healthJson));
    } catch (e) {
      _showMessage('Error getting health data: $e');
    }
  }

  void _showMessage(String message) {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: Text('Health Data'),
          content: SingleChildScrollView(
            child: SelectableText(
              message,
              style: TextStyle(fontFamily: 'monospace'),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {            Clipboard.setData(ClipboardData(text: message));

                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('Health data copied to clipboard'),
                    duration: Duration(seconds: 2),
                  ),
                );
              },
              child: Text('Copy'),
            ),
            TextButton(
              onPressed: () {
                Navigator.of(context).pop();
              },
              child: Text('OK'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _selectStartDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _startDate,
      firstDate: DateTime.now().subtract(Duration(days: 365)),
      lastDate: DateTime.now(),
    );

    if (picked != null) {
      final TimeOfDay? timePicked = await showTimePicker(
        context: context,
        initialTime: TimeOfDay.fromDateTime(_startDate),
      );

      if (timePicked != null) {
        setState(() {
          _startDate = DateTime(
            picked.year,
            picked.month,
            picked.day,
            timePicked.hour,
            timePicked.minute,
          );

          if (_startDate.isAfter(_endDate)) {
            _endDate = _startDate.add(Duration(hours: 1));
          }
        });
      }
    }
  }

  Future<void> _selectEndDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _endDate,
      firstDate: _startDate,
      lastDate: DateTime.now(),
    );

    if (picked != null) {
      final TimeOfDay? timePicked = await showTimePicker(
        context: context,
        initialTime: TimeOfDay.fromDateTime(_endDate),
      );

      if (timePicked != null) {
        setState(() {
          _endDate = DateTime(
            picked.year,
            picked.month,
            picked.day,
            timePicked.hour,
            timePicked.minute,
          );

          if (_endDate.isBefore(_startDate)) {
            _startDate = _endDate.subtract(Duration(hours: 1));
          }
        });
      }
    }
  }

  void _setQuickPeriod(Duration duration) {
    setState(() {
      _endDate = DateTime.now();
      _startDate = _endDate.subtract(duration);
    });
  }

  String _formatDateTime(DateTime dateTime) {
    return '${dateTime.day}/${dateTime.month}/${dateTime.year} ${dateTime.hour.toString().padLeft(2, '0')}:${dateTime.minute.toString().padLeft(2, '0')}';
  }

  @override
  void initState() {
    super.initState();
    startBackgroundFetch();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        title: Text(widget.title),
      ),
      body: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            const Text(
              'Wearables Health Data App',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 30),

            const Text(
              'Quick Selection:',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 10,
              children: [
                ElevatedButton(
                  onPressed: () => _setQuickPeriod(Duration(hours: 1)),
                  child: const Text('Last Hour'),
                ),
                ElevatedButton(
                  onPressed: () => _setQuickPeriod(Duration(hours: 6)),
                  child: const Text('Last 6h'),
                ),
                ElevatedButton(
                  onPressed: () => _setQuickPeriod(Duration(days: 1)),
                  child: const Text('Last 24h'),
                ),
                ElevatedButton(
                  onPressed: () => _setQuickPeriod(Duration(days: 7)),
                  child: const Text('Last Week'),
                ),
              ],
            ),

            const SizedBox(height: 30),

            Card(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  children: [
                    const Text(
                      'Custom Period Selection:',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 15),

                    Row(
                      children: [
                        const Text(
                          'From: ',
                          style: TextStyle(fontWeight: FontWeight.w500),
                        ),
                        Expanded(child: Text(_formatDateTime(_startDate))),
                        ElevatedButton(
                          onPressed: _selectStartDate,
                          child: const Text('Change'),
                        ),
                      ],
                    ),

                    const SizedBox(height: 10),

                    Row(
                      children: [
                        const Text(
                          'To: ',
                          style: TextStyle(fontWeight: FontWeight.w500),
                        ),
                        Expanded(child: Text(_formatDateTime(_endDate))),
                        ElevatedButton(
                          onPressed: _selectEndDate,
                          child: const Text('Change'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),

            const SizedBox(height: 30),

            Text(
              'Period: ${_endDate.difference(_startDate).inHours}h ${_endDate.difference(_startDate).inMinutes % 60}m',
              style: const TextStyle(fontSize: 14, color: Colors.grey),
            ),

            const SizedBox(height: 20),

            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _getHealthData,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 15),
                ),
                child: const Text(
                  'Get Health Data',
                  style: TextStyle(fontSize: 18),
                ),
              ),
            ),
          ],
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
          'value': _parseValue(data.value),
          'unit': data.unit.toString().replaceAll('HealthDataUnit.', ''),
          'startTime': data.dateFrom.toIso8601String(),
          'endTime': data.dateTo.toIso8601String(),
          'durationMinutes': data.dateTo.difference(data.dateFrom).inMinutes,
        };
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
