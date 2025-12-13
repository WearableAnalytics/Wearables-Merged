import 'dart:async';

import 'package:flutter/material.dart';

import '../services/sync_activity_notifier.dart';

enum _SendingStatusState {
  idle,
  sending,
  sentFull,
  sentIconOnly,
  nothingToSendFull,
  nothingToSendIconOnly,
  errorFull,
  errorIconOnly,
}

class SendingStatusOverlay extends StatefulWidget {
  const SendingStatusOverlay({
    super.key,
    this.padding = const EdgeInsets.all(12),
    this.useSafeArea = true,
  });

  final EdgeInsets padding;
  final bool useSafeArea;

  @override
  State<SendingStatusOverlay> createState() => _SendingStatusOverlayState();
}

class _SendingStatusOverlayState extends State<SendingStatusOverlay> {
  _SendingStatusState _status = _SendingStatusState.idle;
  Timer? _successTimer;

  @override
  void initState() {
    super.initState();
    _status =
        SyncActivityNotifier.isSyncing.value ? _SendingStatusState.sending : _SendingStatusState.idle;
    SyncActivityNotifier.isSyncing.addListener(_handleSyncChange);
  }

  @override
  void dispose() {
    SyncActivityNotifier.isSyncing.removeListener(_handleSyncChange);
    _successTimer?.cancel();
    super.dispose();
  }

  void _handleSyncChange() {
    final isSyncing = SyncActivityNotifier.isSyncing.value;
    if (isSyncing) {
      _successTimer?.cancel();
      setState(() => _status = _SendingStatusState.sending);
      return;
    }

    // Sync just finished; pick the right end state before collapsing to the icon-only pill.
    final outcome = SyncActivityNotifier.lastResult.value;
    _successTimer?.cancel();
    if (outcome == SyncOutcome.nothingToSend) {
      setState(() => _status = _SendingStatusState.nothingToSendFull);
      _successTimer = Timer(const Duration(seconds: 2), () {
        if (!mounted) return;
        setState(() => _status = _SendingStatusState.nothingToSendIconOnly);
      });
    } else if (outcome == SyncOutcome.failure) {
      setState(() => _status = _SendingStatusState.errorFull);
      _successTimer = Timer(const Duration(seconds: 2), () {
        if (!mounted) return;
        setState(() => _status = _SendingStatusState.errorIconOnly);
      });
    } else {
      setState(() => _status = _SendingStatusState.sentFull);
      _successTimer = Timer(const Duration(seconds: 2), () {
        if (!mounted) return;
        setState(() => _status = _SendingStatusState.sentIconOnly);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final content = Padding(
      padding: widget.padding,
      child: Align(
        alignment: Alignment.topLeft,
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 250),
          child: switch (_status) {
            _SendingStatusState.idle => const SizedBox.shrink(),
            _SendingStatusState.sending => _SendingContainer(
                key: const ValueKey('sending'),
                background: colorScheme.primaryContainer.withOpacity(0.85),
                foreground: colorScheme.onPrimaryContainer,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.5,
                        color: colorScheme.primary,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'Sending',
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(
                            fontWeight: FontWeight.w700,
                            color: colorScheme.onPrimaryContainer,
                          ),
                    ),
                  ],
                ),
              ),
            _SendingStatusState.sentFull => _SendingContainer(
                key: const ValueKey('sent-full'),
                background: Colors.green.shade600,
                foreground: Colors.white,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.check, size: 20, color: Colors.white),
                    const SizedBox(width: 8),
                    Text(
                      'Sent',
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(
                            fontWeight: FontWeight.w700,
                            color: Colors.white,
                          ),
                    ),
                  ],
                ),
              ),
            _SendingStatusState.sentIconOnly => Container(
                key: const ValueKey('sent-icon'),
                height: 36,
                width: 36,
                decoration: BoxDecoration(
                  color: Colors.green.shade600,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.08),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: const Icon(
                  Icons.check,
                  size: 20,
                  color: Colors.white,
                ),
              ),
            _SendingStatusState.nothingToSendFull => _SendingContainer(
                key: const ValueKey('nothing-to-send'),
                background: Colors.green.shade600,
                foreground: Colors.white,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.check, size: 20, color: Colors.white),
                    const SizedBox(width: 8),
                    Text(
                      'Nothing to send',
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(
                            fontWeight: FontWeight.w700,
                            color: Colors.white,
                          ),
                    ),
                  ],
                ),
              ),
            _SendingStatusState.nothingToSendIconOnly => Container(
                key: const ValueKey('nothing-to-send-icon'),
                height: 36,
                width: 36,
                decoration: BoxDecoration(
                  color: Colors.green.shade600,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.08),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: const Icon(
                  Icons.check,
                  size: 20,
                  color: Colors.white,
                ),
              ),
            _SendingStatusState.errorFull => _SendingContainer(
                key: const ValueKey('send-error'),
                background: Colors.red.shade600,
                foreground: Colors.white,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error, size: 20, color: Colors.white),
                    const SizedBox(width: 8),
                    Text(
                      'Sync failed',
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(
                            fontWeight: FontWeight.w700,
                            color: Colors.white,
                          ),
                    ),
                  ],
                ),
              ),
            _SendingStatusState.errorIconOnly => Container(
                key: const ValueKey('send-error-icon'),
                height: 36,
                width: 36,
                decoration: BoxDecoration(
                  color: Colors.red.shade600,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.08),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: const Icon(
                  Icons.error,
                  size: 20,
                  color: Colors.white,
                ),
              ),
          },
        ),
      ),
    );

    if (!widget.useSafeArea) return content;
    return SafeArea(child: content);
  }
}

class _SendingContainer extends StatelessWidget {
  const _SendingContainer({
    super.key,
    required this.background,
    required this.foreground,
    required this.child,
  });

  final Color background;
  final Color foreground;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: 12,
        vertical: 8,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.08),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: IconTheme(
        data: IconThemeData(color: foreground),
        child: child,
      ),
    );
  }
}
