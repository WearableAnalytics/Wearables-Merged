import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:health/health.dart';
import 'dart:convert';
import 'dart:io';
import 'health_data_types.dart';
import 'storage_service.dart';

class DataViewPage extends StatefulWidget {
  const DataViewPage({super.key});

  @override
  State<DataViewPage> createState() => _DataViewPageState();
}

class _DataViewPageState extends State<DataViewPage> {
  final health = Health();
  DateTime _startDate = DateTime.now().subtract(const Duration(days: 1));
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

      // Get device ID and last send time
      final deviceId = await StorageService.getOrCreateDeviceId();
      final lastSendTime = await StorageService.getLastDataSendTime();

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
          'deviceId': deviceId,
          'authorizationToken': 'your_auth_token_here',
        },
        'batchInfo': {
          'collectionStart': _startDate.toIso8601String(),
          'collectionEnd': _endDate.toIso8601String(),
          'lastSendTime': lastSendTime?.toIso8601String(),
        },
        'measurements': _formatHealthDataByType(healthData),
        'sourceName': healthData.isNotEmpty ? healthData.first.sourceName : 'N/A',
        'sourcePlatform': healthData.isNotEmpty ? healthData.first.sourcePlatform.toString() : 'N/A',
        'totalStepsToday': steps,
        'timestamp': DateTime.now().toIso8601String(),
      };

      _showMessage(const JsonEncoder.withIndent('  ').convert(healthJson));
    } catch (e) {
      _showMessage('Error getting health data: $e');
    }
  }

  void _showMessage(String message) {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: const Text('Health Data'),
          content: SingleChildScrollView(
            child: SelectableText(
              message,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Clipboard.setData(ClipboardData(text: message));
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('Health data copied to clipboard'),
                    duration: Duration(seconds: 2),
                  ),
                );
              },
              child: const Text('Copy'),
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

  Future<void> _selectStartDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _startDate,
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
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
            _endDate = _startDate.add(const Duration(hours: 1));
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
            _startDate = _endDate.subtract(const Duration(hours: 1));
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
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Health Data Viewer'),
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
              children: [
                // Quick Selection Card
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
                              Icons.schedule,
                              color: Theme.of(context).colorScheme.primary,
                            ),
                            const SizedBox(width: 8),
                            Text(
                              'Quick Time Selection',
                              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        Wrap(
                          spacing: 12,
                          runSpacing: 8,
                          children: [
                            _QuickButton('Last Hour', const Duration(hours: 1), _setQuickPeriod),
                            _QuickButton('Last 6h', const Duration(hours: 6), _setQuickPeriod),
                            _QuickButton('Last 24h', const Duration(days: 1), _setQuickPeriod),
                            _QuickButton('Last Week', const Duration(days: 7), _setQuickPeriod),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 16),

                // Custom Period Selection Card
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
                              Icons.date_range,
                              color: Theme.of(context).colorScheme.primary,
                            ),
                            const SizedBox(width: 8),
                            Text(
                              'Custom Period',
                              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),

                        Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    'From',
                                    style: Theme.of(context).textTheme.labelMedium,
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    _formatDateTime(_startDate),
                                    style: Theme.of(context).textTheme.bodyMedium,
                                  ),
                                ],
                              ),
                            ),
                            ElevatedButton.icon(
                              onPressed: _selectStartDate,
                              icon: const Icon(Icons.edit, size: 16),
                              label: const Text('Change'),
                            ),
                          ],
                        ),

                        const SizedBox(height: 16),

                        Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    'To',
                                    style: Theme.of(context).textTheme.labelMedium,
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    _formatDateTime(_endDate),
                                    style: Theme.of(context).textTheme.bodyMedium,
                                  ),
                                ],
                              ),
                            ),
                            ElevatedButton.icon(
                              onPressed: _selectEndDate,
                              icon: const Icon(Icons.edit, size: 16),
                              label: const Text('Change'),
                            ),
                          ],
                        ),

                        const SizedBox(height: 16),
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: Theme.of(context).colorScheme.primaryContainer.withOpacity(0.3),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(
                                Icons.timelapse,
                                size: 16,
                                color: Theme.of(context).colorScheme.onPrimaryContainer,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                'Duration: ${_endDate.difference(_startDate).inHours}h ${_endDate.difference(_startDate).inMinutes % 60}m',
                                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                  color: Theme.of(context).colorScheme.onPrimaryContainer,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 24),

                // Get Data Button
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _getHealthData,
                    icon: const Icon(Icons.visibility),
                    label: const Text('View Health Data'),
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      backgroundColor: Theme.of(context).colorScheme.secondary,
                      foregroundColor: Theme.of(context).colorScheme.onSecondary,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _QuickButton extends StatelessWidget {
  final String label;
  final Duration duration;
  final Function(Duration) onPressed;

  const _QuickButton(this.label, this.duration, this.onPressed);

  @override
  Widget build(BuildContext context) {
    return OutlinedButton(
      onPressed: () => onPressed(duration),
      child: Text(label),
      style: OutlinedButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
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
