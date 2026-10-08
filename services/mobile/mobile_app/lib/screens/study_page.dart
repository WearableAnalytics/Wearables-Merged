import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../app_config.dart';
import '../state/app_state.dart';
import '../theme/app_theme.dart';
import '../utils/formatting.dart';
import '../widgets/study_code_entry.dart';
import '../widgets/study_info_link.dart';

/// Third tab: the linked study code, sharing options and app information.
class StudyPage extends StatefulWidget {
  const StudyPage({super.key, required this.state});

  final AppState state;

  @override
  State<StudyPage> createState() => _StudyPageState();
}

class _StudyPageState extends State<StudyPage> {
  bool _showCode = false;
  String _version = '';

  AppState get state => widget.state;

  @override
  void initState() {
    super.initState();
    PackageInfo.fromPlatform().then((info) {
      if (mounted) {
        setState(() => _version = '${info.version} (${info.buildNumber})');
      }
    });
  }

  Future<void> _changeCode({required bool scan}) async {
    final code = scan
        ? await scanStudyCode(context)
        : await enterStudyCodeManually(context);
    if (code == null || !mounted) return;
    if (code == state.deviceId) {
      _toast('This study code is already linked.');
      return;
    }
    final reset = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Link new study code?'),
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
    _toast('New study code linked.');
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
    _toast('The next upload will start from ${formatDate(state.initialSyncStart)}.');
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
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  String _masked(String code) {
    if (code.length <= 12) return code;
    return '${code.substring(0, 6)}••••••${code.substring(code.length - 6)}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Study')),
      body: ListenableBuilder(
        listenable: state,
        builder: (context, _) => ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
          children: [
            _SectionLabel('Study code'),
            Card(
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Icons.verified_user_outlined),
                    title: Text(state.isLinked ? 'Linked' : 'Not linked'),
                    subtitle: Text(
                      state.isLinked
                          ? (_showCode ? state.deviceId : _masked(state.deviceId))
                          : 'Scan the QR code from your study team.',
                      style: _showCode
                          ? const TextStyle(fontFamily: 'Menlo', fontSize: 11)
                          : null,
                    ),
                    trailing: state.isLinked
                        ? IconButton(
                            tooltip: _showCode ? 'Hide code' : 'Show code',
                            icon: Icon(
                              _showCode
                                  ? Icons.visibility_off_outlined
                                  : Icons.visibility_outlined,
                            ),
                            onPressed: () =>
                                setState(() => _showCode = !_showCode),
                          )
                        : null,
                  ),
                  const Divider(indent: 20, endIndent: 20),
                  ListTile(
                    leading: const Icon(Icons.qr_code_scanner_rounded),
                    title: const Text('Scan new QR code'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => _changeCode(scan: true),
                  ),
                  ListTile(
                    leading: const Icon(Icons.keyboard_alt_outlined),
                    title: const Text('Enter code manually'),
                    trailing: const Icon(Icons.chevron_right_rounded),
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
                    leading: const Icon(Icons.schedule_rounded),
                    title: const Text('Last shared'),
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
                    data: Theme.of(context).copyWith(
                      dividerColor: Colors.transparent,
                    ),
                    child: ExpansionTile(
                      leading: const Icon(Icons.tune_rounded),
                      title: const Text('More settings'),
                      tilePadding: const EdgeInsets.symmetric(horizontal: 20),
                      childrenPadding: const EdgeInsets.only(bottom: 8),
                      iconColor: AppColors.navy,
                      children: [
                        ListTile(
                          leading: const Icon(Icons.event_rounded),
                          title: const Text('Share data from'),
                          subtitle: const Text(
                            'Start of the first upload and of uploads after a reset.',
                          ),
                          trailing: _Pill(formatDate(state.initialSyncStart)),
                          onTap: _pickStartDate,
                        ),
                        ListTile(
                          leading: const Icon(Icons.restart_alt_rounded),
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
            _SectionLabel('About'),
            Card(
              child: Column(
                children: [
                  if (AppConfig.studyInfoUrl.isNotEmpty) ...[
                    ListTile(
                      leading: const Icon(Icons.info_outline_rounded),
                      title: const Text('About the wearables study'),
                      trailing: const Icon(Icons.open_in_new_rounded, size: 20),
                      onTap: openStudyInfo,
                    ),
                    const Divider(indent: 20, endIndent: 20),
                  ],
                  ListTile(
                    leading: const Icon(Icons.account_balance_outlined),
                    title: const Text(AppConfig.institution),
                    subtitle: Text(_version.isEmpty ? '' : 'Version $_version'),
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
        color: AppColors.skySoft,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text,
        style: const TextStyle(
          color: AppColors.navy,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
