import 'package:flutter/material.dart';
import 'package:health/health.dart';
import 'dart:convert';

void main() {
  runApp(const MyApp());
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

      var types = [
        HealthDataType.STEPS,
        HealthDataType.BLOOD_GLUCOSE,
      ];

      bool requested = await health.requestAuthorization(types);

      if (!requested) {
        _showMessage('Authorization not granted');
        return;
      }

      var now = DateTime.now();

      List<HealthDataPoint> healthData = await health.getHealthDataFromTypes(
         startTime: now.subtract(Duration(days: 1)), 
         endTime: now, 
         types: types);
      
      types = [HealthDataType.STEPS, HealthDataType.BLOOD_GLUCOSE];
      var permissions = [
          HealthDataAccess.READ_WRITE,
          HealthDataAccess.READ_WRITE
      ];
      await health.requestAuthorization(types, permissions: permissions);

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
