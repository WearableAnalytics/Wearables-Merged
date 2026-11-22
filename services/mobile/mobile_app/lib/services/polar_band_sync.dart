import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../storage_service.dart';
import 'health_sync_service.dart';
import 'health_upload.dart';
import 'polar_band_samples.dart';
import 'polar_files.dart';
import 'polar_setup.dart';
import 'polar_recording.dart';

String _digest(String value) => sha256.convert(utf8.encode(value)).toString();

List<BandReading> eligibleBandRows(
  Iterable<BandReading> rows,
  Set<PolarMetric> metrics,
  DateTime since,
  DateTime until,
) {
  return rows
      .where(
        (r) =>
            metrics.contains(r.metric) &&
            !r.time.isBefore(since) &&
            !(r.end ?? r.time).isAfter(until),
      )
      .toList()
    ..sort((a, b) {
      final cmp = a.time.compareTo(b.time);
      return cmp != 0 ? cmp : a.id.compareTo(b.id);
    });
}

/// A file may grow, be rewritten, or be reused by the band. Skip an acknowledged
/// prefix only if its contents still match. Changed readings go to the importer's
/// existing conflict checks. Persist only the count and the fingerprint.
String bandPrefix(Iterable<BandReading> rows, [String digest = '']) {
  for (final r in rows) {
    digest = _digest(
      jsonEncode([
        digest,
        r.id,
        r.time.microsecondsSinceEpoch,
        r.metric.name,
        r.value,
        if (r.end != null) r.end!.microsecondsSinceEpoch,
      ]),
    );
  }
  return digest;
}

int confirmedBandPrefix(List<BandReading> rows, String? marker) {
  if (marker == null) return 0;
  final parts = marker.split('/');
  final count = int.tryParse(parts.first) ?? 0;
  if (parts.length != 2 || count < 1 || count > rows.length) return 0;
  return bandPrefix(rows.take(count)) == parts.last ? count : 0;
}

/// Deterministic upload and record identities let a lost receipt or a growing
/// band file be replayed on the same enrollment. The band retains its originals.
Iterable<HealthUpload> bandUploads(
  Iterable<BandReading> rows, {
  required String device,
  required String collector,
  required String platform,
  required Set<PolarMetric> metrics,
  required DateTime since,
  required DateTime until,
  int maxCount = const int.fromEnvironment(
    'INGEST_MAX_READINGS',
    defaultValue: 1000,
  ),
  int maxBytes = const int.fromEnvironment(
    'INGEST_MAX_BODY_BYTES',
    defaultValue: 500000,
  ),
}) sync* {
  final eligible = eligibleBandRows(rows, metrics, since, until);
  if (maxCount < 1 || maxBytes < 1) {
    throw ArgumentError('Invalid upload limits');
  }
  const source = (
    id: 'polar-band-history',
    platform: 'bluetooth-le',
    name: 'Polar band',
  );
  for (var index = 0; index < eligible.length;) {
    var end = min<int>(index + min<int>(200, maxCount), eligible.length);
    while (true) {
      final entries = eligible.sublist(index, end);
      final points = [
        for (final row in entries)
          {
            'type': row.metric.type,
            'unit': row.metric.unit,
            'value': row.value,
            if (row.metric.group == 'instantaneous')
              'timestamp': (row.end ?? row.time).toUtc().toIso8601String(),
            if (row.metric.group == 'cumulative') ...{
              'periodStart': row.time.toUtc().toIso8601String(),
              'periodEnd': row.end!.toUtc().toIso8601String(),
              'duration': row.end!.difference(row.time).inMilliseconds / 1000,
            },
            if (row.metric.group == 'duration') ...{
              'startTime': row.time.toUtc().toIso8601String(),
              'endTime': row.end!.toUtc().toIso8601String(),
              'durationMinutes': row.value,
            },
            'sourceDeviceId': device,
            'sourceRecordId': _digest('$device/${row.id}'),
          },
      ];
      final key = _digest(
        jsonEncode([source.id, device, collector, platform, points]),
      );
      final start = entries.first.time.toUtc().toIso8601String();
      final finish = entries
          .map((r) => r.end ?? r.time)
          .reduce((a, b) => a.isAfter(b) ? a : b)
          .toUtc()
          .toIso8601String();
      final upload = HealthUpload(
        {
          ...source.toLegacyMetadata(),
          'contractVersion': 'wearables-numeric/1',
          'deviceInfo': {'deviceId': collector, 'platform': platform},
          'batchInfo': {
            'batchId': key,
            'dataPointCount': points.length,
            'collectionStart': start,
            'collectionEnd': finish,
          },
          'timestamp': finish,
          'measurements': {
            for (final group in ['instantaneous', 'cumulative', 'duration'])
              group: [
                for (var i = 0; i < entries.length; i++)
                  if (entries[i].metric.group == group) points[i],
              ],
          },
        },
        key,
        points.length,
        source: source,
      );
      if (upload.bytes.length <= maxBytes) {
        yield upload;
        index = end;
        break;
      }
      if (end - index == 1) {
        throw StateError('Single Polar reading exceeds upload limit');
      }
      end = index + (end - index) ~/ 2;
    }
  }
}

typedef PolarSharingState = ({
  String? grant,
  String? detail,
  bool paused,
  bool configured,
  DateTime? lastRead,
});

class PolarBandSync {
  // Invalidation only. The grant and last sync result remain in the durable store.
  static final _changes = ValueNotifier<int>(0);
  static ValueListenable<int> get changes => _changes;
  static const _zonePause =
      'Time zone changed. Check the band clock, then turn sharing off and on to resume.';
  static const _setupPause =
      'Band setup has changed or needs confirmation. Turn sharing off, then choose Auto sync to grant access again.';

  static const grantKey = StorageService.polarBandConsentKey;
  static final _prefs = SharedPreferencesAsync();
  static Future<void>? _active;
  static HttpClient? _client;
  static Timer? _timer;
  static bool _foreground = false;
  static String? _activeGrant;
  // Use the same store as the existing enrollment. Async preferences on Android
  // default to DataStore, so study credentials must come through StorageService.
  static Future<String?> grant(String token) async {
    final value = await _prefs.getString(grantKey);
    if (value == null || jsonDecode(value)['owner'] != _digest(token)) {
      return null;
    }
    return value;
  }

  static Future<void> rememberSetup(String token, String device) async {
    if (!await StorageService.currentStudyMatches(token)) return;
    final band = jsonEncode({
      'owner': _digest(token),
      'device': _digest(device),
    });
    await _prefs.setString(StorageService.polarBandSetupKey, band);
    _changes.value++;
  }

  static String _readKey(String token, String deviceHash) =>
      'polar_last_read_${_digest(token)}/$deviceHash';

  static Future<void> enable(
    String token,
    String device,
    Set<PolarMetric> metrics,
    String setupIdentity,
  ) async {
    if (metrics.isEmpty || !await StorageService.currentStudyMatches(token)) {
      throw StateError('A valid study and metrics are required');
    }
    final destination = HealthSyncService().endpointFor(token);
    if (destination.scheme != 'https') {
      throw StateError('Automatic sharing requires HTTPS');
    }
    final zone = (await FlutterTimezone.getLocalTimezone()).identifier;
    final cfg = jsonEncode({
      'zone': zone,
      'owner': _digest(token),
      'id': newUploadKey(),
      'device': device,
      'setupIdentity': setupIdentity,
      'metrics': metrics.map((m) => m.name).toList(),
      'since': DateTime.now().toUtc().toIso8601String(),
      'endpoint': destination.toString(),
    });
    await _prefs.setString(grantKey, cfg);
    _changes.value++;
    unawaited(run());
  }

  static Future<void> setMetrics(
    String token,
    String original,
    Set<PolarMetric> selected,
  ) => duringSetup(() async {
    if (selected.isEmpty ||
        await grant(token) != original ||
        !await StorageService.currentStudyMatches(token)) {
      throw StateError('Study or sharing settings changed');
    }
    final cfg = jsonDecode(original);
    final existing = List<String>.from(cfg['metrics']);
    final starts = Map<String, dynamic>.from(cfg['metricStarts'] ?? {});
    final now = DateTime.now().toUtc().toIso8601String();
    for (final m in selected) {
      if (existing.contains(m.name)) continue;

      starts[m.name] = now;
    }
    cfg['metrics'] = selected.map((m) => m.name).toList();
    cfg['metricStarts'] = starts;
    await _prefs.setString(grantKey, jsonEncode(cfg));
    _changes.value++;
  });

  static Future<void> disable(String token) async {
    final cfg = await grant(token);
    if (cfg == null) return;
    final device = jsonDecode(cfg)['device'] as String?;
    if (device != null) await rememberSetup(token, device);
    await _prefs.remove(grantKey);
    _changes.value++;
    if (_activeGrant == cfg) _client?.close(force: true);
    _timer?.cancel();
    _timer = null;
  }

  static Future<PolarSharingState> sharingState(String token) async {
    final saved = await grant(token);
    final cfg = saved == null ? null : jsonDecode(saved) as Map;
    final storedSetup = await _prefs.getString(
      StorageService.polarBandSetupKey,
    );
    final setup = storedSetup == null ? null : jsonDecode(storedSetup) as Map;
    final remembered = setup?['owner'] == _digest(token);
    final device = cfg?['device'] as String?;
    final deviceHash = device != null
        ? _digest(device)
        : remembered
        ? setup!['device'] as String
        : null;
    final timestamp = deviceHash == null
        ? null
        : await _prefs.getString(_readKey(token, deviceHash));
    final lastRead = timestamp == null
        ? null
        : DateTime.tryParse(timestamp)?.toLocal();
    if (cfg == null) {
      return (
        grant: null,
        detail: null,
        paused: false,
        configured: remembered,
        lastRead: lastRead,
      );
    }
    if (!await StorageService.currentStudyMatches(token)) {
      return (
        grant: saved,
        configured: true,
        lastRead: lastRead,
        detail: 'Study link unavailable. Review the study code.',
        paused: true,
      );
    }
    final endpoint = HealthSyncService().endpointFor(token);
    if (endpoint.scheme != 'https' || cfg['endpoint'] != endpoint.toString()) {
      return (
        grant: saved,
        configured: true,
        lastRead: lastRead,
        detail:
            'Study destination changed. Review sharing for the current destination.',
        paused: true,
      );
    }
    final stored = await _prefs.getString('polar_status_${cfg['id']}');
    if (stored != null && stored.startsWith('{')) {
      final result = jsonDecode(stored) as Map;
      return (
        grant: saved,
        configured: true,
        lastRead: lastRead,
        detail: result['detail'] as String,
        paused: result['paused'] == true,
      );
    }
    // Previous builds persisted the display message alone.
    return (
      grant: saved,
      configured: true,
      lastRead: lastRead,
      detail: stored,
      paused: stored == _zonePause || stored == _setupPause,
    );
  }

  static Future<void> _recordStatus(
    String id,
    String detail, {
    bool paused = false,
  }) => _prefs.setString(
    'polar_status_$id',
    jsonEncode({'detail': detail, 'paused': paused}),
  );

  static void startForeground() {
    _foreground = true;
    _changes.value++;
  }

  static void _schedule() {
    if (!_foreground) return;
    _timer ??= Timer.periodic(
      const Duration(minutes: 5),
      (_) => unawaited(run()),
    );
  }

  static void stopForeground() {
    _foreground = false;
    _timer?.cancel();
    _timer = null;
  }

  static bool _settingUp = false;

  static Future<T> duringSetup<T>(Future<T> Function() task) async {
    if (_settingUp) throw StateError('Setup is already running');
    _settingUp = true;
    try {
      await _active;
      return await task();
    } finally {
      _settingUp = false;
    }
  }

  static Future<void> run() => _settingUp
      ? Future.value()
      : _active ??= _run().whenComplete(() {
          _active = null;
          _changes.value++;
        });

  static Future<void> _run() async {
    final raw = await _prefs.getString(grantKey);
    if (raw == null) return;
    final cfg = jsonDecode(raw);
    final token = await StorageService.getOrCreateDeviceId();
    if (await grant(token) != raw ||
        !await StorageService.currentStudyMatches(token)) {
      return;
    }
    final endpoint = HealthSyncService().endpointFor(token);
    if (endpoint.scheme != 'https' || cfg['endpoint'] != endpoint.toString()) {
      return;
    }
    _schedule();
    final device = cfg['device'] as String, id = cfg['id'] as String;
    final retryAt = await _prefs.getInt('polar_retry_$id');
    if (retryAt != null && DateTime.now().millisecondsSinceEpoch < retryAt) {
      return;
    }
    final since = DateTime.parse(cfg['since']), now = DateTime.now().toUtc();
    final wanted = (cfg['metrics'] as List)
        .map((v) => PolarMetric.values.byName(v))
        .toSet();
    final files = PolarFiles(device);
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 8);
    _client = client;
    _activeGrant = raw;
    final collector = await StorageService.getOrCreateCollectorId();
    Future<void> authorized() async {
      if (await _prefs.getString(grantKey) != raw ||
          !await StorageService.currentStudyMatches(token)) {
        throw StateError('Study or sharing settings changed');
      }
    }

    final sender = HealthUploader(
      client: client,
      endpoint: endpoint,
      allowLegacy200: false,
      beforeSend: authorized,
    );
    var connectionAttempted = false;
    var stage = 'Connecting to the band';
    var accepted = 0;
    var unreadable = 0;
    Future<void> importFile(
      String path,
      Iterable<BandReading> Function(List<int>) parse, {
      String? revision,
      List<int>? provided,
      List<PolarMetric> selection = const [],
      String dependency = '',
    }) async {
      await authorized();
      final suffix = selection
          .where(wanted.contains)
          .map((m) => m.name)
          .join(',');
      final marker = 'polar_file_${id}_${_digest(path + suffix)}';
      // Even when the firmware supplies a modification time, periodically
      // recheck the content in case a file was replaced within one clock tick.
      final stamp = revision == null
          ? null
          : '${now.year}-${now.month}-${now.day}/$revision';
      if (stamp != null && await _prefs.getString('$marker/stat') == stamp) {
        return;
      }
      stage = 'Reading band history';
      final data = provided ?? await files.read(path);
      if (data == null) return;
      final digest = sha256.convert(data).toString() + dependency;
      if (await _prefs.getString(marker) == digest) {
        if (stamp != null) await _prefs.setString('$marker/stat', stamp);
        return;
      }
      // A band clock ahead of the phone may become eligible on a later pass.
      stage = 'Decoding band history';
      late final List<BandReading> rows;
      try {
        rows = parse(data).toList();
      } on FormatException {
        unreadable++;
        return;
      } on StateError {
        // Cardinality mismatch in a required Polar protobuf field.
        unreadable++;
        return;
      }
      final starts = cfg['metricStarts'] as Map?;
      final eligible = eligibleBandRows(rows, wanted, since, now).where((row) {
        final earliest = starts?[row.metric.name] as String?;
        return earliest == null || !row.time.isBefore(DateTime.parse(earliest));
      }).toList();
      final markerValue = await _prefs.getString('$marker/prefix');
      var confirmed = confirmedBandPrefix(eligible, markerValue);
      var fingerprint = confirmed == 0 ? '' : markerValue!.split('/').last;
      for (final upload in bandUploads(
        eligible.skip(confirmed),
        device: device,
        collector: collector,
        platform: Platform.operatingSystem,
        metrics: wanted,
        since: since,
        until: now,
      )) {
        await authorized();
        stage = 'Sending to the study';
        final receipt = await sender.send(upload, token);
        await StorageService.saveUploadReceipt(token, {
          ...receipt.document,
          'sourceLabel': 'Polar automatic sync',
          'receivedAt': DateTime.now().toUtc().toIso8601String(),
        });
        accepted += upload.readingCount;
        final end = confirmed + upload.readingCount;
        fingerprint = bandPrefix(
          eligible.getRange(confirmed, end),
          fingerprint,
        );
        confirmed = end;
        await _prefs.setString('$marker/prefix', '$confirmed/$fingerprint');
      }
      if (!rows.any((r) => (r.end ?? r.time).isAfter(now))) {
        await _prefs.setString(marker, digest);
        if (stamp != null) await _prefs.setString('$marker/stat', stamp);
      }
    }

    try {
      // Polar archives encode local wall times without a zone. Do not reinterpret
      // them after travel and silently assign old readings to a new instant.
      final zone = (await FlutterTimezone.getLocalTimezone()).identifier;
      final originalZone =
          cfg['zone'] ?? await _prefs.getString('polar_zone_$id');
      if (originalZone == null) await _prefs.setString('polar_zone_$id', zone);
      if (zone != (originalZone ?? zone) ||
          await _prefs.getBool('polar_zone_paused_$id') == true) {
        await _prefs.setBool('polar_zone_paused_$id', true);
        await _recordStatus(id, _zonePause, paused: true);
        return;
      }
      connectionAttempted = true;
      await files.open();
      final expected = cfg['setupIdentity'];
      if (expected == null || expected != await PolarSetup(files).identity()) {
        await _recordStatus(id, _setupPause, paused: true);
        return;
      }
      if (wanted.contains(PolarMetric.heartRate) ||
          wanted.contains(PolarMetric.pulseInterval)) {
        final directory = await files.read('/U/0/AUTOS/');
        if (directory != null) {
          for (final entry in polarDirectory(directory)) {
            if (!RegExp(r'^AUTOS\d{3}\.BPB$').hasMatch(entry.name)) continue;
            await importFile(
              '/U/0/AUTOS/${entry.name}',
              polarAutomaticSamples,
              revision: entry.revision,
            );
          }
        }
      }
      if (wanted.any(
        (m) => m != PolarMetric.heartRate && m != PolarMetric.pulseInterval,
      )) {
        final dir = await files.read('/U/0/');
        if (dir != null) {
          for (final entry in polarDirectory(dir)) {
            if (!RegExp(r'^\d{8}/?$').hasMatch(entry.name)) continue;
            final name = entry.name.substring(0, 8);
            final day = DateTime(
              int.parse(name.substring(0, 4)),
              int.parse(name.substring(4, 6)),
              int.parse(name.substring(6, 8)),
            );
            if (!DateTime(day.year, day.month, day.day + 1).isAfter(since) ||
                day.isAfter(now)) {
              continue;
            }
            final root = '/U/0/$name';
            if (wanted.contains(PolarMetric.skinTemperature)) {
              await importFile(
                '$root/SKINTEMP/TEMPCONT.BPB',
                (bytes) => polarTemperatureSamples(day, bytes),
              );
            }
            if (wanted.contains(PolarMetric.steps) ||
                wanted.contains(PolarMetric.activityMet)) {
              Future<void> stepsIn(String folder, int depth) async {
                final listing = await files.read(folder);
                if (listing == null) return;
                for (final item in polarDirectory(listing)) {
                  if (RegExp(r'^[A-Z0-9_-]+\.BPB$').hasMatch(item.name)) {
                    await importFile(
                      folder + item.name,
                      polarActivitySamples,
                      selection: [PolarMetric.steps, PolarMetric.activityMet],
                      revision: item.revision,
                    );
                  } else if (depth < 2 &&
                      RegExp(r'^[A-Z0-9_-]+/$').hasMatch(item.name)) {
                    await stepsIn(folder + item.name, depth + 1);
                  }
                }
              }

              await stepsIn('$root/ACT/', 0);
            }
            const workouts = [
              PolarMetric.workoutTime,
              PolarMetric.workoutEnergy,
            ];
            if (workouts.any(wanted.contains)) {
              final list = await files.read('$root/E/');
              if (list != null) {
                for (final session in polarDirectory(list)) {
                  if (!RegExp(r'^\d{6}/$').hasMatch(session.name)) continue;
                  await importFile(
                    '$root/E/${session.name}TSESS.BPB',
                    polarWorkout,
                    selection: workouts,
                  );
                }
              }
            }
            final tomorrow = DateTime(day.year, day.month, day.day + 1);
            if (PolarMetric.dailyTotals.any(wanted.contains) &&
                !tomorrow.isAfter(now) &&
                !day.isBefore(since)) {
              await importFile(
                '$root/DSUM/DSUM.BPB',
                (b) => polarDailyTotals(day, b),
                selection: PolarMetric.dailyTotals,
              );
            }
            final recovery =
                wanted.contains(PolarMetric.nightlyHrv) ||
                wanted.contains(PolarMetric.nightlyBreathing);
            if (PolarMetric.sleepStages.any(wanted.contains) || recovery) {
              final path = '$root/SLEEP/SLEEPRES.BPB';
              final sleep = await files.read(path);
              if (sleep == null) continue;
              if (PolarMetric.sleepStages.any(wanted.contains)) {
                await importFile(
                  path,
                  polarSleepPhases,
                  provided: sleep,
                  selection: PolarMetric.sleepStages,
                );
              }
              if (recovery) {
                await importFile(
                  '$root/NR/NR.BPB',
                  (b) => polarNightlyRecovery(day, polarSleepWindow(sleep), b),
                  selection: [
                    PolarMetric.nightlyHrv,
                    PolarMetric.nightlyBreathing,
                  ],
                  dependency: _digest(base64Encode(sleep)),
                );
              }
            }
          }
        }
      }
      await authorized();
      final completed = DateTime.now();
      if (unreadable == 0) {
        await _prefs.setString(
          _readKey(token, _digest(device)),
          completed.toUtc().toIso8601String(),
        );
      }
      await _recordStatus(
        id,
        'Last sync ${completed.toLocal().toString().split(".").first} · $accepted readings accepted on this pass.'
        "${unreadable == 0 ? '' : ' $unreadable band file(s) could not be decoded and will be retried.'}",
      );
    } on UnsupportedError {
      await _recordStatus(
        id,
        'This device does not expose Polar band history.',
        paused: true,
      );
    } on UploadHttpException catch (error) {
      final delay = error.retryAfter;
      if (delay != null) {
        await _prefs.setInt(
          'polar_retry_$id',
          DateTime.now().add(delay).millisecondsSinceEpoch,
        );
      }
      await _recordStatus(
        id,
        'Study server returned ${error.statusCode}. Unconfirmed files remain on the band.',
        paused: error.statusCode == 401 || error.statusCode == 403,
      );
    } catch (_) {
      await _recordStatus(id, '$stage was interrupted. Wearables will retry.');
    } finally {
      client.close(force: true);
      _client = null;
      _activeGrant = null;
      if (connectionAttempted) {
        try {
          await files.close();
        } catch (_) {}
      }
    }
  }
}
