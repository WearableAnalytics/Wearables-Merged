import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../app_config.dart';
import '../storage_service.dart';
import '../services/health_sync_service.dart';
import '../services/sync_activity_notifier.dart';
import '../state/app_state.dart';
import '../theme/app_theme.dart';
import '../utils/formatting.dart';
import '../widgets/brand_header.dart';
import '../widgets/study_code_entry.dart';
import '../widgets/study_info_link.dart';

/// First tab: welcome flow until a study code is linked, then the
/// connection status with a manual "share now" action.
class HomePage extends StatelessWidget {
  const HomePage({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: ListenableBuilder(
          listenable: state,
          builder: (context, _) {
            if (!state.loaded) {
              return const Center(child: CircularProgressIndicator());
            }
            return state.isLinked
                ? _ConnectedView(state: state)
                : _WelcomeView(state: state);
          },
        ),
      ),
    );
  }
}

class _WelcomeView extends StatelessWidget {
  const _WelcomeView({required this.state});

  final AppState state;

  Future<void> _link(BuildContext context, {required bool scan}) async {
    final code = scan
        ? await scanStudyCode(context)
        : await enterStudyCodeManually(context);
    if (code == null) return;
    // A newly linked participant always starts from the chosen period.
    await state.linkStudyCode(code, resetLastSync: true);
    await state.syncNow();
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(0, 8, 0, 24),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight - 40),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const BrandHeader(),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const SizedBox(height: 36),
                    const Center(
                      child: CharitePictogram('icon_smartphone', size: 112),
                    ),
                    const SizedBox(height: 32),
                    Text(
                      'Welcome to the\nCharité Wearables platform',
                      style: textTheme.headlineMedium,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Link this ${AppConfig.deviceName} with your personal code. You find the QR code '
                      'on the information sheet you received.',
                      style: textTheme.bodyLarge?.copyWith(
                        color: AppColors.textMuted,
                        height: 1.45,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 28),
                    const _Steps(),
                    const SizedBox(height: 32),
                    FilledButton.icon(
                      onPressed: () => _link(context, scan: true),
                      icon: const Icon(Symbols.qr_code_scanner_sharp),
                      label: const Text('Scan QR code'),
                    ),
                    const SizedBox(height: 8),
                    TextButton.icon(
                      onPressed: () => _link(context, scan: false),
                      icon: const Icon(Symbols.keyboard_sharp, size: 20),
                      label: const Text('Enter code manually'),
                    ),
                    if (AppConfig.studyInfoUrl.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      const Center(child: StudyInfoLink()),
                    ],
                    const SizedBox(height: 24),
                    const InstituteFooter(),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Steps extends StatelessWidget {
  const _Steps();

  @override
  Widget build(BuildContext context) {
    final steps = [
      (Symbols.qr_code_scanner_sharp, 'Scan your personal code'),
      (Symbols.favorite_sharp, 'Allow access to ${AppConfig.healthStore}'),
      (Symbols.sync_sharp, 'Data is shared automatically'),
    ];
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Column(
          children: [
            for (var i = 0; i < steps.length; i++)
              ListTile(
                leading: CircleAvatar(
                  radius: 16,
                  backgroundColor: AppColors.blueSoft,
                  child: Text(
                    '${i + 1}',
                    style: const TextStyle(
                      color: AppColors.blue,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                title: Text(steps[i].$2),
                trailing: Icon(steps[i].$1, color: AppColors.textMuted),
              ),
          ],
        ),
      ),
    );
  }
}

class _ConnectedView extends StatelessWidget {
  const _ConnectedView({required this.state});

  final AppState state;

  Future<void> _syncNow(BuildContext context) async {
    final result = await state.syncNow();
    if (!context.mounted || result == null) return;
    final message = switch (result.status) {
      HealthSyncStatus.success => 'Shared ${result.totalSent} data points.',
      HealthSyncStatus.partialSuccess =>
        'Shared ${result.totalSent} of ${result.totalAvailable} data points.'
            '${_reason(result)}',
      HealthSyncStatus.nothingToSend =>
        'Up to date. There is no new data to share.',
      HealthSyncStatus.protectedDataUnavailable =>
        'Unlock your ${AppConfig.deviceName} to share health data.',
      HealthSyncStatus.permissionDenied =>
        'Access to ${AppConfig.healthStore} is needed. '
            '${AppConfig.healthAccessHint}',
      HealthSyncStatus.codeRejected =>
        'Your personal code was rejected by the server (Unauthorized). Please scan a new QR code.',
      HealthSyncStatus.codeExpired =>
        'Your personal code has expired. Please scan your QR code again.',
      HealthSyncStatus.failed =>
        'Sharing failed. Please try again later.${_reason(result)}',
    };
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  /// Links the newly scanned code and continues where sharing stopped.
  Future<void> _rescan(BuildContext context) async {
    final code = await scanStudyCode(context);
    if (code == null) return;
    await state.linkStudyCode(code, resetLastSync: false);
    if (context.mounted) await _syncNow(context);
  }

  /// Short server or network reason, e.g. "Status 422".
  String _reason(HealthSyncResult result) {
    final error = result.lastError;
    if (error == null) return '';
    final status = RegExp(r'Status (\d{3})').firstMatch(error)?.group(0);
    return ' (${status ?? error.split('\n').first})';
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final expired = !state.isSyncing && state.codeExpired;
    final rejected = !state.isSyncing && state.codeRejected;
    final failed =
        expired ||
        rejected ||
        (!state.isSyncing && state.lastOutcome == SyncOutcome.failure);
    final incomplete =
        !state.isSyncing &&
        !failed &&
        (state.lastOutcome == SyncOutcome.incomplete || state.isBehind);
    final sharedUpTo = state.lastSendTime == null
        ? ''
        : formatDate(state.lastSendTime!);

    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(0, 8, 0, 24),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight - 40),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const BrandHeader(),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const SizedBox(height: 40),
                    Center(
                      child: _StatusBadge(
                        syncing: state.isSyncing,
                        progress: state.progress,
                        failed: failed,
                        incomplete: incomplete,
                        expired: expired || rejected,
                      ),
                    ),
                    const SizedBox(height: 28),
                    Text(
                      state.isSyncing
                          ? 'Sharing your data…'
                          : rejected
                          ? 'Personal code rejected'
                          : expired
                          ? 'Personal code expired'
                          : failed
                          ? 'Last upload failed'
                          : incomplete
                          ? 'Not fully shared yet'
                          : 'You are connected',
                      style: textTheme.headlineMedium,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 10),
                    Text(
                      state.isSyncing
                          ? 'Please keep the app open until sharing has finished. '
                                'Progress is saved, so it continues where it stopped.'
                          : rejected
                          ? 'The server refused your code (Unauthorized). '
                                'Please scan a valid personal QR code again to continue.'
                          : expired
                          ? 'New data cannot be shared with your current code. '
                                'Please scan the QR code on your information sheet '
                                'again to continue.'
                          : incomplete
                          ? 'Your data is shared up to $sharedUpTo. Tap Share now '
                                'to continue from there.'
                          : failed
                          ? 'Your data will be sent again automatically. You can also '
                                'try it now.'
                          : 'Your ${AppConfig.healthStore} data is shared securely with the '
                                'Charité Wearables platform.',
                      style: textTheme.bodyLarge?.copyWith(
                        color: AppColors.textMuted,
                        height: 1.45,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    if (kDebugMode &&
                        StorageService.codeEndpoint(state.deviceId) !=
                            null) ...[
                      const SizedBox(height: 12),
                      Builder(
                        builder: (context) {
                          final endpoint = StorageService.codeEndpoint(
                            state.deviceId,
                          )!;
                          final isHttp = endpoint.toLowerCase().startsWith(
                            'http://',
                          );

                          if (isHttp) {
                            return Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 12,
                                vertical: 8,
                              ),
                              decoration: BoxDecoration(
                                color: const Color(0xFFFFF3CD),
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(
                                  color: const Color(0xFFFFEEBA),
                                ),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(
                                    Symbols.warning_amber_rounded,
                                    size: 16,
                                    color: Color(0xFF856404),
                                  ),
                                  const SizedBox(width: 8),
                                  Flexible(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        const Text(
                                          'Local Dev Endpoint (HTTP unencrypted):',
                                          style: TextStyle(
                                            fontSize: 10,
                                            fontWeight: FontWeight.bold,
                                            color: Color(0xFF856404),
                                          ),
                                        ),
                                        const SizedBox(height: 2),
                                        Text(
                                          endpoint,
                                          style: const TextStyle(
                                            fontSize: 11,
                                            fontFamily: 'Menlo',
                                            color: Color(0xFF856404),
                                          ),
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                            );
                          }

                          return Text(
                            'Dev Endpoint: $endpoint',
                            style: const TextStyle(
                              fontSize: 11,
                              fontFamily: 'Menlo',
                              color: AppColors.blue,
                            ),
                            textAlign: TextAlign.center,
                          );
                        },
                      ),
                    ],
                    const SizedBox(height: 36),
                    Row(
                      children: [
                        Expanded(
                          child: _InfoTile(
                            icon: Symbols.schedule_sharp,
                            label: 'Shared up to',
                            value: state.lastSendTime == null
                                ? 'Not yet'
                                : formatRelative(state.lastSendTime!),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _InfoTile(
                            icon: Symbols.autorenew_sharp,
                            label: 'Automatic sharing',
                            value: (expired || rejected) ? 'Paused' : 'On',
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 28),
                    if (expired || rejected)
                      FilledButton.icon(
                        onPressed: () => _rescan(context),
                        icon: const Icon(Symbols.qr_code_scanner_sharp),
                        label: const Text('Scan QR code'),
                      )
                    else
                      FilledButton.icon(
                        onPressed: state.isSyncing
                            ? null
                            : () => _syncNow(context),
                        icon: const Icon(Symbols.sync_sharp),
                        label: Text(state.isSyncing ? 'Sharing…' : 'Share now'),
                      ),
                    const SizedBox(height: 12),
                    Text(
                      state.lastSendTime == null
                          ? 'The first upload covers everything since '
                                '${formatDate(state.initialSyncStart)}.'
                          : 'Only data recorded since the last upload is shared.',
                      style: textTheme.bodySmall,
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({
    required this.syncing,
    required this.failed,
    this.incomplete = false,
    this.expired = false,
    this.progress,
  });

  final bool syncing;
  final bool failed;
  final bool incomplete;
  final bool expired;
  final double? progress;

  @override
  Widget build(BuildContext context) {
    final color = failed
        ? AppColors.coral
        : incomplete
        ? AppColors.lightBlue
        : AppColors.success;
    final soft = syncing
        ? AppColors.blueSoft
        : failed
        ? AppColors.coralSoft
        : incomplete
        ? AppColors.blueSoft
        : AppColors.successSoft;
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      child: SizedBox(
        key: ValueKey('$syncing-$failed-$incomplete-$expired'),
        width: 168,
        height: 168,
        child: Stack(
          alignment: Alignment.center,
          children: [
            Container(
              decoration: BoxDecoration(color: soft, shape: BoxShape.circle),
            ),
            if (syncing)
              SizedBox(
                width: 148,
                height: 148,
                child: CircularProgressIndicator(
                  value: progress,
                  strokeWidth: 6,
                  strokeCap: StrokeCap.round,
                  color: AppColors.blue,
                  backgroundColor: AppColors.lightBlue.withValues(alpha: 0.2),
                ),
              ),
            Container(
              width: 112,
              height: 112,
              decoration: BoxDecoration(
                color: syncing ? AppColors.lightBlue : color,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: (syncing ? AppColors.lightBlue : color).withValues(
                      alpha: 0.35,
                    ),
                    blurRadius: 24,
                    offset: const Offset(0, 10),
                  ),
                ],
              ),
              child: syncing && progress != null
                  ? Center(
                      child: Text(
                        '${(progress! * 100).floor()} %',
                        style: Theme.of(context).textTheme.headlineSmall
                            ?.copyWith(color: Colors.white),
                      ),
                    )
                  : Icon(
                      syncing
                          ? Symbols.sync_sharp
                          : expired
                          ? Symbols.qr_code_scanner_sharp
                          : failed
                          ? Symbols.priority_high_sharp
                          : incomplete
                          ? Symbols.pause_sharp
                          : Symbols.check_sharp,
                      size: 64,
                      color: Colors.white,
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoTile extends StatelessWidget {
  const _InfoTile({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 20, color: AppColors.lightBlue),
            const SizedBox(height: 10),
            Text(label, style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 2),
            Text(value, style: Theme.of(context).textTheme.titleMedium),
          ],
        ),
      ),
    );
  }
}
