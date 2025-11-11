import 'package:health/health.dart';

/// Returns a permissions list matching `types.length` where each entry is
/// `HealthDataAccess.READ_WRITE`. The `health` plugin expects a permissions
/// list that aligns 1:1 with the requested types when provided.
List<HealthDataAccess> permissionsFor(List<HealthDataType> types) {
  return List.filled(types.length, HealthDataAccess.READ);
}

final List<HealthDataType> allRequestedHealthDataTypes = [
  HealthDataType.STEPS,
  HealthDataType.ACTIVE_ENERGY_BURNED,
  HealthDataType.HEART_RATE,
  HealthDataType.RESTING_HEART_RATE,
  HealthDataType.BLOOD_PRESSURE_SYSTOLIC,
  HealthDataType.BLOOD_PRESSURE_DIASTOLIC,
  HealthDataType.BLOOD_OXYGEN,
  HealthDataType.RESPIRATORY_RATE,
  HealthDataType.BODY_TEMPERATURE,
  HealthDataType.WEIGHT,
  HealthDataType.BLOOD_GLUCOSE,
  HealthDataType.SLEEP_ASLEEP,
  HealthDataType.SLEEP_DEEP,
  HealthDataType.SLEEP_REM,
  HealthDataType.BODY_FAT_PERCENTAGE,
  HealthDataType.BODY_MASS_INDEX,
  HealthDataType.WORKOUT,
];
