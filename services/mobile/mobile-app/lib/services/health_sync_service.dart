import 'dart:convert';
import 'dart:io';

import 'package:health/health.dart';

import '../health_data_formatter.dart';
import '../health_data_types.dart';
import '../storage_service.dart';

enum HealthSyncStatus {
  success,
  partialSuccess,
  nothingToSend,
  permissionDenied,
  failed,
}

class HealthSyncResult {
  const HealthSyncResult({
    required this.status,
    required this.totalSent,
    required this.totalAvailable,
    required this.rangeStart,
    required this.rangeEnd,
    this.lastError,
  });

  final HealthSyncStatus status;
  final int totalSent;
  final int totalAvailable;
  final DateTime rangeStart;
  final DateTime rangeEnd;
  final String? lastError;

  bool get hasUploads => totalSent > 0;
  bool get isSuccess => status == HealthSyncStatus.success;
}

/// Handles querying the Health API, chunking the payload, and pushing it
/// to the ingest endpoint. UI/background layers simply react to the result.
class HealthSyncService {
  HealthSyncService({Health? health}) : _health = health ?? Health();

  final Health _health;
  static const _chunkSize = 500;
  static const _endpoint = 'https://wearables.cherep.co/import/ingest';

  Future<HealthSyncResult> sendSinceLastSync({
    Duration fallbackWindow = const Duration(days: 7),
    bool requestPermissions = true,
  }) async {
    final now = DateTime.now();

    try {
      await _health.configure();
    } catch (e) {
      return HealthSyncResult(
        status: HealthSyncStatus.failed,
        totalSent: 0,
        totalAvailable: 0,
        rangeStart: now,
        rangeEnd: now,
        lastError: 'Unable to configure health plugin: $e',
      );
    }

    final types = allRequestedHealthDataTypes;
    if (requestPermissions) {
      final permissions = permissionsFor(types);
      final granted = await _health.requestAuthorization(types, permissions: permissions);
      if (!granted) {
        return HealthSyncResult(
          status: HealthSyncStatus.permissionDenied,
          totalSent: 0,
          totalAvailable: 0,
          rangeStart: now,
          rangeEnd: now,
          lastError: 'Authorization not granted',
        );
      }
    }

    final deviceId = await StorageService.getOrCreateDeviceId();
    final lastSendTime = await StorageService.getLastDataSendTime();
    final from = lastSendTime ?? now.subtract(fallbackWindow);

    List<HealthDataPoint> healthData;
    try {
      healthData = await _health.getHealthDataFromTypes(
        startTime: from,
        endTime: now,
        types: types,
      );
    } catch (e) {
      return HealthSyncResult(
        status: HealthSyncStatus.failed,
        totalSent: 0,
        totalAvailable: 0,
        rangeStart: from,
        rangeEnd: now,
        lastError: 'Failed to read health data: $e',
      );
    }

    if (healthData.isEmpty) {
      return HealthSyncResult(
        status: HealthSyncStatus.nothingToSend,
        totalSent: 0,
        totalAvailable: 0,
        rangeStart: from,
        rangeEnd: now,
      );
    }

    final midnight = DateTime(now.year, now.month, now.day);
    final steps = await _health.getTotalStepsInInterval(midnight, now);

    int totalSent = 0;
    String? lastError;
    final totalAvailable = healthData.length;
    final chunks = _chunkHealthData(healthData);

    for (int chunkIndex = 0; chunkIndex < chunks.length; chunkIndex++) {
      final chunk = chunks[chunkIndex];
      try {
        await _sendChunk(
          chunk: chunk,
          chunkIndex: chunkIndex,
          totalChunks: chunks.length,
          from: from,
          to: now,
          lastSendTime: lastSendTime,
          deviceId: deviceId,
          stepsToday: steps,
        );
        totalSent += chunk.length;
        if (chunkIndex < chunks.length - 1) {
          await Future.delayed(const Duration(milliseconds: 500));
        }
      } catch (e) {
        lastError = 'Chunk ${chunkIndex + 1} failed: $e';
      }
    }

    if (totalSent > 0) {
      await StorageService.updateLastDataSendTime(now);
    }

    final status = _determineStatus(totalSent, totalAvailable, lastError);
    return HealthSyncResult(
      status: status,
      totalSent: totalSent,
      totalAvailable: totalAvailable,
      rangeStart: from,
      rangeEnd: now,
      lastError: lastError,
    );
  }

  List<List<HealthDataPoint>> _chunkHealthData(List<HealthDataPoint> data) {
    final chunks = <List<HealthDataPoint>>[];
    for (var i = 0; i < data.length; i += _chunkSize) {
      final end = (i + _chunkSize < data.length) ? i + _chunkSize : data.length;
      chunks.add(data.sublist(i, end));
    }
    return chunks;
  }

  Future<void> _sendChunk({
    required List<HealthDataPoint> chunk,
    required int chunkIndex,
    required int totalChunks,
    required DateTime from,
    required DateTime to,
    required DateTime? lastSendTime,
    required String deviceId,
    required int? stepsToday,
  }) async {
    final payload = {
      'deviceInfo': {
        'platform': Platform.isIOS ? 'iOS' : 'Android',
        'deviceId': deviceId,
        'authorizationToken': 'your_auth_token_here',
      },
      'batchInfo': {
        'batchId': '${DateTime.now().millisecondsSinceEpoch}_${chunkIndex + 1}',
        'chunkNumber': chunkIndex + 1,
        'totalChunks': totalChunks,
        'collectionStart': from.toIso8601String(),
        'collectionEnd': to.toIso8601String(),
        'lastSendTime': lastSendTime?.toIso8601String(),
        'dataPointCount': chunk.length,
      },
      'measurements': formatHealthDataByType(chunk),
      'sourceName': chunk.isNotEmpty ? chunk.first.sourceName : 'N/A',
      'sourcePlatform': chunk.isNotEmpty ? chunk.first.sourcePlatform.toString() : 'N/A',
      'totalStepsToday': stepsToday,
      'timestamp': DateTime.now().toIso8601String(),
    };

    final client = HttpClient();
    client.connectionTimeout = const Duration(seconds: 30);
    try {
      final request = await client.postUrl(Uri.parse(_endpoint));
      request.headers.set(HttpHeaders.contentTypeHeader, 'application/json');
      request.add(utf8.encode(jsonEncode(payload)));
      final response = await request.close().timeout(const Duration(seconds: 30));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final body = await response.transform(utf8.decoder).join();
        throw HttpException('Status ${response.statusCode}: $body');
      }
      await response.drain();
    } finally {
      client.close(force: true);
    }
  }

  HealthSyncStatus _determineStatus(int sent, int total, String? error) {
    if (sent == 0) {
      return HealthSyncStatus.failed;
    }
    if (sent < total || error != null) {
      return HealthSyncStatus.partialSuccess;
    }
    return HealthSyncStatus.success;
  }
}
