import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:universal_ble/universal_ble.dart';

import '../app_config.dart';
import 'polar_history_page.dart';
import 'polar_setup_page.dart';
import '../services/polar_files.dart';
import '../services/polar_setup.dart';
import '../services/health_sync_service.dart';
import '../services/health_upload.dart';
import '../services/polar_recording.dart';
import '../services/polar_pmd.dart';
import '../services/polar_band_sync.dart';
import '../storage_service.dart';

class PolarRecordingPage extends StatefulWidget {
  const PolarRecordingPage({super.key, required this.token});
  final String token;
  @override
  State<PolarRecordingPage> createState() => _PolarRecordingPageState();
}

class _PolarRecordingPageState extends State<PolarRecordingPage>
    with WidgetsBindingObserver {
  static const service = '0000180d-0000-1000-8000-00805f9b34fb';
  static const characteristic = '00002a37-0000-1000-8000-00805f9b34fb';
  final devices = <String, BleDevice>{};
  final samples = <PolarSample>[];
  final endpointResolver = HealthSyncService();
  String message =
      'Scan for your band. For a new Polar 360 choose Set up band. Choose Auto sync for daily use or tap the device for live recording.';
  Completer<void>? stop;
  bool sending = false;
  bool longerRecording = false;
  String? bandGrant;
  bool grantLoaded = false;
  String? bandStatus;
  Timer? statusTimer;
  Future<void> loadSharing() async {
    final granted = await PolarBandSync.grant(widget.token);
    final status = granted == null ? null : await PolarBandSync.status(granted);
    if (mounted) {
      setState(() {
        bandGrant = granted;
        bandStatus = status;
        grantLoaded = true;
      });
    }
  }

  bool settingUp = false;
  Future<void> setupBand(BleDevice device, {bool shareAfter = false}) async {
    setState(() => settingUp = true);
    final files = PolarFiles(device.deviceId);
    final setup = PolarSetup(files);
    Future<T> connected<T>(Future<T> Function() task) =>
        PolarBandSync.duringSetup(() async {
          try {
            await files.open(setupSession: true);
            return await task();
          } finally {
            try {
              await files.close();
            } catch (_) {}
          }
        });
    try {
      showMessage(
        'Checking the band. Keep it on its charger near the phone and accept pairing if prompted.',
      );
      final state = await connected(setup.inspect);
      if (!mounted) return;
      if (state == PolarSetupState.configured) {
        showMessage(
          'This band is already set up. Choose Auto sync to review study sharing.',
        );
        if (shareAfter) {
          final identity = await connected(setup.identity);
          if (identity == null) throw StateError('Band setup changed');
          if (mounted) await chooseAutomatic(device, identity);
        }
        return;
      }
      final profile = await Navigator.push<PolarSetupProfile>(
        context,
        MaterialPageRoute(
          builder: (_) => PolarSetupPage(band: device.name ?? 'Polar 360'),
        ),
      );
      if (profile == null || !mounted) {
        showMessage('Setup cancelled.');
        return;
      }
      showMessage('Saving settings to your Polar 360…');
      final written = await connected(
        () => setup.configure(profile, DateTime.now()),
      );
      showMessage(
        written
            ? 'Band setup complete. Choose Auto sync to review study sharing.'
            : 'This band is already set up. Choose Auto sync to review study sharing.',
      );
      if (shareAfter && mounted) {
        final identity = await connected(setup.identity);
        if (identity == null) throw StateError('Band setup changed');
        if (mounted) await chooseAutomatic(device, identity);
      }
    } on UniversalBleException catch (error) {
      final code = int.tryParse(error.details.toString());
      if (code == 5 || code == 15) {
        final detail =
            'This phone and the band could not establish an encrypted Bluetooth connection (ATT $code). Keep the band on its charger and close to this phone. Accept the system pairing request if it appears. If the band was reset, remove its old Bluetooth pairing before retrying.';
        showMessage(detail);
        if (mounted) {
          await showDialog<void>(
            context: context,
            builder: (context) => AlertDialog(
              title: const Text('Bluetooth pairing incomplete'),
              content: Text(detail),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('OK'),
                ),
              ],
            ),
          );
        }
      } else {
        showMessage(
          'Bluetooth setup was interrupted. Keep the band near the phone and retry Set up band.',
        );
      }
    } on UnsupportedError {
      showMessage(
        'Setup requires an identifiable Polar 360 with Bluetooth file transfer.',
      );
    } catch (_) {
      showMessage(
        'Could not confirm setup. Keep the band charged near the phone, accept Bluetooth pairing, and retry Set up band.',
      );
    } finally {
      if (mounted) setState(() => settingUp = false);
    }
  }

  Future<void> chooseAutomatic(BleDevice device, String identity) async {
    final selected = PolarMetric.values.toSet();
    final allowed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: const Text('Enable automatic sharing?'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Share new readings from ${device.name} with ${endpointResolver.endpointFor(widget.token).host} starting now. Wearables will automatically retrieve stored readings when the band reconnects. Stop sharing here at any time.',
                ),
                for (final m in PolarMetric.values)
                  CheckboxListTile(
                    title: Text(m.label),
                    value: selected.contains(m),
                    onChanged: (v) => update(() {
                      if (v == true) {
                        selected.add(m);
                      } else {
                        selected.remove(m);
                      }
                    }),
                  ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: selected.isEmpty
                  ? null
                  : () => Navigator.pop(context, true),
              child: const Text('Enable sharing'),
            ),
          ],
        ),
      ),
    );
    if (allowed != true || !mounted) return;
    try {
      await PolarBandSync.enable(
        widget.token,
        device.deviceId,
        selected,
        identity,
      );
      await loadSharing();
    } catch (_) {
      showMessage('Unable to enable automatic sharing. Check the study link.');
    }
  }

  PolarMetric metric = PolarMetric.heartRate;
  static const uploadLimit = int.fromEnvironment(
    'INGEST_MAX_READINGS',
    defaultValue: 1000,
  );
  int get sampleLimit => (longerRecording ? 300 : 10).clamp(1, uploadLimit);
  HealthUpload? upload;
  UploadReceipt? lastReceipt;
  PolarMetric? receiptMetric;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(loadSharing());
    statusTimer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => loadSharing(),
    );
  }

  void finish() {
    final current = stop;
    if (current != null && !current.isCompleted) current.complete();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) finish();
  }

  @override
  void dispose() {
    statusTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    finish();
    super.dispose();
  }

  void showMessage(String text) {
    if (mounted) setState(() => message = text);
  }

  Future<void> scan() async {
    final done = stop = Completer<void>();
    devices.clear();
    showMessage('Looking for Polar devices…');
    void found(BleDevice device) {
      if (!mounted ||
          done.isCompleted ||
          !isPolarAdvertisement(
            device.name,
            device.manufacturerDataList.map((m) => m.companyId),
          )) {
        return;
      }
      if ((device.name ?? '').isEmpty) {
        device.name = devices[device.deviceId]?.name ?? 'Polar sensor';
      }
      setState(() => devices[device.deviceId] = device);
    }

    final listener = UniversalBle.scanStream.listen(found);
    try {
      await UniversalBle.requestPermissions();
      if (done.isCompleted) return;
      final radio = await UniversalBle.getBluetoothAvailabilityState();
      if (done.isCompleted) return;
      if (radio != AvailabilityState.poweredOn) {
        showMessage(
          radio == AvailabilityState.poweredOff
              ? 'Bluetooth is unavailable to Wearables. Check Bluetooth in phone settings, then scan again.'
              : 'Bluetooth is not ready. Check Bluetooth access for Wearables, then scan again.',
        );
        return;
      }
      for (final device in await UniversalBle.getSystemDevices(
        withServices: [service],
      )) {
        found(device);
      }
      if (done.isCompleted) return;
      // A Polar sensor can advertise its company ID without a local name.
      await UniversalBle.startScan();
      await Future.any([
        done.future,
        Future<void>.delayed(const Duration(seconds: 8)),
      ]);
      showMessage(
        devices.isEmpty
            ? 'No Polar found. Check Bluetooth and heart rate sharing, then scan again.'
            : 'Select your Polar to record.',
      );
    } catch (_) {
      showMessage(
        'Scan unavailable. Check Bluetooth and the app’s nearby-device permission.',
      );
    } finally {
      await listener.cancel();
      try {
        await UniversalBle.stopScan();
      } catch (_) {}
      stop = null;
      if (mounted) setState(() {});
    }
  }

  Future<void> record(BleDevice device) async {
    final done = stop = Completer<void>();
    samples.clear();
    lastReceipt = null;
    showMessage('Connecting to ${device.name}…');
    Timer? idleTimer;
    StreamSubscription<List<int>>? values;
    StreamSubscription<bool>? connection;
    PolarPmd? pmd;
    String? failure;
    void accept(List<PolarSample> batch) {
      if (done.isCompleted || !mounted || batch.isEmpty) return;
      samples.addAll(batch.take(sampleLimit - samples.length));
      idleTimer?.cancel();
      idleTimer = Timer(const Duration(seconds: 30), finish);
      showMessage(
        '${displayValue(samples.last.value)} ${metric.displayUnit} · ${samples.length}/$sampleLimit readings',
      );
      if (samples.length >= sampleLimit) finish();
    }

    try {
      await UniversalBle.connect(
        device.deviceId,
        timeout: const Duration(seconds: 12),
      );
      if (done.isCompleted) return;
      connection = UniversalBle.connectionStream(device.deviceId).listen((
        connected,
      ) {
        if (!connected) finish();
      });
      final services = await UniversalBle.discoverServices(device.deviceId);
      if (done.isCompleted) return;
      if (metric == PolarMetric.heartRate) {
        values =
            UniversalBle.characteristicValueStream(
              device.deviceId,
              characteristic,
            ).listen(
              (bytes) {
                final bpm = polarHeartRate(bytes);
                if (bpm != null) {
                  accept([(value: bpm, time: DateTime.now().toUtc())]);
                }
              },
              onError: (Object e) {
                failure = 'Heart-rate stream interrupted.';
                finish();
              },
            );
        await UniversalBle.subscribeNotifications(
          device.deviceId,
          service,
          characteristic,
        );
      } else {
        if (!services.any((s) => s.uuid.toLowerCase() == polarPmdService)) {
          throw StateError(
            'This device did not expose the Polar measurement service.',
          );
        }
        if (Platform.isAndroid) {
          await UniversalBle.requestMtu(device.deviceId, 232);
        }
        pmd = PolarPmd(device.deviceId);
        await pmd.start(metric, device.name ?? '', accept, (error) {
          failure = 'Could not read ${metric.label}: $error';
          finish();
        });
      }
      if (samples.isEmpty) {
        showMessage('Waiting for ${metric.label.toLowerCase()}…');
      }
      idleTimer ??= Timer(
        Duration(seconds: metric == PolarMetric.pulseInterval ? 90 : 40),
        finish,
      );
      await done.future;
    } catch (error) {
      failure = error is StateError
          ? error.message
          : 'Could not connect to the selected Polar stream.';
    } finally {
      finish();
      idleTimer?.cancel();
      try {
        await pmd?.close();
      } catch (_) {
        /* Disconnect below also stops the live stream. */
      }
      await values?.cancel();
      await connection?.cancel();
      try {
        await UniversalBle.disconnect(
          device.deviceId,
          timeout: const Duration(seconds: 5),
        );
      } catch (_) {}
      try {
        if (mounted && samples.isNotEmpty) {
          upload = polarUpload(
            samples: samples,
            metric: metric,
            device: device.deviceId,
            name: device.name!,
            collector: await StorageService.getOrCreateCollectorId(),
            platform: Platform.operatingSystem,
          );
          showMessage(
            'Recorded ${samples.length} readings. Review before sharing.',
          );
        } else if (mounted) {
          showMessage(
            failure ??
                'No usable readings captured. Check that the band is worn snugly.',
          );
        }
      } catch (_) {
        showMessage('Could not prepare this recording. Scan and record again.');
      } finally {
        stop = null;
        if (mounted) setState(() {});
      }
    }
  }

  String displayValue(num value) => metric == PolarMetric.skinTemperature
      ? value.toStringAsFixed(2)
      : value.toString();

  Future<void> share() async {
    final batch = upload!;
    final token = widget.token;
    setState(() => sending = true);
    final client = HttpClient();
    try {
      if (await StorageService.getOrCreateDeviceId() != token ||
          StorageService.isCodeExpired(token)) {
        showMessage('Study link changed or expired. Return to the study home.');
        return;
      }
      final sender = HealthUploader(
        client: client,
        endpoint: endpointResolver.endpointFor(token),
        allowLegacy200: false,
      );
      final receipt = await sender.send(batch, token);
      await StorageService.saveUploadReceipt(token, {
        ...receipt.document,
        'sourceLabel': 'Polar Bluetooth · ${metric.label}',
        'receivedAt': DateTime.now().toUtc().toIso8601String(),
      });
      lastReceipt = receipt;
      receiptMetric = metric;
      upload = null;
      samples.clear();
      showMessage(
        'Study server accepted ${receipt.readingCount} readings. Receipt ${receipt.acceptanceId}',
      );
    } catch (_) {
      showMessage(
        'Acceptance could not be verified. Retry with the same recording.',
      );
    } finally {
      client.close(force: true);
      if (mounted) setState(() => sending = false);
    }
  }

  Future<void> checkStorage() async {
    final token = widget.token;
    final receipt = lastReceipt!;
    setState(() => sending = true);
    final client = HttpClient();
    try {
      final sender = HealthUploader(
        client: client,
        endpoint: endpointResolver.endpointFor(token),
      );
      final status = await sender.status(receipt.acceptanceId, token);
      if (status['rawSha256'] != receipt.rawSha256 ||
          status['readingCount'] != receipt.readingCount) {
        throw const FormatException(
          'Status does not match the accepted upload',
        );
      }
      await StorageService.saveUploadReceipt(token, {
        ...receipt.document,
        ...status,
        'sourceLabel': 'Polar Bluetooth · ${receiptMetric!.label}',
        'checkedAt': DateTime.now().toUtc().toIso8601String(),
      });
      showMessage(
        'Processing: ${status["processingState"]}. '
        'Storage confirmed for ${status["storedConfirmedCount"] ?? 0} of ${receipt.readingCount} readings.',
      );
    } catch (_) {
      showMessage(
        'Could not retrieve processing status. The upload was already accepted.',
      );
    } finally {
      client.close(force: true);
      if (mounted) setState(() => sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final busy = stop != null || sending || settingUp;
    return Scaffold(
      appBar: AppBar(title: const Text('Polar device')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          if (bandGrant == null)
            Text(
              message,
              semanticsLabel: message,
              style: Theme.of(context).textTheme.titleMedium,
            ),
          if (bandGrant != null)
            ListTile(
              title: const Text('Automatic Polar sharing is on'),
              subtitle: Text(bandStatus ?? 'Waiting for the first band sync.'),
              trailing: TextButton(
                onPressed: () async {
                  await PolarBandSync.disable(widget.token);
                  await loadSharing();
                },
                child: const Text('Turn off'),
              ),
            ),
          if (lastReceipt != null)
            TextButton(
              onPressed: busy ? null : checkStorage,
              child: const Text('Check storage status'),
            ),
          if (upload == null && bandGrant == null && grantLoaded) ...[
            Wrap(
              spacing: 8,
              children: [
                for (final option in PolarMetric.values)
                  ChoiceChip(
                    label: Text(option.label),
                    selected: metric == option,
                    onSelected: busy
                        ? null
                        : (_) => setState(() => metric = option),
                  ),
              ],
            ),
            SwitchListTile(
              title: const Text('Longer recording'),
              subtitle: Text(
                'Stop at any time. This upload accepts up to $sampleLimit readings.',
              ),
              value: longerRecording,
              onChanged: busy
                  ? null
                  : (v) => setState(() => longerRecording = v),
            ),
            OutlinedButton(
              onPressed: busy ? null : scan,
              child: const Text('Scan for Polar'),
            ),
            for (final device in devices.values)
              ListTile(
                title: Text(device.name!),
                subtitle: TextButton(
                  onPressed: busy ? null : () => setupBand(device),
                  child: const Text('Set up band'),
                ),
                enabled: !busy,
                onTap: busy ? null : () => record(device),
                trailing: TextButton(
                  onPressed: busy
                      ? null
                      : () => setupBand(device, shareAfter: true),
                  child: const Text('Auto sync'),
                ),
              ),
            if (stop != null)
              TextButton(onPressed: finish, child: const Text('Stop')),
          ] else if (upload != null) ...[
            Text(
              '${metric.label}: ${samples.map((s) => displayValue(s.value)).join(', ')} ${metric.displayUnit}',
            ),
            FilledButton(
              onPressed: busy ? null : share,
              child: Text(
                'Share with ${endpointResolver.endpointFor(widget.token).host}',
              ),
            ),
            TextButton(
              onPressed: busy
                  ? null
                  : () => setState(() {
                      upload = null;
                      samples.clear();
                      message = 'Recording discarded.';
                    }),
              child: const Text('Discard recording'),
            ),
          ],
          if (!busy && upload == null)
            OutlinedButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => PolarHistoryPage(token: widget.token),
                ),
              ),
              child: const Text('Import a day from Polar Flow'),
            ),
          if (!busy && upload == null)
            ExpansionTile(
              title: const Text('Sync workouts and history from Polar Flow'),
              children: [
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    'Sync your watch in Polar Flow. In Flow → General settings, enable '
                    '${AppConfig.healthStore} and choose the categories you want to share. '
                    'In Wearables, enable ${AppConfig.healthStore} in Account settings and use Share now. '
                    'Only supported categories that Flow writes and you allow can be imported. '
                    'Use a separate recording window for the Bluetooth demo to avoid overlapping readings.',
                  ),
                ),
              ],
            ),
        ],
      ),
    );
  }
}
