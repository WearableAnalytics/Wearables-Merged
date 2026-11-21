import 'dart:convert';

import 'package:charite_wearables/screens/polar_history_page.dart';
import 'package:charite_wearables/services/polar_recording.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
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
  for (final platform in ['ios', 'android']) {
    test(
      '$platform capture uses importer units and separate source/collector identities',
      () {
        final time = DateTime.utc(2026, 11, 21);
        final upload = polarUpload(
          samples: [
            (time: time, bpm: 75),
            (time: time.add(const Duration(seconds: 1)), bpm: 76),
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
