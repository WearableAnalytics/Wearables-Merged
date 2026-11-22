import 'health_upload.dart';

bool isPolarAdvertisement(String? name, Iterable<int> companyIds) =>
    (name ?? '').trimLeft().toLowerCase().startsWith('polar') ||
    companyIds.contains(0x006b);

/// Bluetooth SIG Heart Rate Measurement (0x2A37). Ignore packets with lost
/// sensor contact, invalid trailing fields, or no measured rate.
int? polarHeartRate(List<int> bytes) {
  if (bytes.length < 2) return null;
  final flags = bytes.first;
  if (flags & 0xe0 != 0 || flags & 6 == 4) return null;
  final wide = flags & 1 != 0;
  final length = (wide ? 3 : 2) + (flags & 8 != 0 ? 2 : 0);
  final remaining = bytes.length - length;
  if (remaining < 0 ||
      (flags & 16 == 0 ? remaining != 0 : remaining < 2 || remaining.isOdd)) {
    return null;
  }
  final bpm = bytes[1] + (wide ? bytes[2] << 8 : 0);
  return bpm == 0 ? null : bpm;
}

enum PolarMetric {
  heartRate('Heart rate', 'HEART_RATE', 'BEATS_PER_MINUTE', 'bpm'),
  skinTemperature('Skin temperature', 'SKIN_TEMPERATURE', 'Cel', '°C'),
  pulseInterval('Pulse interval', 'PULSE_TO_PULSE_INTERVAL', 'ms', 'ms'),
  steps('Steps', 'STEPS', '1', 'steps', 'cumulative'),
  activityDistance(
    'Activity distance',
    'DISTANCE_DELTA',
    'm',
    'm',
    'cumulative',
  ),
  activityEnergy(
    'Activity energy',
    'ACTIVE_ENERGY_BURNED',
    'kcal',
    'kcal',
    'cumulative',
  ),
  basalEnergy(
    'Basal energy',
    'BASAL_ENERGY_BURNED',
    'kcal',
    'kcal',
    'cumulative',
  ),
  activityMet(
    'Activity intensity (MET)',
    'POLAR_ACTIVITY_MET',
    '1',
    'MET',
    'cumulative',
  ),
  workoutTime(
    'Workout elapsed time',
    'WORKOUT_ELAPSED_TIME',
    'min',
    'min',
    'duration',
  ),
  workoutEnergy(
    'Workout energy',
    'POLAR_WORKOUT_ENERGY',
    'kcal',
    'kcal',
    'cumulative',
  ),
  sleepAsleep('Time asleep', 'SLEEP_ASLEEP', 'min', 'min', 'duration'),
  sleepLight('Light sleep', 'SLEEP_LIGHT', 'min', 'min', 'duration'),
  sleepDeep('Deep sleep', 'SLEEP_DEEP', 'min', 'min', 'duration'),
  sleepRem('REM sleep', 'SLEEP_REM', 'min', 'min', 'duration'),
  sleepAwake('Awake during sleep', 'SLEEP_AWAKE', 'min', 'min', 'duration'),
  nightlyHrv(
    'Nightly mean HRV (RMSSD)',
    'POLAR_NIGHTLY_MEAN_RMSSD',
    'ms',
    'ms',
  ),
  nightlyBreathing(
    'Nightly breathing rate',
    'RESPIRATORY_RATE',
    '/min',
    '/min',
  );

  static const live = [heartRate, skinTemperature, pulseInterval];
  static const sleepStages = [
    sleepLight,
    sleepDeep,
    sleepRem,
    sleepAwake,
    sleepAsleep,
  ];
  static const dailyTotals = [activityDistance, activityEnergy, basalEnergy];

  const PolarMetric(
    this.label,
    this.type,
    this.unit,
    this.displayUnit, [
    this.group = 'instantaneous',
  ]);
  final String label, type, unit, displayUnit, group;
}

typedef PolarSample = ({num value, DateTime time});

HealthUpload polarUpload({
  required List<PolarSample> samples,
  PolarMetric metric = PolarMetric.heartRate,
  required String device,
  required String name,
  required String collector,
  required String platform,
}) {
  final key = newUploadKey();
  final source = (id: 'polar-ble', platform: 'bluetooth-le', name: name);
  final start = samples.first.time.toUtc().toIso8601String();
  final end = samples.last.time.toUtc().toIso8601String();
  return HealthUpload(
    {
      ...source.toLegacyMetadata(),
      'contractVersion': 'wearables-numeric/1',
      'deviceInfo': {'deviceId': collector, 'platform': platform},
      'batchInfo': {
        'batchId': key,
        'dataPointCount': samples.length,
        'collectionStart': start,
        'collectionEnd': end,
      },
      'timestamp': end,
      'measurements': {
        'instantaneous': [
          for (var i = 0; i < samples.length; i++)
            {
              'type': metric.type,
              'unit': metric.unit,
              'value': samples[i].value,
              'timestamp': samples[i].time.toUtc().toIso8601String(),
              // Live notifications have no persistent provider record ID. Retries reuse this capture.
              'sourceRecordId': '$key-$i', 'sourceDeviceId': device,
            },
        ],
        'cumulative': [],
        'duration': [],
      },
    },
    key,
    samples.length,
    source: source,
  );
}
