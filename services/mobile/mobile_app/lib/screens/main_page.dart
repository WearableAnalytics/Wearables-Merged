import 'package:flutter/material.dart';
import '../data_view_page.dart';
import '../services/health_sync_service.dart';
import '../services/sync_activity_notifier.dart';
import '../storage_service.dart';
import 'qr_scan_page.dart';
import '../widgets/sending_status_overlay.dart';

enum _DeviceIdInputChoice { manual, qr }

/// Main dashboard screen that lets the user review device info and
/// trigger a manual sync of health data to the backend.
class MainPage extends StatefulWidget {
  const MainPage({super.key});

  @override
  State<MainPage> createState() => _MainPageState();
}

class _MainPageState extends State<MainPage> {
  final HealthSyncService _healthSyncService = HealthSyncService();
  DateTime? _lastSendTime;
  final TextEditingController _deviceIdController = TextEditingController();
  bool _resetLastSync = false;

  @override
  void initState() {
    super.initState();
    // Load cached device ID + last sync time as soon as the screen mounts.
    _loadDeviceInfo();
  }

  @override
  void dispose() {
    _deviceIdController.dispose();
    super.dispose();
  }

  Future<void> _loadDeviceInfo() async {
    final deviceId = await StorageService.getOrCreateDeviceId();
    final lastSendTime = await StorageService.getLastDataSendTime();

    if (!mounted) return;
    setState(() {
      _lastSendTime = lastSendTime;
      _deviceIdController.text = deviceId;
    });
  }

  Future<void> _promptForDeviceId() async {
    if (!mounted) return;
    final choice = await showModalBottomSheet<_DeviceIdInputChoice>(
      context: context,
      builder: (ctx) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                leading: const Icon(Icons.keyboard),
                title: const Text('Enter manually'),
                onTap: () => Navigator.of(ctx).pop(_DeviceIdInputChoice.manual),
              ),
              ListTile(
                leading: const Icon(Icons.qr_code_scanner),
                title: const Text('Scan QR code'),
                onTap: () => Navigator.of(ctx).pop(_DeviceIdInputChoice.qr),
              ),
            ],
          ),
        );
      },
    );

    switch (choice) {
      case _DeviceIdInputChoice.manual:
        await _showManualEntryDialog();
        break;
      case _DeviceIdInputChoice.qr:
        await _launchQrScanner();
        break;
      case null:
        break;
    }
  }

  Future<void> _showManualEntryDialog() async {
    final tempController = TextEditingController(
      text: _deviceIdController.text,
    );
    final result = await showDialog<String>(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: const Text('Enter Device ID'),
          content: TextField(
            controller: tempController,
            autofocus: true,
            decoration: const InputDecoration(
              hintText: 'Enter device ID',
              border: OutlineInputBorder(),
              isDense: true,
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () =>
                  Navigator.of(ctx).pop(tempController.text.trim()),
              child: const Text('Use ID'),
            ),
          ],
        );
      },
    );

    // Dispose controller after the dialog finishes its own disposal cycle.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      tempController.dispose();
    });

    if (result != null && result.isNotEmpty) {
      setState(() {
        _deviceIdController.text = result.trim();
      });
    }
  }

  Future<void> _launchQrScanner() async {
    final scannedValue = await Navigator.of(
      context,
    ).push<String>(MaterialPageRoute(builder: (_) => const QrScanPage()));

    if (scannedValue != null && scannedValue.trim().isNotEmpty) {
      setState(() {
        _deviceIdController.text = scannedValue.trim();
      });
    }
  }

  Future<void> _updateDeviceId() async {
    final newDeviceId = _deviceIdController.text.trim();
    if (newDeviceId.isNotEmpty) {
      final currentId = await StorageService.getOrCreateDeviceId();

      // Update device ID only if it has changed
      if (newDeviceId != currentId) {
        await StorageService.setCustomDeviceId(newDeviceId);
      }

      // Reset last sync time if requested
      if (_resetLastSync) {
        await StorageService.clearLastDataSendTime();
      }

      await _loadDeviceInfo();
      if (!mounted) return;
      setState(() {
        _resetLastSync = false;
      });
    }
  }

  Future<void> _sendRecentHealthData() async {
    if (SyncActivityNotifier.isSyncing.value) return;

    await _healthSyncService.sendSinceLastSync();
    await _loadDeviceInfo();
  }

  String _formatDateTime(DateTime dateTime) {
    return '${dateTime.day}/${dateTime.month}/${dateTime.year} ${dateTime.hour.toString().padLeft(2, '0')}:${dateTime.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final headerBackground = colorScheme.primaryContainer.withOpacity(0.1);

    return Scaffold(
      appBar: AppBar(
        backgroundColor: headerBackground,
        surfaceTintColor: headerBackground,
        elevation: 0,
        centerTitle: false,
        automaticallyImplyLeading: false,
        iconTheme: IconThemeData(color: colorScheme.onSurface),
        title: const SendingStatusOverlay(
          padding: EdgeInsets.zero,
          useSafeArea: false,
        ),
        actions: [
          IconButton(
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (context) => const DataViewPage()),
              );
            },
            icon: const Icon(Icons.analytics),
            tooltip: 'View Health Data',
          ),
        ],
      ),
      body: Stack(
        children: [
          Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Theme.of(context).colorScheme.primaryContainer.withOpacity(0.1),
                  Theme.of(context).colorScheme.surface,
                ],
              ),
            ),
            child: SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    return SingleChildScrollView(
                      child: ConstrainedBox(
                        constraints: BoxConstraints(
                          minHeight: constraints.maxHeight,
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                // Header
                                Card(
                                  elevation: 4,
                                  child: Padding(
                                    padding: const EdgeInsets.all(24.0),
                                    child: Column(
                                      children: [
                                        Icon(
                                          Icons.health_and_safety,
                                          size: 48,
                                          color: Theme.of(
                                            context,
                                          ).colorScheme.primary,
                                        ),
                                        const SizedBox(height: 16),
                                        Text(
                                          'Wearables Health Monitor',
                                          style: Theme.of(context)
                                              .textTheme
                                              .headlineSmall
                                              ?.copyWith(
                                                fontWeight: FontWeight.bold,
                                              ),
                                          textAlign: TextAlign.center,
                                        ),
                                        const SizedBox(height: 8),
                                        Text(
                                          'Send your health data to the cloud',
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodyMedium
                                              ?.copyWith(
                                                color: Theme.of(context)
                                                    .colorScheme
                                                    .onSurfaceVariant,
                                              ),
                                          textAlign: TextAlign.center,
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 24),
                                // Device Info Card
                                Card(
                                  elevation: 2,
                                  child: Padding(
                                    padding: const EdgeInsets.all(20.0),
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Row(
                                          children: [
                                            Icon(
                                              Icons.smartphone,
                                              color: Theme.of(
                                                context,
                                              ).colorScheme.primary,
                                            ),
                                            const SizedBox(width: 8),
                                            Text(
                                              'Device Settings',
                                              style: Theme.of(context)
                                                  .textTheme
                                                  .titleMedium
                                                  ?.copyWith(
                                                    fontWeight: FontWeight.w600,
                                                  ),
                                            ),
                                          ],
                                        ),
                                        const SizedBox(height: 16),
                                        // Device ID input field
                                        Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              'Device ID',
                                              style: Theme.of(
                                                context,
                                              ).textTheme.labelMedium,
                                            ),
                                            const SizedBox(height: 8),
                                            InkWell(
                                              onTap: _promptForDeviceId,
                                              borderRadius: BorderRadius.circular(
                                                12,
                                              ),
                                              child: Container(
                                                width: double.infinity,
                                                padding:
                                                    const EdgeInsets.symmetric(
                                                  horizontal: 16,
                                                  vertical: 14,
                                                ),
                                                decoration: BoxDecoration(
                                                  borderRadius:
                                                      BorderRadius.circular(12),
                                                  border: Border.all(
                                                    color: Theme.of(
                                                      context,
                                                    ).colorScheme.outlineVariant,
                                                  ),
                                                  color: Theme.of(context)
                                                      .colorScheme
                                                      .surfaceVariant
                                                      .withOpacity(0.3),
                                                ),
                                                child: Row(
                                                  children: [
                                                    Expanded(
                                                      child: Column(
                                                        crossAxisAlignment:
                                                            CrossAxisAlignment
                                                                .start,
                                                        children: [
                                                          Text(
                                                            _deviceIdController
                                                                .text,
                                                            style:
                                                                Theme.of(context)
                                                                    .textTheme
                                                                    .titleMedium
                                                                    ?.copyWith(
                                                                      fontWeight:
                                                                          FontWeight
                                                                              .w600,
                                                                    ),
                                                            overflow:
                                                                TextOverflow
                                                                    .ellipsis,
                                                          ),
                                                          const SizedBox(height: 4),
                                                          Text(
                                                            'Tap to enter manually or scan a QR code',
                                                            style: Theme.of(context)
                                                                .textTheme
                                                                .bodySmall
                                                                ?.copyWith(
                                                                  color: Theme.of(
                                                                    context,
                                                                  )
                                                                      .colorScheme
                                                                      .onSurfaceVariant,
                                                                ),
                                                          ),
                                                        ],
                                                      ),
                                                    ),
                                                    const SizedBox(width: 12),
                                                    const Icon(
                                                      Icons.qr_code,
                                                      size: 24,
                                                    ),
                                                  ],
                                                ),
                                              ),
                                            ),
                                            const SizedBox(height: 8),
                                            CheckboxListTile(
                                              contentPadding: EdgeInsets.zero,
                                              title: const Text(
                                                'Reset last sync time as well',
                                              ),
                                              subtitle: const Text(
                                                'Use when this device ID represents a new user/device.',
                                              ),
                                              value: _resetLastSync,
                                              onChanged: (value) {
                                                setState(() {
                                                  _resetLastSync = value ?? false;
                                                });
                                              },
                                              controlAffinity:
                                                  ListTileControlAffinity.leading,
                                            ),
                                            const SizedBox(height: 8),
                                            SizedBox(
                                              width: double.infinity,
                                              child: ElevatedButton.icon(
                                                onPressed: _updateDeviceId,
                                                icon: const Icon(
                                                  Icons.save,
                                                  size: 18,
                                                ),
                                                label: const Text('Update'),
                                                style: ElevatedButton.styleFrom(
                                                  padding: const EdgeInsets.symmetric(
                                                    horizontal: 16,
                                                    vertical: 14,
                                                  ),
                                                ),
                                              ),
                                            ),
                                          ],
                                        ),
                                        const SizedBox(height: 16),
                                        Row(
                                          children: [
                                            Icon(
                                              Icons.schedule,
                                              size: 16,
                                              color: Theme.of(
                                                context,
                                              ).colorScheme.onSurfaceVariant,
                                            ),
                                            const SizedBox(width: 8),
                                            Text(
                                              'Last sync: ${_lastSendTime != null ? _formatDateTime(_lastSendTime!) : "Never"}',
                                              style: Theme.of(context)
                                                  .textTheme
                                                  .bodySmall
                                                  ?.copyWith(
                                                    color: Theme.of(
                                                      context,
                                                    ).colorScheme.onSurfaceVariant,
                                                  ),
                                            ),
                                          ],
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                // Main Action Button
                                Card(
                                  elevation: 4,
                                  child: Padding(
                                    padding: const EdgeInsets.all(4.0),
                                    child: ValueListenableBuilder<bool>(
                                      valueListenable:
                                          SyncActivityNotifier.isSyncing,
                                      builder: (context, isSyncing, _) {
                                        return ElevatedButton(
                                          onPressed: isSyncing
                                              ? null
                                              : _sendRecentHealthData,
                                          style: ElevatedButton.styleFrom(
                                            backgroundColor: Theme.of(
                                              context,
                                            ).colorScheme.primary,
                                            foregroundColor: Theme.of(
                                              context,
                                            ).colorScheme.onPrimary,
                                            padding: const EdgeInsets.symmetric(
                                              vertical: 20,
                                            ),
                                            shape: RoundedRectangleBorder(
                                              borderRadius:
                                                  BorderRadius.circular(12),
                                            ),
                                            elevation: 0,
                                          ),
                                          child: Row(
                                            mainAxisAlignment:
                                                MainAxisAlignment.center,
                                            children: [
                                              Icon(
                                                isSyncing
                                                    ? Icons.sync
                                                    : Icons.cloud_upload,
                                                size: 24,
                                              ),
                                              const SizedBox(width: 12),
                                              Text(
                                                isSyncing
                                                    ? 'Syncing...'
                                                    : 'Send Health Data',
                                                style: Theme.of(context)
                                                    .textTheme
                                                    .titleMedium
                                                    ?.copyWith(
                                                      fontWeight: FontWeight.w600,
                                                      color: Theme.of(
                                                        context,
                                                      ).colorScheme.onPrimary,
                                                    ),
                                              ),
                                            ],
                                          ),
                                        );
                                      },
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 16),
                                Text(
                                  'Uploads new health data since last sync (or last 7 days if first time)',
                                  style: Theme.of(context).textTheme.bodySmall
                                      ?.copyWith(
                                        color: Theme.of(
                                          context,
                                        ).colorScheme.onSurfaceVariant,
                                      ),
                                  textAlign: TextAlign.center,
                                ),
                                const SizedBox(height: 24),
                              ],
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
