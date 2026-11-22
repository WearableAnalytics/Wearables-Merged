import 'dart:convert';
import 'dart:typed_data';
import 'package:charite_wearables/services/polar_band_samples.dart';
import 'package:charite_wearables/services/polar_band_sync.dart';
import 'package:charite_wearables/services/polar_recording.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:crypto/crypto.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:charite_wearables/storage_service.dart';

// Small protobuf fixtures from the field definitions published in Polar's
// automatic_samples, ppi_samples and temperature_measurement_period schemas.
List<int> varint(int n) {
  final bytes = <int>[];
  while (n >= 128) {
    bytes.add(128 | (n & 127));
    n >>= 7;
  }
  return [...bytes, n];
}

List<int> number(int tag, int value) => [tag << 3, ...varint(value)];
List<int> nested(int tag, List<int> bytes) => [
  tag << 3 | 2,
  ...varint(bytes.length),
  ...bytes,
];
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'a replacement study cannot inherit or silently restore Polar sharing',
    () async {
      SharedPreferencesAsyncPlatform.instance =
          InMemorySharedPreferencesAsync.empty();
      const old = 'a.e30.a', replacement = 'b.e30.b';
      SharedPreferences.setMockInitialValues({'device_id': old});
      final db = SharedPreferencesAsync();
      final cfg = jsonEncode({
        'id': 'test-grant',
        'owner': sha256.convert(utf8.encode(old)).toString(),
      });
      await db.setString(PolarBandSync.grantKey, cfg);
      expect(await PolarBandSync.grant(old), cfg);
      expect(await PolarBandSync.grant(replacement), isNull);
      await StorageService.setCustomDeviceId(replacement);
      await StorageService.setCustomDeviceId(old);
      expect(await PolarBandSync.grant(old), isNull);
    },
  );
  final day = DateTime(2026, 11, 22);
  final calendar = [...number(1, 2026), ...number(2, 11), ...number(3, 22)];
  final clock = [...number(1, 12), ...number(2, 5), ...number(3, 0)];
  final samples = [
    ...nested(1, calendar),
    ...nested(2, [
      ...number(1, 1),
      ...nested(2, clock),
      ...nested(3, [70, 71]),
    ]),
    ...nested(3, [
      ...nested(2, clock),
      ...nested(3, [
        ...nested(1, [...varint(1600), ...varint(19), ...varint(10)]),
        ...nested(3, [1, 3, 1]),
      ]),
    ]),
  ];
  test(
    'decode stored pulse, quality flags, signed deltas and sample times',
    () {
      final rows = polarAutomaticSamples(samples).toList();
      expect(rows.map((r) => r.value), [70, 71, 800, 795]);
      expect(rows[1].time.difference(rows[0].time).inSeconds, 1);
      expect(rows[3].time.difference(rows[2].time).inMilliseconds, 1590);
      expect(rows.map((r) => r.id).toSet(), hasLength(4));
    },
  );
  test('temperature requires skin and uses a day-relative offset', () {
    final temp = (ByteData(
      4,
    )..setFloat32(0, 31.25, Endian.little)).buffer.asUint8List();
    final reading = nested(4, [...number(1, 60000), 21, ...temp]);
    final rows = polarTemperatureSamples(day, [...number(1, 1), ...reading]);
    expect(rows.single.time, day.add(const Duration(minutes: 1)).toUtc());
    expect(rows.single.value, 31.25);
    expect(
      polarTemperatureSamples(day, [...number(1, 2), ...reading]),
      isEmpty,
    );
  });
  test(
    'consent start, end, selected metric, exact retry and source binding',
    () {
      final rows = polarAutomaticSamples(samples).toList();
      final start = rows[1].time;
      List uploads(String device) => bandUploads(
        rows,
        device: device,
        collector: 'phone',
        platform: 'ios',
        metrics: {PolarMetric.heartRate},
        since: start,
        until: start,
      ).toList();
      final a = uploads('band-a').single,
          same = uploads('band-a').single,
          b = uploads('band-b').single;
      expect(a.readingCount, 1);
      expect(a.key, same.key);
      expect(a.bytes, same.bytes);
      final doc = jsonDecode(utf8.decode(a.bytes));
      expect(doc['measurements']['instantaneous'].single['value'], 71);
      expect(a.key, isNot(b.key));
    },
  );
  test(
    'growing and replaced band files only skip a confirmed, identical prefix',
    () {
      final rows = polarAutomaticSamples(samples).toList();
      final marker = '2/${bandPrefix(rows.take(2))}';
      expect(confirmedBandPrefix(rows, marker), 2);
      expect(confirmedBandPrefix(rows.reversed.toList(), marker), 0);
      expect(confirmedBandPrefix(rows.take(1).toList(), marker), 0);
      expect(confirmedBandPrefix(rows, null), 0);
    },
  );
}
