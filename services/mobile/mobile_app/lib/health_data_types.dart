import 'package:health/health.dart';

/// Returns a permissions list matching `types.length` where each entry is
/// `HealthDataAccess.READ_WRITE`. The `health` plugin expects a permissions
/// list that aligns 1:1 with the requested types when provided.
List<HealthDataAccess> permissionsFor(List<HealthDataType> types) {
  return List.filled(types.length, HealthDataAccess.READ);
}

final List<HealthDataType> allRequestedHealthDataTypes = [
  //IOS DATA TYPES
  HealthDataType.ACTIVE_ENERGY_BURNED,
  HealthDataType.AUDIOGRAM,
  HealthDataType.BASAL_ENERGY_BURNED,
  HealthDataType.BLOOD_GLUCOSE,
  HealthDataType.BLOOD_OXYGEN,
  HealthDataType.BLOOD_PRESSURE_DIASTOLIC,
  HealthDataType.BLOOD_PRESSURE_SYSTOLIC,
  HealthDataType.BODY_FAT_PERCENTAGE,
  HealthDataType.BODY_MASS_INDEX,
  HealthDataType.BODY_TEMPERATURE,
  HealthDataType.DIETARY_CARBS_CONSUMED,
  HealthDataType.DIETARY_CAFFEINE,
  HealthDataType.DIETARY_ENERGY_CONSUMED,
  HealthDataType.DIETARY_FATS_CONSUMED,
  HealthDataType.DIETARY_PROTEIN_CONSUMED,
  HealthDataType.ELECTRODERMAL_ACTIVITY,
  HealthDataType.FORCED_EXPIRATORY_VOLUME,
  HealthDataType.HEART_RATE,
  HealthDataType.HEART_RATE_VARIABILITY_SDNN,
  HealthDataType.HEIGHT,
  HealthDataType.HIGH_HEART_RATE_EVENT,
  HealthDataType.IRREGULAR_HEART_RATE_EVENT,
  HealthDataType.LOW_HEART_RATE_EVENT,
  HealthDataType.RESTING_HEART_RATE,
  HealthDataType.RESPIRATORY_RATE,
  HealthDataType.PERIPHERAL_PERFUSION_INDEX,
  HealthDataType.STEPS,
  HealthDataType.WAIST_CIRCUMFERENCE,
  HealthDataType.WALKING_HEART_RATE,
  HealthDataType.WEIGHT,
  HealthDataType.FLIGHTS_CLIMBED,
  HealthDataType.DISTANCE_WALKING_RUNNING,
  HealthDataType.DISTANCE_SWIMMING,
  HealthDataType.DISTANCE_CYCLING,
  HealthDataType.MINDFULNESS,
  HealthDataType.SLEEP_IN_BED,
  HealthDataType.SLEEP_AWAKE,
  HealthDataType.SLEEP_ASLEEP,
  HealthDataType.SLEEP_DEEP,
  HealthDataType.SLEEP_REM,
  HealthDataType.SLEEP_ASLEEP_CORE,
  HealthDataType.SLEEP_ASLEEP_DEEP,
  HealthDataType.SLEEP_ASLEEP_REM,
  HealthDataType.WATER,
  HealthDataType.EXERCISE_TIME,
  HealthDataType.WORKOUT,
  HealthDataType.HEADACHE_NOT_PRESENT,
  HealthDataType.HEADACHE_MILD,
  HealthDataType.HEADACHE_MODERATE,
  HealthDataType.HEADACHE_SEVERE,
  HealthDataType.HEADACHE_UNSPECIFIED,
  HealthDataType.ELECTROCARDIOGRAM,
  HealthDataType.NUTRITION,


  // // Cumulative - total count over time
  // HealthDataType.STEPS,
  // HealthDataType.ACTIVE_ENERGY_BURNED,
  
  // // Instantaneous - point-in-time measurements
  // HealthDataType.HEART_RATE,
  // HealthDataType.RESTING_HEART_RATE,
  // // HealthDataType.BLOOD_PRESSURE_SYSTOLIC, 
  // // HealthDataType.BLOOD_PRESSURE_DIASTOLIC, 
  // HealthDataType.BLOOD_OXYGEN,
  // HealthDataType.RESPIRATORY_RATE,
  // HealthDataType.BODY_TEMPERATURE,
  // HealthDataType.WEIGHT,
  // // HealthDataType.BLOOD_GLUCOSE,
  // HealthDataType.BODY_FAT_PERCENTAGE,
  // HealthDataType.BODY_MASS_INDEX,
  
  // // Duration - time-based measurements
  // HealthDataType.SLEEP_ASLEEP,
  // HealthDataType.SLEEP_DEEP,
  // HealthDataType.SLEEP_REM,
  // HealthDataType.WORKOUT,
];
