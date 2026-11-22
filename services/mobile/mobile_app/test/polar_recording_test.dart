import 'dart:convert';
import 'dart:typed_data';

import 'package:charite_wearables/services/polar_pmd.dart';

import 'package:charite_wearables/screens/polar_history_page.dart';
import 'package:charite_wearables/services/polar_recording.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('recognizes the Polar company ID when the device omits its name', () {
    expect(isPolarAdvertisement(null, [0x006b]), isTrue);
    expect(isPolarAdvertisement('Polar 360', []), isTrue);
    expect(isPolarAdvertisement(null, [0x004c]), isFalse);
    expect(isPolarAdvertisement('Other sensor', []), isFalse);
  });
  testWidgets('history requires a category and authorization before sharing', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1000, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      const MaterialApp(home: PolarHistoryPage(token: 'fixture')),
    );
    final authorize = find.widgetWithText(
      FilledButton,
      'Authorize in Polar Flow',
    );
    final pulse = find.widgetWithText(
      CheckboxListTile,
      'Continuous heart rate',
    );
    expect(find.byType(CheckboxListTile), findsNWidgets(8));
    expect(tester.widget<FilledButton>(authorize).onPressed, isNull);
    await tester.tap(pulse);
    await tester.pump();
    expect(tester.widget<FilledButton>(authorize).onPressed, isNotNull);
    expect(find.textContaining('Share with'), findsNothing);
    await tester.tap(pulse);
    await tester.pump();
    expect(tester.widget<FilledButton>(authorize).onPressed, isNull);
  });
  test(
    'reads standard 8/16-bit heart rate and optional energy and RR fields',
    () {
      expect(polarHeartRate([6, 72]), 72);
      expect(polarHeartRate([1, 4, 1]), 260);
      expect(polarHeartRate([30, 75, 1, 0, 0, 4]), 75);
      for (final packet in <List<int>>[
        [],
        [1, 75],
        [4, 72],
        [0, 0],
        [8, 76],
        [16, 76, 1],
        [0, 72, 0],
      ]) {
        expect(polarHeartRate(packet), isNull);
      }
    },
  );
  test(
    'skin temperature preserves Celsius, sensor time and compressed deltas',
    () {
      final received = DateTime.utc(2026, 11, 22);
      final raw = ByteData(18)
        ..setUint8(0, 7)
        ..setUint64(1, 2000000000, Endian.little)
        ..setFloat32(10, 32.5, Endian.little)
        ..setFloat32(14, 32.75, Endian.little);
      final values = decodePolarFrame(
        raw.buffer.asUint8List(),
        7,
        received,
        sampleHz: 1,
      );
      expect(values.map((s) => s.value), [32.5, 32.75]);
      expect(values.first.time, DateTime.utc(2000, 1, 1, 0, 0, 1));
      final delta = Uint8List.fromList([
        ...raw.buffer.asUint8List(0, 14),
        2,
        2,
        13,
      ])..[9] = 128;
      final compressed = decodePolarFrame(delta, 7, received, sampleHz: 1);
      expect(compressed.length, 3);
      expect(compressed[1].value, greaterThan(32.5));
      expect(compressed.last.value, 32.5);
      expect(
        () => decodePolarFrame(delta.sublist(0, 16), 7, received, sampleHz: 1),
        throwsFormatException,
      );
    },
  );
  test(
    'PPI excludes blocked samples and poor contact while preserving elapsed beat time',
    () {
      final received = DateTime.utc(2026, 11, 22);
      final bytes = Uint8List.fromList([
        3,
        ...List.filled(9, 0),
        70,
        32,
        3,
        2,
        0,
        6,
        70,
        32,
        3,
        2,
        0,
        7,
        70,
        32,
        3,
        2,
        0,
        4,
        70,
        32,
        3,
        2,
        0,
        6,
      ]);
      final points = decodePolarFrame(bytes, 3, received, sampleHz: 1);
      expect(points.map((p) => p.value), [800, 800]);
      expect(
        points.first.time,
        received.subtract(const Duration(milliseconds: 2400)),
      );
      expect(points.last.time, received);
      for (final metric in [
        PolarMetric.skinTemperature,
        PolarMetric.pulseInterval,
      ]) {
        final batch = polarUpload(
          samples: [
            (
              value: metric == PolarMetric.skinTemperature ? 32.5 : 800,
              time: received,
            ),
          ],
          metric: metric,
          device: 'sensor',
          name: 'Polar 360',
          collector: 'phone',
          platform: 'ios',
        );
        final row = jsonDecode(
          utf8.decode(batch.bytes),
        )['measurements']['instantaneous'].single;
        expect(row['type'], metric.type);
        expect(row['unit'], metric.unit);
        expect(row['sourceDeviceId'], 'sensor');
      }
    },
  );
  for (final platform in ['ios', 'android']) {
    test(
      '$platform capture uses importer units and separate source/collector identities',
      () {
        final time = DateTime.utc(2026, 11, 21);
        final upload = polarUpload(
          samples: [
            (time: time, value: 75),
            (time: time.add(const Duration(seconds: 1)), value: 76),
          ],
          device: 'demo-device',
          name: 'Polar 360',
          collector: 'test-phone',
          platform: platform,
        );
        final payload = jsonDecode(utf8.decode(upload.bytes));
        expect(payload['sourcePlatform'], 'bluetooth-le');
        expect(payload['contractVersion'], 'wearables-numeric/1');
        expect(payload['deviceInfo'], {
          'deviceId': 'test-phone',
          'platform': platform,
        });
        final readings = payload['measurements']['instantaneous'] as List;
        expect(readings.first['unit'], 'BEATS_PER_MINUTE');
        expect(readings.first['timestamp'], time.toIso8601String());
        expect(readings.first['sourceDeviceId'], 'demo-device');
        expect(readings.map((r) => r['sourceRecordId']).toSet().length, 2);
        expect(upload.readingCount, readings.length);
        expect(upload.key, payload['batchInfo']['batchId']);
      },
    );
  }
}
