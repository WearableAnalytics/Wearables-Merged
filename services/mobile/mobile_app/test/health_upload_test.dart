import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:health/health.dart';
import 'package:charite_wearables/services/health_upload.dart';
import 'package:charite_wearables/storage_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

HealthDataPoint point({
  String source = 'sensor',
  String? sourceId,
  HealthValue? value,
}) => HealthDataPoint(
  uuid: 'record',
  value: value ?? NumericHealthValue(numericValue: 61),
  type: HealthDataType.HEART_RATE,
  unit: HealthDataUnit.BEATS_PER_MINUTE,
  dateFrom: DateTime.parse('2026-11-03T10:00:00.123456+01:00'),
  dateTo: DateTime.parse('2026-11-03T10:00:01.654321+01:00'),
  sourcePlatform: HealthPlatformType.appleHealth,
  sourceDeviceId: 'device',
  sourceId: sourceId ?? source,
  sourceName: source,
);

List<HealthUpload> prepare(
  List<HealthDataPoint> points, {
  int maxBytes = 500000,
  int maxReadings = 1000,
}) => prepareHealthUploads(
  points: points,
  collectorId: 'collector',
  platform: 'iOS',
  from: DateTime.parse('2026-11-03T10:00:00+01:00'),
  to: DateTime.parse('2026-11-03T11:00:00+01:00'),
  lastSendTime: DateTime.parse('2026-11-03T09:00:00+01:00'),
  stepsToday: 1,
  now: DateTime.parse('2026-11-03T12:00:00+01:00'),
  maxBytes: maxBytes,
  maxReadings: maxReadings,
);

const acceptanceId = '12345678-1234-1234-1234-123456789abc';
Map<String, dynamic> receipt(HealthUpload upload) => {
  'acceptanceId': acceptanceId,
  'status': 'archived',
  'readingCount': upload.readingCount,
  'rawSha256': upload.sha256Hex,
  'processingState': 'awaiting-delivery',
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'splits by serialized count and preserves UTC timestamps and metadata',
    () {
      final uploads = prepare(List.generate(2001, (_) => point()));
      expect(uploads.map((u) => u.readingCount), [1000, 1000, 1]);
      final payload = jsonDecode(utf8.decode(uploads.first.bytes));
      expect(
        payload['measurements']['instantaneous'][0]['timestamp'],
        '2026-11-03T09:00:00.123456Z',
      );
      expect(
        payload['batchInfo']['collectionStart'],
        '2026-11-03T09:00:00.000Z',
      );
      expect(payload['batchInfo']['collectionEnd'], '2026-11-03T10:00:00.000Z');
      expect(payload['batchInfo']['lastSendTime'], '2026-11-03T08:00:00.000Z');
      expect(payload['timestamp'], '2026-11-03T11:00:00.000Z');
      expect(payload['sourceId'], 'sensor');
      expect(payload['sourcePlatform'], 'apple-health');
      expect(payload['contractVersion'], 'wearables-numeric/1');
      expect(
        payload['measurements']['instantaneous'][0]['sourceRecordId'],
        'record',
      );
      expect(
        payload['measurements']['instantaneous'][0]['sourceDeviceId'],
        'device',
      );
      expect(payload['deviceInfo'], {
        'deviceId': 'collector',
        'platform': 'iOS',
      });
      expect(uploads.every((u) => u.bytes.length <= 500000), isTrue);
      expect(() => uploads.first.bytes.add(1), throwsUnsupportedError);
    },
  );

  test(
    'missing native IDs remain legacy and do not borrow collector identity',
    () {
      final missing = point(sourceId: '');
      missing.uuid = '';
      final uploads = prepare([point(), missing]);
      expect(uploads.length, 2);
      final legacy = jsonDecode(utf8.decode(uploads.last.bytes));
      expect(legacy.containsKey('contractVersion'), isFalse);
      expect(legacy.containsKey('sourceId'), isFalse);
      expect(
        legacy['measurements']['instantaneous'][0].containsKey(
          'sourceRecordId',
        ),
        isFalse,
      );
    },
  );

  test('byte boundary includes UTF-8 metadata, envelope and count digits', () {
    final points = List.generate(12, (_) => point(source: '心率💓'));
    final exactSize = prepare(points.take(10).toList()).single.bytes.length;
    final uploads = prepare(points, maxBytes: exactSize);
    expect(uploads.map((u) => u.readingCount), [10, 2]);
    expect(uploads.first.bytes.length, exactSize);
    expect(uploads.every((u) => u.bytes.length <= exactSize), isTrue);
    expect(
      () => prepare([point(source: 'x' * 2000)], maxBytes: 1000),
      throwsStateError,
    );
  });

  test(
    'keeps sources separate and skips unsupported values without empty batches',
    () {
      expect(prepare([point(source: 'a'), point(source: 'b')]).length, 2);
      final unsupported = point(
        value: AudiogramHealthValue(
          frequencies: [1000],
          leftEarSensitivities: [20],
          rightEarSensitivities: [25],
        ),
      );
      expect(prepare([unsupported]), isEmpty);
      expect(prepare([unsupported, point()]).single.readingCount, 1);
      expect(prepare([]), isEmpty);
    },
  );

  test(
    'interleaved sources form complete batches and send native source IDs',
    () {
      final points = [
        point(source: 'same name', sourceId: 'provider-a'),
        point(source: 'same name', sourceId: 'provider-b'),
        point(source: 'same name', sourceId: 'provider-a'),
        point(source: 'same name', sourceId: 'provider-b'),
        point(source: 'same name', sourceId: 'provider-a'),
      ];
      final uploads = prepare(points, maxReadings: 2);
      expect(uploads.map((u) => u.readingCount), [2, 1, 2]);
      expect(uploads.map((u) => u.source.id), [
        'provider-a',
        'provider-a',
        'provider-b',
      ]);
      for (final upload in uploads) {
        expect(upload.source.name, 'same name');
        final wire = jsonDecode(utf8.decode(upload.bytes)) as Map;
        expect(wire['sourceName'], upload.source.name);
        expect(wire['sourcePlatform'], upload.source.platform);
        expect(wire['sourceId'], upload.source.id);
      }
    },
  );

  test('validates acceptance receipt against exact wire bytes and count', () {
    final upload = prepare([point()]).single;
    expect(
      UploadReceipt.validate(
        jsonEncode(receipt(upload)),
        upload,
      ).processingState,
      'awaiting-delivery',
    );
    for (final bad in [
      '{}',
      'not json',
      jsonEncode({...receipt(upload), 'rawSha256': 'wrong'}),
      jsonEncode({...receipt(upload), 'readingCount': 2}),
      jsonEncode({...receipt(upload), 'acceptanceId': 'wrong'}),
      jsonEncode({...receipt(upload), 'status': 'stored'}),
      jsonEncode({...receipt(upload), 'processingState': 'unknown'}),
    ]) {
      expect(() => UploadReceipt.validate(bad, upload), throwsFormatException);
    }
  });

  test(
    'failed batch or receipt persistence leaves checkpoint unchanged',
    () async {
      final uploads = prepare([point(), point()], maxReadings: 1);
      final events = <String>[];
      var calls = 0;
      await expectLater(
        deliverHealthUploads(
          uploads: uploads,
          send: (upload) async {
            if (++calls == 2) throw TimeoutException('response lost');
            return UploadReceipt.validate(jsonEncode(receipt(upload)), upload);
          },
          saveReceipt: (_) async {
            events.add('saved');
          },
          onAccepted: (count) {
            events.add('accepted:$count');
          },
          checkpoint: () async {
            events.add('checkpoint');
          },
        ),
        throwsA(isA<TimeoutException>()),
      );
      expect(events, ['saved', 'accepted:1']);
      events.clear();
      await expectLater(
        deliverHealthUploads(
          uploads: uploads,
          send: (u) async => UploadReceipt.validate(jsonEncode(receipt(u)), u),
          saveReceipt: (_) async => throw StateError('disk full'),
          onAccepted: (_) {
            events.add('accepted');
          },
          checkpoint: () async {
            events.add('checkpoint');
          },
        ),
        throwsStateError,
      );
      expect(events, isEmpty);
    },
  );

  test(
    'saves receipts before checkpoint, scoped away from another study',
    () async {
      SharedPreferences.setMockInitialValues({});
      final upload = prepare([point()]).single;
      final events = <String>[];
      await deliverHealthUploads(
        uploads: [upload],
        send: (u) async => UploadReceipt.validate(jsonEncode(receipt(u)), u),
        saveReceipt: (r) =>
            StorageService.saveUploadReceipt('tokenA', r.document),
        onAccepted: (_) {
          events.add('accepted');
        },
        checkpoint: () async {
          expect(
            (await StorageService.getUploadReceipts(
              'tokenA',
            )).single['acceptanceId'],
            acceptanceId,
          );
          events.add('checkpoint');
        },
      );
      expect(events, ['accepted', 'checkpoint']);
      expect(await StorageService.getUploadReceipts('tokenB'), isEmpty);
      final collector = await StorageService.getOrCreateCollectorId();
      expect(await StorageService.getOrCreateCollectorId(), collector);
    },
  );

  group('HTTP protocol', () {
    late HttpServer server;
    late HttpClient client;
    late HealthUploader uploader;
    late StreamSubscription<HttpRequest> subscription;
    setUp(() async {
      // Flutter tests normally replace HTTP with a fake 400 client.
      client = HttpOverrides.runWithHttpOverrides(
        () => HttpClient(),
        _RealHttp(),
      );
      server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      uploader = HealthUploader(
        client: client,
        endpoint: Uri.parse('http://127.0.0.1:${server.port}/ingest'),
        delay: (_) async {},
      );
    });
    tearDown(() async {
      client.close(force: true);
      await subscription.cancel();
      await server.close(force: true);
    });

    test(
      'retries a lost acknowledgement with identical bytes and key; reads status',
      () async {
        final upload = prepare([point()]).single;
        final bodies = <List<int>>[];
        final keys = <String?>[];
        subscription = server.listen((request) async {
          expect(request.headers.value('authorization'), 'Bearer secret');
          if (request.method == 'GET') {
            expect(request.uri.path, '/ingest/$acceptanceId');
            request.response.write(
              jsonEncode({
                ...receipt(upload),
                'processingState': 'storage-observed',
              }),
            );
            await request.response.close();
            return;
          }
          bodies.add(
            await request.fold<List<int>>(
              [],
              (bytes, part) => bytes..addAll(part),
            ),
          );
          keys.add(request.headers.value('Idempotency-Key'));
          if (bodies.length == 1) {
            final socket = await request.response.detachSocket(
              writeHeaders: false,
            );
            socket.destroy();
          } else {
            request.response.statusCode = 202;
            request.response.write(jsonEncode(receipt(upload)));
            await request.response.close();
          }
        });
        final accepted = await uploader.send(upload, 'secret');
        expect(accepted.acceptanceId, acceptanceId);
        expect(bodies.length, 2);
        expect(bodies[0], bodies[1]);
        expect(keys, [upload.key, upload.key]);
        expect(
          (await uploader.status(acceptanceId, 'secret'))['processingState'],
          'storage-observed',
        );
      },
    );

    for (final code in [401, 408, 409, 413, 422, 429, 503]) {
      test('HTTP $code never counts as accepted', () async {
        var requests = 0;
        subscription = server.listen((request) async {
          requests++;
          await request.drain<void>();
          request.response.statusCode = code;
          if (code == 429) request.response.headers.set('Retry-After', '3600');
          request.response.write('{}');
          await request.response.close();
        });
        await expectLater(
          uploader.send(prepare([point()]).single, 'token'),
          throwsA(isA<UploadHttpException>()),
        );
        expect(requests, (code == 503 || code == 408) ? 3 : 1);
      });
    }

    test(
      'HTTP 200 produces synthetic receipt when allowLegacy200 is enabled',
      () async {
        subscription = server.listen((request) async {
          await request.drain<void>();
          request.response.statusCode = 200;
          request.response.write('{"status":"ok"}');
          await request.response.close();
        });
        final upload = prepare([point()]).single;
        final receipt = await uploader.send(upload, 'token');
        expect(receipt.readingCount, upload.readingCount);
        expect(receipt.rawSha256, upload.sha256Hex);
        expect(receipt.processingState, 'awaiting-processing');
      },
    );

    test(
      'HTTP 200 throws UploadHttpException when allowLegacy200 is false',
      () async {
        uploader = HealthUploader(
          client: client,
          endpoint: Uri.parse('http://127.0.0.1:${server.port}/ingest'),
          allowLegacy200: false,
        );
        subscription = server.listen((request) async {
          await request.drain<void>();
          request.response.statusCode = 200;
          request.response.write('{"status":"ok"}');
          await request.response.close();
        });
        await expectLater(
          uploader.send(prepare([point()]).single, 'token'),
          throwsA(isA<UploadHttpException>()),
        );
      },
    );

    test('honors short Retry-After before retrying the same upload', () async {
      final waits = <Duration>[];
      uploader = HealthUploader(
        client: client,
        endpoint: Uri.parse('http://127.0.0.1:${server.port}/ingest'),
        delay: (duration) async {
          waits.add(duration);
        },
      );
      final upload = prepare([point()]).single;
      var calls = 0;
      subscription = server.listen((request) async {
        await request.drain<void>();
        if (++calls == 1) {
          request.response.statusCode = 429;
          request.response.headers.set('Retry-After', '3');
        } else {
          request.response.statusCode = 202;
          request.response.write(jsonEncode(receipt(upload)));
        }
        await request.response.close();
      });
      await uploader.send(upload, 'token');
      expect(calls, 2);
      expect(waits, [const Duration(seconds: 3)]);
    });

    test('stalled response bodies time out with bounded retries', () async {
      final upload = prepare([point()]).single;
      uploader = HealthUploader(
        client: client,
        endpoint: Uri.parse('http://127.0.0.1:${server.port}/ingest'),
        timeout: const Duration(milliseconds: 100),
        delay: (_) async {},
      );
      var calls = 0;
      subscription = server.listen((request) async {
        calls++;
        await request.drain<void>();
        request.response.statusCode = 202;
        request.response.write('{');
        await request.response.flush();
        // Leave the response body incomplete to model a stalled connection.
      });
      await expectLater(
        uploader.send(upload, 'token'),
        throwsA(isA<TimeoutException>()),
      );
      expect(calls, 3);
    });

    test('HTTP 202 with malformed receipt is not success', () async {
      subscription = server.listen((request) async {
        await request.drain<void>();
        request.response.statusCode = 202;
        request.response.write('{}');
        await request.response.close();
      });
      await expectLater(
        uploader.send(prepare([point()]).single, 'token'),
        throwsFormatException,
      );
    });
  });
}

class _RealHttp extends HttpOverrides {}
