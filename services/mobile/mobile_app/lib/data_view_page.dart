import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:health/health.dart';

import 'health_data_formatter.dart';
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

  /// Collects health data for the selected interval and shows it as JSON.
  Future<void> _getHealthData() async {
    try {
      await health.configure();


      // Use platform-specific health data types
      var types = Platform.isIOS ? iosHealthDataTypes : androidHealthDataTypes;
      var permissions = permissionsFor(types);

      // Check if permissions are already granted before requesting
      bool alreadyGranted = await health.hasPermissions(types, permissions: permissions) ?? false;
      if (!alreadyGranted) {
        bool requested = await health.requestAuthorization(
          types,
          permissions: permissions,
        );
        // Debug: Check which permissions are not granted
        List<String> notGranted = [];
        for (int i = 0; i < types.length; i++) {
          bool granted = await health.hasPermissions([types[i]], permissions: [permissions[i]]) ?? false;
          if (!granted) {
            notGranted.add(types[i].toString());
          }
        }
        if (notGranted.isNotEmpty) {
          _showMessage('Authorization not granted for:\n' + notGranted.join('\n'));
          return;
        }
        if (!requested) {
          _showMessage('Authorization not granted');
          return;
        }
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

      final Map<String, dynamic> healthJson = {
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
        // Use the shared formatter so the JSON looks identical
        // to what the upload API receives.
        'measurements': formatHealthDataByType(healthData),
        'sourceName': healthData.isNotEmpty
            ? healthData.first.sourceName
            : 'N/A',
        'sourcePlatform': healthData.isNotEmpty
            ? healthData.first.sourcePlatform.toString()
            : 'N/A',
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
      appBar: AppBar(title: const Text('Health Data Viewer')),
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
            child: LayoutBuilder(
              builder: (context, constraints) {
                return SingleChildScrollView(
                  child: ConstrainedBox(
                    constraints: BoxConstraints(
                      minHeight: constraints.maxHeight,
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Column(
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
                                          color: Theme.of(
                                            context,
                                          ).colorScheme.primary,
                                        ),
                                        const SizedBox(width: 8),
                                        Text(
                                          'Quick Time Selection',
                                          style: Theme.of(context)
                                              .textTheme
                                              .titleMedium
                                              ?.copyWith(
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
                                        _QuickButton(
                                          'Last Hour',
                                          const Duration(hours: 1),
                                          _setQuickPeriod,
                                        ),
                                        _QuickButton(
                                          'Last 6h',
                                          const Duration(hours: 6),
                                          _setQuickPeriod,
                                        ),
                                        _QuickButton(
                                          'Last 24h',
                                          const Duration(days: 1),
                                          _setQuickPeriod,
                                        ),
                                        _QuickButton(
                                          'Last Week',
                                          const Duration(days: 7),
                                          _setQuickPeriod,
                                        ),
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
                                          color: Theme.of(
                                            context,
                                          ).colorScheme.primary,
                                        ),
                                        const SizedBox(width: 8),
                                        Text(
                                          'Custom Period',
                                          style: Theme.of(context)
                                              .textTheme
                                              .titleMedium
                                              ?.copyWith(
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
                                            crossAxisAlignment:
                                                CrossAxisAlignment.start,
                                            children: [
                                              Text(
                                                'From',
                                                style: Theme.of(
                                                  context,
                                                ).textTheme.labelMedium,
                                              ),
                                              const SizedBox(height: 4),
                                              Text(
                                                _formatDateTime(_startDate),
                                                style: Theme.of(
                                                  context,
                                                ).textTheme.bodyMedium,
                                              ),
                                            ],
                                          ),
                                        ),
                                        ElevatedButton.icon(
                                          onPressed: _selectStartDate,
                                          icon: const Icon(
                                            Icons.edit,
                                            size: 16,
                                          ),
                                          label: const Text('Change'),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 16),
                                    Row(
                                      children: [
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment:
                                                CrossAxisAlignment.start,
                                            children: [
                                              Text(
                                                'To',
                                                style: Theme.of(
                                                  context,
                                                ).textTheme.labelMedium,
                                              ),
                                              const SizedBox(height: 4),
                                              Text(
                                                _formatDateTime(_endDate),
                                                style: Theme.of(
                                                  context,
                                                ).textTheme.bodyMedium,
                                              ),
                                            ],
                                          ),
                                        ),
                                        ElevatedButton.icon(
                                          onPressed: _selectEndDate,
                                          icon: const Icon(
                                            Icons.edit,
                                            size: 16,
                                          ),
                                          label: const Text('Change'),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 16),
                                    Container(
                                      padding: const EdgeInsets.all(12),
                                      decoration: BoxDecoration(
                                        color: Theme.of(context)
                                            .colorScheme
                                            .primaryContainer
                                            .withOpacity(0.3),
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      child: Row(
                                        mainAxisAlignment:
                                            MainAxisAlignment.center,
                                        children: [
                                          Icon(
                                            Icons.timelapse,
                                            size: 16,
                                            color: Theme.of(
                                              context,
                                            ).colorScheme.onPrimaryContainer,
                                          ),
                                          const SizedBox(width: 8),
                                          Text(
                                            'Duration: ${_endDate.difference(_startDate).inHours}h ${_endDate.difference(_startDate).inMinutes % 60}m',
                                            style: Theme.of(context)
                                                .textTheme
                                                .bodyMedium
                                                ?.copyWith(
                                                  color: Theme.of(context)
                                                      .colorScheme
                                                      .onPrimaryContainer,
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
                          ],
                        ),
                        Column(
                          children: [
                            const SizedBox(height: 24),
                            // Get Data Button
                            SizedBox(
                              width: double.infinity,
                              child: ElevatedButton.icon(
                                onPressed: _getHealthData,
                                icon: const Icon(Icons.visibility),
                                label: const Text('View Health Data'),
                                style: ElevatedButton.styleFrom(
                                  padding: const EdgeInsets.symmetric(
                                    vertical: 16,
                                  ),
                                  backgroundColor: Theme.of(
                                    context,
                                  ).colorScheme.secondary,
                                  foregroundColor: Theme.of(
                                    context,
                                  ).colorScheme.onSecondary,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              },
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
