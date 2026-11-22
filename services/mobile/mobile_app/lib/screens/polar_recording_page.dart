import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:universal_ble/universal_ble.dart';

import '../app_config.dart';
import 'polar_history_page.dart';
import '../services/health_sync_service.dart';
import '../services/health_upload.dart';
import '../services/polar_recording.dart';
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
  String message = 'Wear your Polar. On watches, enable heart rate sharing.';
  Completer<void>? stop;
  bool sending = false;
  bool longerRecording = false;
  static const uploadLimit = int.fromEnvironment(
    'INGEST_MAX_READINGS',
    defaultValue: 1000,
  );
  int get sampleLimit => (longerRecording ? 300 : 10).clamp(1, uploadLimit);
  HealthUpload? upload;
  UploadReceipt? lastReceipt;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
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
      await UniversalBle.discoverServices(device.deviceId);
      if (done.isCompleted) return;
      values =
          UniversalBle.characteristicValueStream(
            device.deviceId,
            characteristic,
          ).listen((bytes) {
            final bpm = polarHeartRate(bytes);
            if (bpm == null || done.isCompleted || !mounted) return;
            samples.add((bpm: bpm, time: DateTime.now().toUtc()));
            idleTimer?.cancel();
            idleTimer = Timer(const Duration(seconds: 30), finish);
            showMessage('$bpm bpm · ${samples.length}/$sampleLimit readings');
            if (samples.length >= sampleLimit) finish();
          });
      showMessage('Waiting for a heart rate measurement…');
      await UniversalBle.subscribeNotifications(
        device.deviceId,
        service,
        characteristic,
      );
      idleTimer ??= Timer(const Duration(seconds: 30), finish);
      await done.future;
    } catch (_) {
      showMessage(
        'Connection interrupted. Check that your Polar is sharing heart rate.',
      );
    } finally {
      idleTimer?.cancel();
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
            'No readings captured. Check sensor contact and heart rate sharing.',
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
        'sourceLabel': 'Polar Bluetooth',
        'receivedAt': DateTime.now().toUtc().toIso8601String(),
      });
      lastReceipt = receipt;
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
      await StorageService.saveUploadReceipt(token, {
        ...receipt.document,
        ...status,
        'sourceLabel': 'Polar Bluetooth',
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
    final busy = stop != null || sending;
    return Scaffold(
      appBar: AppBar(title: const Text('Polar device')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            message,
            semanticsLabel: message,
            style: Theme.of(context).textTheme.titleMedium,
          ),
          if (lastReceipt != null)
            TextButton(
              onPressed: busy ? null : checkStorage,
              child: const Text('Check storage status'),
            ),
          if (upload == null) ...[
            SwitchListTile(
              title: const Text('Longer recording'),
              subtitle: Text(
                'Stop at any time. This upload accepts up to $sampleLimit pulse readings.',
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
                subtitle: Text(device.deviceId),
                enabled: !busy,
                onTap: () => record(device),
              ),
            if (stop != null)
              TextButton(onPressed: finish, child: const Text('Stop')),
          ] else ...[
            Text('${samples.map((s) => s.bpm).join(', ')} bpm'),
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
