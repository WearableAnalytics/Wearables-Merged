import 'package:flutter/material.dart';
import 'package:health/health.dart';
import 'dart:convert';
import 'health_data_types.dart';
import 'package:background_fetch/background_fetch.dart';
import 'dart:io';

/// URL to upload health JSON to. Replace with your server endpoint.
const String kHealthUploadUrl = 'https://example.com/health/upload';

void main() {
  // Make sure plugin services are initialized before using BackgroundFetch.
  WidgetsFlutterBinding.ensureInitialized();

  // Register headless task (required for Android when app is terminated).
  BackgroundFetch.registerHeadlessTask(backgroundFetchHeadlessTask);

  runApp(const MyApp());
}

/// Headless background fetch handler. Must be a top-level function.
void backgroundFetchHeadlessTask(HeadlessTask task) async {
  final String taskId = task.taskId;
  final bool isTimeout = task.timeout;

  if (isTimeout) {
    // This task has exceeded its allowed running-time.
    BackgroundFetch.finish(taskId);
    return;
  }

  try {
    await uploadHealthDataInBackground();
  } catch (e) {
    // Swallow errors; you may want to log these to persistent storage.
  } finally {
    BackgroundFetch.finish(taskId);
  }
}

/// Configure BackgroundFetch to run periodically. Call from an active context
/// (e.g. in a `State.initState`).
Future<void> startBackgroundFetch() async {
  // Configure the plugin.
  await BackgroundFetch.configure(
    BackgroundFetchConfig(
      minimumFetchInterval: 15, // minutes
      stopOnTerminate: false, // Android-only; iOS ignores
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
      } catch (e) {
        // handle/log
      } finally {
        BackgroundFetch.finish(taskId);
      }
    },
    (String taskId) async {
      BackgroundFetch.finish(taskId);
    },
  );
}

/// Read health data and upload it to your server. Keep this work short.
Future<void> uploadHealthDataInBackground() async {
  final health = Health();

  // Ensure the plugin is configured. In background contexts the user should
  // already have granted permission; avoid requesting permission here.
  try {
    await health.configure();
  } catch (e) {
    // If configure fails, abort.
    return;
  }

  final types = allRequestedHealthDataTypes; // choose group you want to upload
  final now = DateTime.now();
  // Fetch last 15 minutes of data (adjust as needed)
  final from = now.subtract(Duration(minutes: 15));

  List<HealthDataPoint> healthData = [];
  try {
    healthData = await health.getHealthDataFromTypes(
      startTime: from,
      endTime: now,
      types: types,
    );
  } catch (e) {
    // plugin may fail in background isolate; handle gracefully.
    return;
  }

  Map<String, dynamic> payload = {
    'healthData': healthData.map((data) => {
      'type': data.type.toString(),
      'value': data.value.toString(),
      'unit': data.unit.toString(),
      'dateFrom': data.dateFrom.toIso8601String(),
      'dateTo': data.dateTo.toIso8601String(),
    }).toList(),
    'timestamp': now.toIso8601String(),
  };

  // Upload with a short timeout.
  try {
    final client = HttpClient();
    client.connectionTimeout = Duration(seconds: 20);
    final request = await client.postUrl(Uri.parse(kHealthUploadUrl));
    request.headers.set(HttpHeaders.contentTypeHeader, 'application/json');
    request.add(utf8.encode(jsonEncode(payload)));
    final response = await request.close().timeout(Duration(seconds: 20));
    // Optionally check response.statusCode
    await response.drain();
    client.close(force: true);
  } catch (e) {
    // failed to upload — consider local persistence for retry.
  }
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
  int _counter = 0;
  
  final health = Health();

  void _incrementCounter() {
    setState(() {
      _counter++;
    });
  }

  Future<void> _getHealthData() async {
    try {
      await health.configure();

      // Which data types to request are defined in `lib/health_data_types.dart`.
      var types = allRequestedHealthDataTypes;

      // Request read/write permissions for each requested type.
      var permissions = permissionsFor(types);
      bool requested = await health.requestAuthorization(types, permissions: permissions);

      if (!requested) {
        _showMessage('Authorization not granted');
        return;
      }

      var now = DateTime.now();

      List<HealthDataPoint> healthData = await health.getHealthDataFromTypes(
         startTime: now.subtract(Duration(days: 1)), 
         endTime: now, 
         types: types);
      
    // (authorization already requested above using clinicianDataTypes)

      var midnight = DateTime(now.year, now.month, now.day);
      int? steps = await health.getTotalStepsInInterval(midnight, now);

      Map<String, dynamic> healthJson = {
        'healthData': healthData.map((data) => {
          'type': data.type.toString(),
          'value': data.value.toString(),
          'unit': data.unit.toString(),
          'dateFrom': data.dateFrom.toIso8601String(),
          'dateTo': data.dateTo.toIso8601String(),
        }).toList(),
        'totalStepsToday': steps,
        'dataPointsCount': healthData.length,
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
            child: Text(message),
          ),
          actions: [
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
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            const Text('You have pushed the button this many times:'),
            Text(
              '$_counter',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: _getHealthData,
              child: const Text('Get Health Data'),
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _incrementCounter,
        tooltip: 'Increment',
        child: const Icon(Icons.add),
      ), // This trailing comma makes auto-formatting nicer for build methods.
    );
  }
}
