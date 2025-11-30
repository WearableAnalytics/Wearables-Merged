import 'package:health/health.dart';

Map<String, dynamic> formatHealthDataByType(List<HealthDataPoint> healthData) {
  Map<String, List<Map<String, dynamic>>> categorizedData = {
    'instantaneous': [],
    'cumulative': [],
    'duration': [],
  };

  for (var data in healthData) {
    String category = categorizeHealthDataType(data.type);
    Map<String, dynamic> formattedPoint = {};

    switch (category) {
      case 'instantaneous':
        formattedPoint = {
          'type': data.type.toString().replaceAll('HealthDataType.', ''),
          'value': parseValue(data.value),
          'unit': data.unit.toString().replaceAll('HealthDataUnit.', ''),
          'timestamp': data.dateFrom.toIso8601String(),
        };
        break;

      case 'cumulative':
        formattedPoint = {
          'type': data.type.toString().replaceAll('HealthDataType.', ''),
          'value': parseValue(data.value),
          'unit': data.unit.toString().replaceAll('HealthDataUnit.', ''),
          'periodStart': data.dateFrom.toIso8601String(),
          'periodEnd': data.dateTo.toIso8601String(),
          'duration': data.dateTo.difference(data.dateFrom).inSeconds,
        };
        break;

      case 'duration':
        formattedPoint = {
          'type': data.type.toString().replaceAll('HealthDataType.', ''),
          'value': parseValue(data.value),
          'unit': data.unit.toString().replaceAll('HealthDataUnit.', ''),
          'startTime': data.dateFrom.toIso8601String(),
          'endTime': data.dateTo.toIso8601String(),
          'durationMinutes': data.dateTo.difference(data.dateFrom).inMinutes,
        };
        break;
    }

    categorizedData[category]!.add(formattedPoint);
  }

  return categorizedData;
}

String categorizeHealthDataType(HealthDataType type) {
  switch (type) {
    // Instantaneous - point-in-time measurements
    case HealthDataType.HEART_RATE:
    case HealthDataType.RESTING_HEART_RATE:
    case HealthDataType.WALKING_HEART_RATE:
    case HealthDataType.HEART_RATE_VARIABILITY_SDNN:
    case HealthDataType.HIGH_HEART_RATE_EVENT:
    case HealthDataType.IRREGULAR_HEART_RATE_EVENT:
    case HealthDataType.LOW_HEART_RATE_EVENT:
    case HealthDataType.BLOOD_OXYGEN:
    case HealthDataType.BLOOD_PRESSURE_SYSTOLIC:
    case HealthDataType.BLOOD_PRESSURE_DIASTOLIC:
    case HealthDataType.BLOOD_GLUCOSE:
    case HealthDataType.BODY_TEMPERATURE:
    case HealthDataType.RESPIRATORY_RATE:
    case HealthDataType.PERIPHERAL_PERFUSION_INDEX:
    case HealthDataType.ELECTRODERMAL_ACTIVITY:
    case HealthDataType.WEIGHT:
    case HealthDataType.HEIGHT:
    case HealthDataType.BODY_FAT_PERCENTAGE:
    case HealthDataType.BODY_MASS_INDEX:
    case HealthDataType.WAIST_CIRCUMFERENCE:
    case HealthDataType.FORCED_EXPIRATORY_VOLUME:
    case HealthDataType.AUDIOGRAM:
    case HealthDataType.ELECTROCARDIOGRAM:
    case HealthDataType.HEADACHE_NOT_PRESENT:
    case HealthDataType.HEADACHE_MILD:
    case HealthDataType.HEADACHE_MODERATE:
    case HealthDataType.HEADACHE_SEVERE:
    case HealthDataType.HEADACHE_UNSPECIFIED:
      return 'instantaneous';

    // Cumulative - total count/amount over time
    case HealthDataType.STEPS:
    case HealthDataType.DISTANCE_WALKING_RUNNING:
    case HealthDataType.DISTANCE_SWIMMING:
    case HealthDataType.DISTANCE_CYCLING:
    case HealthDataType.FLIGHTS_CLIMBED:
    case HealthDataType.ACTIVE_ENERGY_BURNED:
    case HealthDataType.BASAL_ENERGY_BURNED:
    case HealthDataType.DIETARY_CARBS_CONSUMED:
    case HealthDataType.DIETARY_CAFFEINE:
    case HealthDataType.DIETARY_ENERGY_CONSUMED:
    case HealthDataType.DIETARY_FATS_CONSUMED:
    case HealthDataType.DIETARY_PROTEIN_CONSUMED:
    case HealthDataType.WATER:
    case HealthDataType.NUTRITION:
      return 'cumulative';

    // Duration - time-based activities/states
    case HealthDataType.SLEEP_IN_BED:
    case HealthDataType.SLEEP_ASLEEP:
    case HealthDataType.SLEEP_AWAKE:
    case HealthDataType.SLEEP_DEEP:
    case HealthDataType.SLEEP_LIGHT:
    case HealthDataType.SLEEP_REM:
    case HealthDataType.SLEEP_ASLEEP_CORE:
    case HealthDataType.SLEEP_ASLEEP_DEEP:
    case HealthDataType.SLEEP_ASLEEP_REM:
    case HealthDataType.WORKOUT:
    case HealthDataType.EXERCISE_TIME:
    case HealthDataType.MINDFULNESS:
      return 'duration';

    default:
      return 'instantaneous';
  }
}

dynamic parseValue(dynamic value) {
  try {
    if (value != null) {
      try {
        final numericValue = (value as dynamic).numericValue;
        if (numericValue != null) {
          return numericValue is double &&
                  numericValue == numericValue.roundToDouble()
              ? numericValue.round()
              : numericValue;
        }
      } catch (_) { }

      try {
        final val = (value as dynamic).value;
        if (val != null && val is num) {
          return val is double && val == val.roundToDouble()
              ? val.round()
              : val;
        }
      } catch (_) { }
    }
  } catch (_) { }
  if (value is String) {
    final doubleValue = double.tryParse(value);
    if (doubleValue != null) {
      return doubleValue == doubleValue.roundToDouble()
          ? doubleValue.round()
          : doubleValue;
    }
  }
  if (value is num) {
    return value is double && value == value.roundToDouble()
        ? value.round()
        : value;
  }
  if (value != null) {
    final valueStr = value.toString();
    final regex = RegExp(r'numeric_value[\":\s]*([0-9]+\.?[0-9]*)');
    final match = regex.firstMatch(valueStr);
    if (match != null) {
      final numericStr = match.group(1);
      if (numericStr != null) {
        try {
          final doubleValue = double.parse(numericStr);
          return doubleValue == doubleValue.roundToDouble()
              ? doubleValue.round()
              : doubleValue;
        } catch (e) {
          // Return original value if parsing fails
        }
      }
    }
  }

  return value;
}
