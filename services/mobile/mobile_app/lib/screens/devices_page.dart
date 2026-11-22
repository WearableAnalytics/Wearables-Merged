import 'package:flutter/material.dart';
import '../services/polar_band_sync.dart';
import 'polar_recording_page.dart';

class DevicesPage extends StatelessWidget {
  const DevicesPage({
    super.key,
    required this.token,
    required this.available,
    required this.openAccount,
  });
  final String token;
  final bool available;
  final VoidCallback openAccount;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Devices')),
    body: ListView(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      children: [
        if (available)
          PolarDeviceEntry(key: ValueKey(token), token: token)
        else
          const ListTile(
            title: Text('A valid study link is required to manage wearables.'),
          ),
        ListTile(
          leading: const Icon(Icons.cloud_outlined),
          title: const Text('Phone and cloud sources'),
          trailing: const Icon(Icons.chevron_right),
          onTap: openAccount,
        ),
      ],
    ),
  );
}

class PolarDeviceEntry extends StatefulWidget {
  const PolarDeviceEntry({super.key, required this.token, this.openDevices});
  final VoidCallback? openDevices;
  final String token;

  @override
  State<PolarDeviceEntry> createState() => _PolarDeviceEntryState();
}

class _PolarDeviceEntryState extends State<PolarDeviceEntry> {
  late Future<PolarSharingState> sharing = PolarBandSync.sharingState(
    widget.token,
  );

  @override
  void initState() {
    super.initState();
    PolarBandSync.changes.addListener(reload);
  }

  void reload() {
    setState(() {
      sharing = PolarBandSync.sharingState(widget.token);
    });
  }

  @override
  void dispose() {
    PolarBandSync.changes.removeListener(reload);
    super.dispose();
  }

  Future<void> open() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => PolarRecordingPage(token: widget.token),
      ),
    );
    if (mounted) reload();
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<PolarSharingState>(
    future: sharing,
    builder: (context, snapshot) {
      final state = snapshot.data;
      if (state == null && !snapshot.hasError) return const SizedBox.shrink();
      if (widget.openDevices != null && (state == null || !state.configured)) {
        return OutlinedButton.icon(
          onPressed: widget.openDevices,
          icon: const Icon(Icons.watch_outlined),
          label: Text(
            snapshot.hasError ? 'Manage devices' : 'Connect wearable',
          ),
        );
      }
      String status;
      if (snapshot.hasError) {
        status = 'Sharing status unavailable';
      } else if (!state!.configured) {
        status = 'Set up via Bluetooth';
      } else {
        status = state.paused
            ? 'Auto-sync paused'
            : state.grant == null
            ? 'Auto-sync off'
            : 'Auto-sync enabled';
        final at = state.lastRead;
        if (at != null) {
          final local = MaterialLocalizations.of(context);
          final clock = local.formatTimeOfDay(
            TimeOfDay.fromDateTime(at),
            alwaysUse24HourFormat: MediaQuery.alwaysUse24HourFormatOf(context),
          );
          final day = DateUtils.isSameDay(at, DateTime.now())
              ? ''
              : '${local.formatShortDate(at)} ';
          status += ' · Last successful sync $day$clock';
        } else if (state.grant != null &&
            !state.paused &&
            state.detail == null) {
          status += ' · Waiting for a successful sync';
        }
      }
      return ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 12),
        leading: const Icon(Icons.watch_outlined),
        title: const Text('Polar 360'),
        subtitle: Text(status),
        trailing: const Icon(Icons.chevron_right),
        onTap: open,
      );
    },
  );
}
