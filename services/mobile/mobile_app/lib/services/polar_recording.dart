import 'health_upload.dart';

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

typedef PolarSample = ({int bpm, DateTime time});

HealthUpload polarUpload({
  required List<PolarSample> samples,
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
              'type': 'HEART_RATE',
              'unit': 'BEATS_PER_MINUTE',
              'value': samples[i].bpm,
              'timestamp': samples[i].time.toUtc().toIso8601String(),
              // HRS has no native sample identifier or clock. Identity is scoped
              // to this capture, and timestamps are phone reception times.
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
