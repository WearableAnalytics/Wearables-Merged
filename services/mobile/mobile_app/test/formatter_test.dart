import 'package:flutter_test/flutter_test.dart';
import 'package:health/health.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import 'package:charite_wearables/health_data_formatter.dart';

HealthDataPoint _point(HealthDataType type, HealthValue value) {
  final t = DateTime(2026, 1, 1, 8);
  return HealthDataPoint(
    uuid: 'x',
    value: value,
    type: type,
    unit: HealthDataUnit.COUNT,
    dateFrom: t,
    dateTo: t.add(const Duration(minutes: 1)),
    sourcePlatform: HealthPlatformType.appleHealth,
    sourceDeviceId: 'd',
    sourceId: 's',
    sourceName: 'n',
  );
}

void main() {
  test(
    'all categories preserve instants, endpoints and microseconds across DST and travel',
    () {
      tzdata.initializeTimeZones();
      final instants = [
        '2026-11-03T10:00:00.123456+01:00',
        '2026-07-03T10:00:00.123456+02:00',
        '2026-10-25T02:30:00.123456+02:00',
        '2026-10-25T02:30:00.123456+01:00',
        '2026-03-29T01:59:59.123456+01:00',
        '2026-03-29T03:00:00.123456+02:00',
      ];
      for (final zone in ['UTC', 'Europe/Berlin', 'America/New_York']) {
        for (final text in instants) {
          final instant = DateTime.parse(text);
          final start = tz.TZDateTime.from(instant, tz.getLocation(zone));
          final end = start.add(const Duration(seconds: 90, microseconds: 123));
          for (final type in [
            HealthDataType.HEART_RATE,
            HealthDataType.STEPS,
            HealthDataType.SLEEP_DEEP,
          ]) {
            final original = _point(type, NumericHealthValue(numericValue: 61));
            final point = HealthDataPoint(
              uuid: original.uuid,
              value: original.value,
              type: type,
              unit: original.unit,
              dateFrom: start,
              dateTo: end,
              sourcePlatform: original.sourcePlatform,
              sourceDeviceId: original.sourceDeviceId,
              sourceId: original.sourceId,
              sourceName: original.sourceName,
            );
            final category = categorizeHealthDataType(type);
            final formatted =
                (formatHealthDataByType([point])[category] as List).single
                    as Map;
            final startKey = category == 'instantaneous'
                ? 'timestamp'
                : category == 'cumulative'
                ? 'periodStart'
                : 'startTime';
            expect(formatted[startKey], instant.toUtc().toIso8601String());
            if (category != 'instantaneous') {
              final endKey = category == 'cumulative' ? 'periodEnd' : 'endTime';
              expect(formatted[endKey], end.toUtc().toIso8601String());
            }
          }
        }
      }
    },
  );

  test('only finite numeric values reach the upload payload', () {
    final formatted = formatHealthDataByType([
      _point(HealthDataType.HEART_RATE, NumericHealthValue(numericValue: 61)),
      _point(
        HealthDataType.AUDIOGRAM,
        AudiogramHealthValue(
          frequencies: [1000],
          leftEarSensitivities: [20],
          rightEarSensitivities: [25],
        ),
      ),
    ]);
    final values = [
      for (final list in formatted.values)
        for (final point in list as List) point['value'],
    ];
    expect(values, [61]);
  });
}
