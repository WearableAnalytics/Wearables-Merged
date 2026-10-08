import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:health/health.dart';

import '../health_data_formatter.dart';
import '../health_data_types.dart';
import '../storage_service.dart';
import 'device_lock_service.dart';
import 'sync_activity_notifier.dart';

enum HealthSyncStatus {
  success,
  partialSuccess,
  nothingToSend,
  permissionDenied,
  protectedDataUnavailable,
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
  static const _endpoint = 'https://wearables.charite.de/import/ingest';

  Future<HealthSyncResult> sendSinceLastSync({
    bool requestPermissions = true,
  }) async {
    final now = DateTime.now();
    final activity = SyncActivityNotifier.startSync();
    HealthSyncResult complete(HealthSyncResult result) {
      SyncActivityNotifier.reportResult(_mapOutcome(result.status));
      return result;
    }

    try {
      try {
        await _health.configure();
      } catch (e) {
        return complete(
          HealthSyncResult(
            status: HealthSyncStatus.failed,
            totalSent: 0,
            totalAvailable: 0,
            rangeStart: now,
            rangeEnd: now,
            lastError: 'Unable to configure health plugin: $e',
          ),
        );
      }

      // Use platform-specific health data types
      final types = Platform.isIOS
          ? iosHealthDataTypes
          : androidHealthDataTypes;
      final permissions = permissionsFor(types);
      final alreadyGranted =
          await _health.hasPermissions(types, permissions: permissions) ??
          false;
      if (!alreadyGranted) {
        if (!requestPermissions) {
          return complete(
            HealthSyncResult(
              status: HealthSyncStatus.permissionDenied,
              totalSent: 0,
              totalAvailable: 0,
              rangeStart: now,
              rangeEnd: now,
              lastError: 'Health permissions not granted',
            ),
          );
        }

        final granted = await _health.requestAuthorization(
          types,
          permissions: permissions,
        );
        if (!granted) {
          return complete(
            HealthSyncResult(
              status: HealthSyncStatus.permissionDenied,
              totalSent: 0,
              totalAvailable: 0,
              rangeStart: now,
              rangeEnd: now,
              lastError: 'Authorization not granted',
            ),
          );
        }
      }

      final unlocked = await DeviceLockService.isDeviceUnlocked();
      if (!unlocked) {
        return complete(
          HealthSyncResult(
            status: HealthSyncStatus.protectedDataUnavailable,
            totalSent: 0,
            totalAvailable: 0,
            rangeStart: now,
            rangeEnd: now,
            lastError:
                'Protected health data is locked. Unlock the device to sync.',
          ),
        );
      }

      final deviceId = await StorageService.getOrCreateDeviceId();
      final lastSendTime = await StorageService.getLastDataSendTime();
      final from = lastSendTime ?? await StorageService.getInitialSyncStart();

      final midnight = DateTime(now.year, now.month, now.day);
      String? lastError;
      int? steps;
      try {
        steps = await _health.getTotalStepsInInterval(midnight, now);
      } catch (e) {
        if (_isProtectedDataError(e)) {
          return complete(_locked(from, now, 0, 0));
        }
        lastError = 'Failed to read step count: $e';
      }

      // Work through the range one day at a time and store progress after
      // each day, so an interrupted sync resumes where it stopped instead of
      // re-sending everything (and a failed batch is retried, not skipped).
      final totalSeconds = now.difference(from).inSeconds.clamp(1, 1 << 31);
      int totalSent = 0;
      int totalAvailable = 0;
      SyncActivityNotifier.reportProgress(0);

      for (final (start, end) in _dayWindows(from, now)) {
        if (!await DeviceLockService.isDeviceUnlocked()) {
          return complete(_locked(from, now, totalSent, totalAvailable));
        }

        List<HealthDataPoint> healthData;
        try {
          healthData = await _health.getHealthDataFromTypes(
            startTime: start,
            endTime: end,
            types: types,
          );
        } catch (e) {
          if (_isProtectedDataError(e)) {
            return complete(_locked(from, now, totalSent, totalAvailable));
          }
          lastError = 'Failed to read health data: $e';
          break;
        }

        totalAvailable += healthData.length;
        final chunks = _chunkHealthData(healthData);
        var dayComplete = true;
        for (int chunkIndex = 0; chunkIndex < chunks.length; chunkIndex++) {
          final chunk = chunks[chunkIndex];
          try {
            await _sendChunkWithRetry(
              chunk: chunk,
              chunkIndex: chunkIndex,
              totalChunks: chunks.length,
              from: start,
              to: end,
              lastSendTime: lastSendTime,
              deviceId: deviceId,
              stepsToday: steps,
            );
            totalSent += chunk.length;
            if (chunkIndex < chunks.length - 1) {
              await Future.delayed(const Duration(milliseconds: 150));
            }
          } catch (e) {
            lastError ??= 'Upload failed: $e';
            dayComplete = false;
            break;
          }
        }
        if (!dayComplete) break;

        await StorageService.updateLastDataSendTime(end);
        SyncActivityNotifier.reportProgress(
          end.difference(from).inSeconds / totalSeconds,
        );
      }

      if (totalAvailable == 0 && lastError == null) {
        return complete(
          HealthSyncResult(
            status: HealthSyncStatus.nothingToSend,
            totalSent: 0,
            totalAvailable: 0,
            rangeStart: from,
            rangeEnd: now,
          ),
        );
      }

      final status = _determineStatus(totalSent, totalAvailable, lastError);
      return complete(
        HealthSyncResult(
          status: status,
          totalSent: totalSent,
          totalAvailable: totalAvailable,
          rangeStart: from,
          rangeEnd: now,
          lastError: lastError,
        ),
      );
    } finally {
      activity.close();
    }
  }

  HealthSyncResult _locked(DateTime from, DateTime to, int sent, int total) {
    return HealthSyncResult(
      status: HealthSyncStatus.protectedDataUnavailable,
      totalSent: sent,
      totalAvailable: total,
      rangeStart: from,
      rangeEnd: to,
      lastError: 'Protected health data is locked. Unlock the device to sync.',
    );
  }

  /// Splits [from, to) at local midnights.
  List<(DateTime, DateTime)> _dayWindows(DateTime from, DateTime to) {
    final windows = <(DateTime, DateTime)>[];
    var start = from;
    while (start.isBefore(to)) {
      final nextMidnight = DateTime(start.year, start.month, start.day + 1);
      final end = nextMidnight.isBefore(to) ? nextMidnight : to;
      windows.add((start, end));
      start = end;
    }
    return windows;
  }

  SyncOutcome _mapOutcome(HealthSyncStatus status) {
    switch (status) {
      case HealthSyncStatus.success:
        return SyncOutcome.success;
      case HealthSyncStatus.partialSuccess:
        return SyncOutcome.incomplete;
      case HealthSyncStatus.nothingToSend:
        return SyncOutcome.nothingToSend;
      case HealthSyncStatus.permissionDenied:
      case HealthSyncStatus.protectedDataUnavailable:
      case HealthSyncStatus.failed:
        return SyncOutcome.failure;
    }
  }

  List<List<HealthDataPoint>> _chunkHealthData(List<HealthDataPoint> data) {
    final chunks = <List<HealthDataPoint>>[];
    for (var i = 0; i < data.length; i += _chunkSize) {
      final end = (i + _chunkSize < data.length) ? i + _chunkSize : data.length;
      chunks.add(data.sublist(i, end));
    }
    return chunks;
  }

  /// Retries transient failures (network drops, timeouts, server errors)
  /// before giving up; 4xx responses are not retried.
  Future<void> _sendChunkWithRetry({
    required List<HealthDataPoint> chunk,
    required int chunkIndex,
    required int totalChunks,
    required DateTime from,
    required DateTime to,
    required DateTime? lastSendTime,
    required String deviceId,
    required int? stepsToday,
  }) async {
    const backoff = [Duration(seconds: 2), Duration(seconds: 6)];
    for (var attempt = 0; ; attempt++) {
      try {
        return await _sendChunk(
          chunk: chunk,
          chunkIndex: chunkIndex,
          totalChunks: totalChunks,
          from: from,
          to: to,
          lastSendTime: lastSendTime,
          deviceId: deviceId,
          stepsToday: stepsToday,
        );
      } catch (e) {
        final transient =
            e is SocketException ||
            e is TimeoutException ||
            e is HandshakeException ||
            (e is HttpException && e.message.startsWith('Status 5'));
        if (!transient || attempt >= backoff.length) rethrow;
        await Future.delayed(backoff[attempt]);
      }
    }
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
      'sourcePlatform': chunk.isNotEmpty
          ? chunk.first.sourcePlatform.toString()
          : 'N/A',
      'totalStepsToday': stepsToday,
      'timestamp': DateTime.now().toIso8601String(),
    };

    final client = HttpClient();
    client.connectionTimeout = const Duration(seconds: 30);
    try {
      final request = await client.postUrl(Uri.parse(_endpoint));
      request.headers.set(HttpHeaders.contentTypeHeader, 'application/json');
      request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $deviceId');
      request.add(utf8.encode(jsonEncode(payload)));
      final response = await request.close().timeout(
        const Duration(seconds: 30),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final body = await response.transform(utf8.decoder).join();
        throw HttpException('Status ${response.statusCode}: $body');
      }
      final responseBody = await response.transform(utf8.decoder).join();
      // Optionally log or process the response body for successful requests
      if (responseBody.isNotEmpty) {
        print('Successful upload response: $responseBody');
      }
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

  bool _isProtectedDataError(Object error) {
    if (error is PlatformException) {
      final code = error.code.toLowerCase();
      final message = error.message?.toLowerCase() ?? '';
      final details = error.details?.toString().toLowerCase() ?? '';
      if (_protectedDataMatch(code) ||
          _protectedDataMatch(message) ||
          _protectedDataMatch(details)) {
        return true;
      }
    }

    final text = error.toString().toLowerCase();
    return _protectedDataMatch(text) ||
        (text.contains('hkerrordomain') && text.contains('code=4'));
  }

  bool _protectedDataMatch(String value) {
    if (value.isEmpty) return false;
    return value.contains('protected') &&
        (value.contains('unlock') ||
            value.contains('locked') ||
            value.contains('data is not available'));
  }
}
