import 'package:flutter_test/flutter_test.dart';
import 'package:health/health.dart';

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
