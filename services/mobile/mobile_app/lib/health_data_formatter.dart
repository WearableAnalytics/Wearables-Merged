import 'package:health/health.dart';

/// Shared helpers for turning raw `HealthDataPoint` values from the
/// `health` plugin into the JSON structure your backend expects.
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
          'value': parseDurationValue(data),
          'unit': data.unit.toString().replaceAll('HealthDataUnit.', ''),
          'startTime': data.dateFrom.toIso8601String(),
          'endTime': data.dateTo.toIso8601String(),
          'durationMinutes': data.dateTo.difference(data.dateFrom).inMinutes,
        };

        // Provide rich metadata for workouts when available.
        if (data.type == HealthDataType.WORKOUT) {
          var workoutDetails = extractWorkoutDetails(data.value);
          if (workoutDetails != null) {
            formattedPoint.addAll(workoutDetails);
          }
        }
        break;
    }

    // The ingest API only accepts finite numbers. Types such as audiograms
    // carry structured values; leave those out so one point cannot get a
    // whole batch rejected (HTTP 422).
    final value = formattedPoint['value'];
    if (value is! num || value.isNaN || value.isInfinite) continue;

    categorizedData[category]!.add(formattedPoint);
  }

  return categorizedData;
}

String categorizeHealthDataType(HealthDataType type) {
  switch (type) {
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

    case HealthDataType.SLEEP_IN_BED:
    case HealthDataType.SLEEP_ASLEEP:
    case HealthDataType.SLEEP_AWAKE:
    case HealthDataType.SLEEP_DEEP:
    case HealthDataType.SLEEP_LIGHT:
    case HealthDataType.SLEEP_REM:
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
      } catch (_) {}

      try {
        final val = (value as dynamic).value;
        if (val != null && val is num) {
          return val is double && val == val.roundToDouble()
              ? val.round()
              : val;
        }
      } catch (_) {}
    }
  } catch (_) {}
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

double parseDurationValue(HealthDataPoint data) {
  return data.dateTo.difference(data.dateFrom).inMinutes.toDouble();
}

Map<String, dynamic>? extractWorkoutDetails(dynamic value) {
  if (value == null) return null;

  try {
    final valueStr = value.toString();

    final activityRegex = RegExp(r'workout_activity_type[\":\s]*([A-Z_]+)');
    final activityMatch = activityRegex.firstMatch(valueStr);

    final energyRegex = RegExp(r'total_energy_burned[\":\s]*([0-9]+\.?[0-9]*)');
    final energyMatch = energyRegex.firstMatch(valueStr);

    final distanceRegex = RegExp(r'total_distance[\":\s]*([0-9]+\.?[0-9]*)');
    final distanceMatch = distanceRegex.firstMatch(valueStr);

    final energyUnitRegex = RegExp(r'total_energy_burned_unit[\":\s]*([A-Z]+)');
    final energyUnitMatch = energyUnitRegex.firstMatch(valueStr);

    final distanceUnitRegex = RegExp(r'total_distance_unit[\":\s]*([A-Z]+)');
    final distanceUnitMatch = distanceUnitRegex.firstMatch(valueStr);

    Map<String, dynamic> details = {};

    if (activityMatch != null) {
      details['workoutActivityType'] = activityMatch.group(1);
    }

    if (energyMatch != null) {
      final energyValue = double.tryParse(energyMatch.group(1) ?? '');
      if (energyValue != null) {
        details['totalEnergyBurned'] = energyValue;
      }
    }

    if (distanceMatch != null) {
      final distanceValue = double.tryParse(distanceMatch.group(1) ?? '');
      if (distanceValue != null) {
        details['totalDistance'] = distanceValue;
      }
    }

    if (energyUnitMatch != null) {
      details['totalEnergyBurnedUnit'] = energyUnitMatch.group(1);
    }

    if (distanceUnitMatch != null) {
      details['totalDistanceUnit'] = distanceUnitMatch.group(1);
    }

    return details.isNotEmpty ? details : null;
  } catch (e) {
    return null;
  }
}
