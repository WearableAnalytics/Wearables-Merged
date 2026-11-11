import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../app_config.dart';
import '../services/cloud_connector_service.dart';
import '../state/app_state.dart';
import '../theme/app_theme.dart';
import '../utils/formatting.dart';
import '../widgets/study_code_entry.dart';
import '../widgets/study_info_link.dart';
import '../widgets/sync_mode_dialog.dart';

/// Third tab: the linked study code, sharing options, data sources and app information.
class StudyPage extends StatefulWidget {
  const StudyPage({super.key, required this.state});

  final AppState state;

  @override
  State<StudyPage> createState() => _StudyPageState();
}

class _StudyPageState extends State<StudyPage> with WidgetsBindingObserver {
  bool _showCode = false;
  String? _awaitingAuthProvider;
  String _version = '';

  AppState get state => widget.state;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    PackageInfo.fromPlatform().then((info) {
      if (mounted) {
        setState(() => _version = '${info.version} (${info.buildNumber})');
      }
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState lifecycleState) {
    if (lifecycleState == AppLifecycleState.resumed &&
        _awaitingAuthProvider != null) {
      final providerId = _awaitingAuthProvider!;
      _awaitingAuthProvider = null;
      _checkCloudAfterAuth(CloudProvider.find(providerId));
    }
  }

  Future<void> _checkCloudAfterAuth(CloudProvider provider) async {
    try {
      // Small delay for InAppBrowser closes
      await Future.delayed(const Duration(milliseconds: 350));
      final wasConnected = state.isCloudConnected(provider.id);
      final status = await state.refreshCloudStatus(provider.id);
      if (!mounted) return;
      if (status.connected && !wasConnected) {
        _toast('${provider.name} Cloud connected.');
        await _promptSyncModeAfterConnect(provider);
      } else if (status.connected) {
        _toast('${provider.name} Cloud connection is active.');
      }
    } catch (e) {
      if (mounted) {
        _toast('Could not verify ${provider.name} connection: $e');
      }
    }
  }

  Future<void> _promptSyncModeAfterConnect(CloudProvider provider) async {
    if (!mounted) return;
    await promptSyncModeAfterConnect(context, state, provider);
  }

  Future<void> _connectCloud(CloudProvider provider) async {
    if (!state.isLinked) {
      _toast('Please link your personal QR code first.');
      return;
    }
    _awaitingAuthProvider = provider.id;
    final launched = await state.startCloudConnect(provider.id);
    if (!mounted) return;
    if (!launched) {
      _awaitingAuthProvider = null;
      _toast('Could not open ${provider.name} login page.');
    }
  }

  Future<void> _refreshCloudStatus(CloudProvider provider) async {
    try {
      final wasConnected = state.isCloudConnected(provider.id);
      final status = await state.refreshCloudStatus(provider.id);
      if (!mounted) return;
      if (status.connected) {
        if (!wasConnected) {
          await _promptSyncModeAfterConnect(provider);
        } else {
          _toast('${provider.name} Cloud is connected.');
        }
      } else {
        _toast('${provider.name} Cloud is not connected yet.');
      }
    } catch (e) {
      if (mounted) {
        _toast('Failed to check ${provider.name} Cloud status.');
      }
    }
  }

  Future<void> _confirmDisconnectCloud(CloudProvider provider) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Remove ${provider.name} Cloud connection?'),
        content: Text(
          'This will deregister your ${provider.name} account on the server and stop '
          'direct cloud synchronization.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              minimumSize: const Size(0, 44),
              backgroundColor: AppColors.coral,
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await state.disconnectCloud(provider.id);
      if (!mounted) return;
      _toast('${provider.name} Cloud connection removed from server.');
    } catch (e) {
      if (!mounted) return;
      _toast('Could not remove ${provider.name} Cloud connection: $e');
    }
  }

  Future<void> _toggleLocalSync(bool enabled) async {
    await state.setLocalHealthSyncEnabled(enabled);
    if (!mounted) return;
    final cloudName = state.primaryCloudProvider?.name ?? 'Cloud';
    if (!enabled && state.hasAnyCloudConnection) {
      _toast('$cloudName Cloud-only mode active. Local phone uploads paused.');
    } else if (!enabled && !state.hasAnyCloudConnection) {
      _toast(
        'Local ${AppConfig.healthStore} uploads paused. Connect a Cloud wearable below for cloud sync.',
      );
    } else if (enabled && state.hasAnyCloudConnection) {
      _toast(
        'Parallel sync active (${AppConfig.healthStore} + $cloudName Cloud).',
      );
    } else {
      _toast('${AppConfig.healthStore} synchronization enabled.');
    }
  }

  Future<void> _changeCode({required bool scan}) async {
    final code = scan
        ? await scanStudyCode(context)
        : await enterStudyCodeManually(context);
    if (code == null || !mounted) return;
    if (state.isCodeUnusable) {
      // Replacing an expired or rejected code: continue where sharing stopped.
      await state.linkStudyCode(code, resetLastSync: false);
      _toast('Personal code linked. Sharing continues.');
      await state.syncNow();
      return;
    }
    if (code == state.deviceId) {
      _toast('This personal code is already linked.');
      return;
    }
    final reset = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Link new personal code?'),
        content: Text(
          'Future uploads will belong to the new code. Should the period since '
          '${formatDate(state.initialSyncStart)} be shared again for it?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Only new data'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Share again'),
          ),
        ],
      ),
    );
    if (reset == null) return;
    await state.linkStudyCode(code, resetLastSync: reset);
    _toast('New personal code linked.');
  }

  Future<void> _confirmReset() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Share the full period again?'),
        content: Text(
          'The next upload will include all data since '
          '${formatDate(state.initialSyncStart)}, including data that was '
          'already shared.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Reset'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await state.resetLastSync();
    _toast(
      'The next upload will start from ${formatDate(state.initialSyncStart)}.',
    );
  }

  Future<void> _pickStartDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: state.initialSyncStart,
      firstDate: DateTime(now.year - 5),
      lastDate: now,
      helpText: 'Share data from',
    );
    if (picked == null) return;
    await state.setInitialSyncStart(picked);
  }

  void _toast(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  String _masked(String code) {
    if (code.length <= 12) return code;
    return '${code.substring(0, 6)}••••••${code.substring(code.length - 6)}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Account')),
      body: ListenableBuilder(
        listenable: state,
        builder: (context, _) => ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
          children: [
            _SectionLabel('Personal code'),
            Card(
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Symbols.verified_user_sharp),
                    title: Text(
                      !state.isLinked
                          ? 'Not linked'
                          : state.codeRejected
                          ? 'Rejected by server, please scan your QR code again'
                          : state.codeExpired
                          ? 'Expired, please scan your QR code again'
                          : 'Linked',
                    ),
                    subtitle: Text(
                      state.isLinked
                          ? (_showCode
                                ? state.deviceId
                                : _masked(state.deviceId))
                          : 'Scan the QR code from your information sheet.',
                      style: _showCode
                          ? const TextStyle(fontFamily: 'Menlo', fontSize: 11)
                          : null,
                    ),
                    trailing: state.isLinked
                        ? IconButton(
                            tooltip: _showCode ? 'Hide code' : 'Show code',
                            icon: Icon(
                              _showCode
                                  ? Symbols.visibility_off_sharp
                                  : Symbols.visibility_sharp,
                            ),
                            onPressed: () =>
                                setState(() => _showCode = !_showCode),
                          )
                        : null,
                  ),
                  const Divider(indent: 20, endIndent: 20),
                  ListTile(
                    leading: const Icon(Symbols.qr_code_scanner_sharp),
                    title: const Text('Scan new QR code'),
                    trailing: const Icon(Symbols.chevron_right_sharp),
                    onTap: () => _changeCode(scan: true),
                  ),
                  ListTile(
                    leading: const Icon(Symbols.keyboard_sharp),
                    title: const Text('Enter code manually'),
                    trailing: const Icon(Symbols.chevron_right_sharp),
                    onTap: () => _changeCode(scan: false),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            _SectionLabel('Sharing'),
            Card(
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Symbols.schedule_sharp),
                    title: const Text('Shared up to'),
                    trailing: Text(
                      state.lastSendTime == null
                          ? 'Not yet'
                          : formatDateTime(state.lastSendTime!),
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: AppColors.textMuted,
                      ),
                    ),
                  ),
                  const Divider(indent: 20, endIndent: 20),
                  Theme(
                    data: Theme.of(
                      context,
                    ).copyWith(dividerColor: Colors.transparent),
                    child: ExpansionTile(
                      leading: const Icon(Symbols.tune_sharp),
                      title: const Text('More settings'),
                      tilePadding: const EdgeInsets.symmetric(horizontal: 20),
                      childrenPadding: const EdgeInsets.only(bottom: 8),
                      iconColor: AppColors.blue,
                      children: [
                        ListTile(
                          leading: const Icon(Symbols.event_sharp),
                          title: const Text('Share data from'),
                          subtitle: const Text(
                            'Start of the first upload and of uploads after a reset.',
                          ),
                          trailing: _Pill(formatDate(state.initialSyncStart)),
                          onTap: _pickStartDate,
                        ),
                        ListTile(
                          leading: const Icon(Symbols.restart_alt_sharp),
                          title: const Text('Share full period again'),
                          subtitle: const Text(
                            'Resets the last upload time. Use for a new participant.',
                          ),
                          onTap: _confirmReset,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            _SectionLabel('Data sources'),
            Card(
              child: Column(
                children: [
                  SwitchListTile(
                    secondary: const Icon(Symbols.favorite_sharp),
                    title: Text(AppConfig.healthStore),
                    subtitle: Text(
                      state.localHealthSyncEnabled &&
                              state.hasAnyCloudConnection
                          ? 'Syncing local phone data in parallel with ${state.primaryCloudProvider?.name ?? "Cloud"} Cloud.'
                          : state.localHealthSyncEnabled
                          ? 'Syncs health data stored on this ${AppConfig.deviceName}.'
                          : state.hasAnyCloudConnection
                          ? 'Paused - using ${state.primaryCloudProvider?.name ?? "Cloud"} Cloud only (no phone upload needed).'
                          : 'Paused - enable or connect a Cloud wearable below.',
                    ),
                    value: state.localHealthSyncEnabled,
                    activeThumbColor: AppColors.blue,
                    onChanged: _toggleLocalSync,
                  ),
                  for (final provider in CloudProvider.activeProviders) ...[
                    const Divider(indent: 20, endIndent: 20),
                    _CloudProviderTile(
                      provider: provider,
                      connected: state.isCloudConnected(provider.id),
                      busy: state.isCloudBusy(provider.id),
                      userId: state.cloudUserId(provider.id),
                      onRefresh: () => _refreshCloudStatus(provider),
                      onConnect: () => _connectCloud(provider),
                      onDisconnect: () => _confirmDisconnectCloud(provider),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 24),
            _SectionLabel('About'),
            Card(
              child: Column(
                children: [
                  if (AppConfig.studyInfoUrl.isNotEmpty) ...[
                    ListTile(
                      leading: const Icon(Symbols.info_sharp),
                      title: const Text('About the Charité Wearables platform'),
                      trailing: const Icon(Symbols.open_in_new_sharp, size: 20),
                      onTap: openStudyInfo,
                    ),
                    const Divider(indent: 20, endIndent: 20),
                  ],
                  ListTile(
                    leading: const Icon(Symbols.account_balance_sharp),
                    title: const Text(AppConfig.institute),
                    subtitle: Text(
                      _version.isEmpty
                          ? AppConfig.institution
                          : '${AppConfig.institution}\nVersion $_version',
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 0, 4, 10),
      child: Text(
        text.toUpperCase(),
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
          color: AppColors.textMuted,
          letterSpacing: 0.8,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.blueSoft,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text,
        style: const TextStyle(
          color: AppColors.blue,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _CloudProviderTile extends StatelessWidget {
  const _CloudProviderTile({
    required this.provider,
    required this.connected,
    required this.busy,
    this.userId,
    required this.onRefresh,
    required this.onConnect,
    required this.onDisconnect,
  });

  final CloudProvider provider;
  final bool connected;
  final bool busy;
  final String? userId;
  final VoidCallback onRefresh;
  final VoidCallback onConnect;
  final VoidCallback onDisconnect;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        ListTile(
          leading: Icon(
            provider.icon ?? Symbols.watch_sharp,
            color: connected ? AppColors.success : null,
          ),
          title: Text('${provider.displayName} (Cloud)'),
          subtitle: Text(
            connected
                ? (userId != null
                      ? 'Connected ($userId) - direct cloud sync active.'
                      : 'Connected — direct cloud sync active.')
                : provider.description,
          ),
          trailing: busy
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : IconButton(
                  tooltip: 'Check ${provider.name} connection status',
                  icon: const Icon(Symbols.refresh_sharp),
                  onPressed: onRefresh,
                ),
        ),
        if (!connected)
          ListTile(
            leading: const Icon(Symbols.add_link_sharp),
            title: Text('Connect ${provider.name} Cloud'),
            trailing: const Icon(Symbols.open_in_new_sharp, size: 20),
            onTap: busy ? null : onConnect,
          )
        else
          ListTile(
            leading: const Icon(Symbols.link_off_sharp, color: AppColors.coral),
            title: Text(
              'Remove ${provider.name} Cloud connection',
              style: const TextStyle(color: AppColors.coral),
            ),
            onTap: busy ? null : onDisconnect,
          ),
      ],
    );
  }
}
