import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:health/health.dart';

import 'health_data_formatter.dart';
import 'health_data_types.dart';
import 'storage_service.dart';
import 'theme/app_theme.dart';
import 'utils/formatting.dart';

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
        // iOS never reveals whether read access was granted (hasPermissions
        // returns null/false for READ types), so a per-type check would always
        // fail there. Rely on requestAuthorization's result, like the sync does.
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
          title: const Text('Data preview'),
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

  String _formatDuration() {
    final d = _endDate.difference(_startDate);
    if (d.inDays >= 1) return '${d.inDays} d ${d.inHours % 24} h';
    return '${d.inHours} h ${d.inMinutes % 60} min';
  }

  @override
  Widget build(BuildContext context) {
    const quick = [
      ('1 hour', Duration(hours: 1)),
      ('6 hours', Duration(hours: 6)),
      ('24 hours', Duration(days: 1)),
      ('7 days', Duration(days: 7)),
    ];
    final selected = _endDate.difference(_startDate);
    return Scaffold(
      appBar: AppBar(title: const Text('My data')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          Text(
            'See exactly which Apple Health data the app reads for a period. '
            'The preview uses the same format as the upload.',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: AppColors.textMuted,
                ),
          ),
          const SizedBox(height: 20),
          Card(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(20, 4, 20, 12),
                    child: Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final (label, duration) in quick)
                          ChoiceChip(
                            label: Text(label),
                            selected: (selected - duration).inMinutes.abs() < 2,
                            onSelected: (_) => _setQuickPeriod(duration),
                            selectedColor: AppColors.skySoft,
                            side: const BorderSide(color: AppColors.outline),
                            showCheckmark: false,
                            labelStyle: const TextStyle(
                              fontWeight: FontWeight.w600,
                              color: AppColors.navy,
                            ),
                          ),
                      ],
                    ),
                  ),
                  const Divider(indent: 20, endIndent: 20),
                  ListTile(
                    leading: const Icon(Icons.first_page_rounded),
                    title: const Text('From'),
                    trailing: Text(formatDateTime(_startDate)),
                    onTap: _selectStartDate,
                  ),
                  ListTile(
                    leading: const Icon(Icons.last_page_rounded),
                    title: const Text('To'),
                    trailing: Text(formatDateTime(_endDate)),
                    onTap: _selectEndDate,
                  ),
                  ListTile(
                    leading: const Icon(Icons.timelapse_rounded),
                    title: const Text('Duration'),
                    trailing: Text(_formatDuration()),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
          FilledButton.icon(
            onPressed: _getHealthData,
            icon: const Icon(Icons.visibility_outlined),
            label: const Text('Show data'),
          ),
        ],
      ),
    );
  }
}
