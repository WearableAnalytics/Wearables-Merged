import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:health/health.dart';

import '../health_data_formatter.dart';

String newUploadKey() {
  final random = Random.secure();
  return List.generate(
    16,
    (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
  ).join();
}

/// Native provider identity, independent of the collector and authentication.
typedef UploadSource = ({String id, String name, String platform});

UploadSource _sourceOf(HealthDataPoint point) => (
  id: point.sourceId,
  name: point.sourceName,
  platform: point.sourcePlatform == HealthPlatformType.appleHealth
      ? 'apple-health'
      : 'health-connect',
);

extension UploadSourceMetadata on UploadSource {
  Map<String, String> toLegacyMetadata() => {
    'sourceName': name,
    'sourcePlatform': platform,
    if (id.isNotEmpty) 'sourceId': id,
  };
}

/// Immutable wire request, reused verbatim after an uncertain response.
class HealthUpload {
  HealthUpload(
    Map<String, dynamic> payload,
    this.key,
    this.readingCount, {
    required this.source,
  }) : bytes = List.unmodifiable(utf8.encode(jsonEncode(payload)));

  final UploadSource source;
  final List<int> bytes;
  final String key;
  final int readingCount;
  String get sha256Hex => sha256.convert(bytes).toString();
}

String _formatUuid(String hex32) {
  if (hex32.length != 32) return "00000000-0000-0000-0000-000000000000";
  return hex32.substring(0, 8) +
      "-" +
      hex32.substring(8, 12) +
      "-" +
      hex32.substring(12, 16) +
      "-" +
      hex32.substring(16, 20) +
      "-" +
      hex32.substring(20, 32);
}

class UploadReceipt {
  factory UploadReceipt.synthetic(HealthUpload upload) {
    return UploadReceipt._({
      "status": "archived",
      "acceptanceId": _formatUuid(upload.key),
      "readingCount": upload.readingCount,
      "rawSha256": upload.sha256Hex,
      "processingState": "awaiting-processing",
      "receivedAt": DateTime.now().toUtc().toIso8601String(),
    });
  }

  UploadReceipt._(this.document);
  final Map<String, dynamic> document;
  String get acceptanceId => document['acceptanceId'] as String;
  String get processingState => document['processingState'] as String;
  int get readingCount => document['readingCount'] as int;
  String get rawSha256 => document['rawSha256'] as String;

  static UploadReceipt validate(String body, HealthUpload upload) {
    final value = jsonDecode(body);
    if (value is! Map<String, dynamic> ||
        value['status'] != 'archived' ||
        value['acceptanceId'] is! String ||
        !RegExp(
          r'^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$',
        ).hasMatch(value['acceptanceId'] as String) ||
        value['readingCount'] != upload.readingCount ||
        value['rawSha256'] != upload.sha256Hex ||
        !processingStates.contains(value['processingState'])) {
      throw const FormatException('Invalid or mismatched upload receipt');
    }
    return UploadReceipt._(Map.unmodifiable(value));
  }

  static const processingStates = {
    'awaiting-delivery',
    'awaiting-processing',
    'awaiting-storage',
    'storage-observed',
    'partially-rejected',
    'rejected',
    'blocked',
    'needs-review',
  };
}

/// Groups only serializable readings, keeping provider metadata with its data.
/// Limits include the complete UTF-8 JSON envelope, not just the measurements.
/// Build-time INGEST_MAX_READINGS / INGEST_MAX_BODY_BYTES must not exceed the
/// deployed import service's limits. Defaults match reliable-ingestion defaults;
/// these values are not discovered from the server at runtime.
List<HealthUpload> prepareHealthUploads({
  required List<HealthDataPoint> points,
  required String collectorId,
  required String platform,
  required DateTime from,
  required DateTime to,
  required DateTime? lastSendTime,
  required int? stepsToday,
  int maxReadings = const int.fromEnvironment(
    'INGEST_MAX_READINGS',
    defaultValue: 1000,
  ),
  int maxBytes = const int.fromEnvironment(
    'INGEST_MAX_BODY_BYTES',
    defaultValue: 500000,
  ),
  DateTime? now,
}) {
  if (maxReadings < 1 || maxBytes < 1) {
    throw ArgumentError('Upload limits must be positive');
  }
  final uploads = <HealthUpload>[];
  final timestamp = (now ?? DateTime.now()).toUtc().toIso8601String();
  Map<String, dynamic>? payload;
  UploadSource? source;
  String? key;
  var count = 0;
  var byteLength = 0;

  void finish() {
    if (count == 0) return;
    final upload = HealthUpload(payload!, key!, count, source: source!);
    if (upload.bytes.length > maxBytes) {
      throw StateError('Upload exceeds the configured byte limit');
    }
    uploads.add(upload);
    count = 0;
  }

  void start(HealthDataPoint point) {
    key = newUploadKey();
    payload = {
      'deviceInfo': {'platform': platform, 'deviceId': collectorId},
      'batchInfo': {
        'batchId': key,
        'collectionStart': from.toUtc().toIso8601String(),
        'collectionEnd': to.toUtc().toIso8601String(),
        'lastSendTime': lastSendTime?.toUtc().toIso8601String(),
        'dataPointCount': 0,
      },
      'measurements': {
        'instantaneous': <Map<String, dynamic>>[],
        'cumulative': <Map<String, dynamic>>[],
        'duration': <Map<String, dynamic>>[],
      },
      ..._sourceOf(point).toLegacyMetadata(),
      if (point.uuid.isNotEmpty && point.sourceId.isNotEmpty)
        'contractVersion': 'wearables-numeric/1',
      'totalStepsToday': stepsToday,
      'timestamp': timestamp,
    };
    byteLength = utf8.encode(jsonEncode(payload)).length;
  }

  // Map insertion order keeps the first-seen source order; readings retain
  // their order within each source. Interleaving must not fragment requests.
  final groups = <UploadSource, List<HealthDataPoint>>{};
  for (final point in points) {
    groups.putIfAbsent(_sourceOf(point), () => []).add(point);
  }
  for (final point in groups.values.expand((group) => group)) {
    final formatted = formatHealthDataByType([point]);
    final category = categoryForPoint(point);
    final readings = formatted[category] as List;
    if (readings.isEmpty) continue;
    final reading = readings.single as Map<String, dynamic>;
    if (point.uuid.isNotEmpty) reading['sourceRecordId'] = point.uuid;
    if (point.sourceDeviceId.isNotEmpty) {
      reading['sourceDeviceId'] = point.sourceDeviceId;
    }
    final pointSource = _sourceOf(point);
    final identified = point.uuid.isNotEmpty && point.sourceId.isNotEmpty;
    if (payload == null ||
        source != pointSource ||
        payload!.containsKey('contractVersion') != identified) {
      finish();
      start(point);
      source = pointSource;
    }
    var measurements = payload!['measurements'] as Map<String, dynamic>;
    var list = measurements[category] as List<Map<String, dynamic>>;
    final readingBytes = utf8.encode(jsonEncode(reading)).length;
    int addedBytes() =>
        readingBytes +
        (list.isEmpty ? 0 : 1) +
        (count + 1).toString().length -
        count.toString().length;
    if (count >= maxReadings || byteLength + addedBytes() > maxBytes) {
      finish();
      start(point);
      measurements = payload!['measurements'] as Map<String, dynamic>;
      list = measurements[category] as List<Map<String, dynamic>>;
    }
    if (byteLength + addedBytes() > maxBytes) {
      throw StateError(
        'A single reading and its metadata exceed the upload byte limit',
      );
    }
    byteLength += addedBytes();
    list.add(reading);
    count++;
    (payload!['batchInfo'] as Map<String, dynamic>)['dataPointCount'] = count;
  }
  finish();
  return uploads;
}

class UploadHttpException extends HttpException {
  UploadHttpException(this.statusCode, {this.retryAfter})
    : super('Status $statusCode: upload was not accepted');
  final int statusCode;
  final Duration? retryAfter;
}

/// A valid archived receipt is acceptance, not proof of downstream storage.
class HealthUploader {
  HealthUploader({
    required this.client,
    required this.endpoint,
    this.timeout = const Duration(seconds: 30),
    this.allowLegacy200 = true,
    Future<void> Function(Duration)? delay,
  }) : delay = delay ?? Future<void>.delayed;

  final HttpClient client;
  final Uri endpoint;
  final Duration timeout;
  final bool allowLegacy200;
  final Future<void> Function(Duration) delay;

  Future<UploadReceipt> send(HealthUpload upload, String token) async {
    const backoff = [Duration(seconds: 2), Duration(seconds: 6)];
    for (var attempt = 0; ; attempt++) {
      try {
        return await _sendOnce(upload, token);
      } catch (error) {
        final transient =
            error is SocketException ||
            error is TimeoutException ||
            error is HandshakeException ||
            error is HttpException &&
                (error is! UploadHttpException ||
                    error.statusCode == 408 ||
                    error.statusCode == 429 ||
                    error.statusCode >= 500);
        if (!transient || attempt >= backoff.length) rethrow;
        final retryAfter = error is UploadHttpException
            ? error.retryAfter
            : null;
        // Long quota waits are deferred to a later sync; never block background
        // execution for an hour, and never retry earlier than Retry-After.
        if (retryAfter != null && retryAfter > const Duration(seconds: 30)) {
          rethrow;
        }
        await delay(
          retryAfter != null && retryAfter > backoff[attempt]
              ? retryAfter
              : backoff[attempt],
        );
      }
    }
  }

  Future<UploadReceipt> _sendOnce(HealthUpload upload, String token) async {
    HttpClientRequest? request;
    try {
      request = await client.postUrl(endpoint).timeout(timeout);
      request.headers.set(HttpHeaders.contentTypeHeader, 'application/json');
      request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
      request.headers.set('Idempotency-Key', upload.key);
      request.contentLength = upload.bytes.length;
      request.add(upload.bytes);
      final response = await request.close().timeout(timeout);
      // Reading the body is part of the deadline too. Abort stalled requests.
      final body = await response
          .transform(utf8.decoder)
          .join()
          .timeout(timeout);
      if (response.statusCode != HttpStatus.accepted) {
        if (allowLegacy200 && response.statusCode == HttpStatus.ok) {
          return UploadReceipt.synthetic(upload);
        }
        final header = response.headers.value(HttpHeaders.retryAfterHeader);
        Duration? retryAfter;
        if (header != null) {
          final seconds = int.tryParse(header);
          if (seconds != null) {
            retryAfter = Duration(seconds: seconds < 0 ? 0 : seconds);
          } else {
            try {
              final wait = HttpDate.parse(
                header,
              ).difference(DateTime.now().toUtc());
              retryAfter = wait.isNegative ? Duration.zero : wait;
            } on FormatException {
              /* Use bounded backoff for invalid headers. */
            }
          }
        }
        throw UploadHttpException(response.statusCode, retryAfter: retryAfter);
      }
      return UploadReceipt.validate(body, upload);
    } catch (_) {
      request?.abort();
      rethrow;
    }
  }

  Future<Map<String, dynamic>> status(String acceptanceId, String token) async {
    if (!RegExp(r'^[0-9a-fA-F-]{36}$').hasMatch(acceptanceId)) {
      throw ArgumentError('Invalid acceptance ID');
    }
    final request = await client
        .getUrl(Uri.parse('$endpoint/$acceptanceId'))
        .timeout(timeout);
    request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
    final response = await request.close().timeout(timeout);
    final body = await response.transform(utf8.decoder).join().timeout(timeout);
    if (response.statusCode != 200) {
      throw UploadHttpException(response.statusCode);
    }
    final value = jsonDecode(body);
    if (value is! Map<String, dynamic> ||
        value['acceptanceId'] != acceptanceId ||
        value['status'] != 'archived' ||
        !UploadReceipt.processingStates.contains(value['processingState'])) {
      throw const FormatException('Invalid upload status');
    }
    return value;
  }
}

/// Save each receipt before committing collection progress. Partial acceptance
/// never advances this window; accepted counts can still be reported on failure.
Future<void> deliverHealthUploads({
  required List<HealthUpload> uploads,
  required Future<UploadReceipt> Function(HealthUpload) send,
  required Future<void> Function(UploadReceipt) saveReceipt,
  required void Function(int) onAccepted,
  required Future<void> Function() checkpoint,
}) async {
  for (final upload in uploads) {
    final receipt = await send(upload);
    await saveReceipt(receipt);
    onAccepted(upload.readingCount);
  }
  await checkpoint();
}
