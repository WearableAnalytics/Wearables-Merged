import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import '../services/health_sync_service.dart';
import '../services/health_upload.dart';
import '../storage_service.dart';

class UploadHistoryPage extends StatefulWidget {
  const UploadHistoryPage({super.key, required this.token});
  final String token;

  @override
  State<UploadHistoryPage> createState() => _UploadHistoryPageState();
}

class _UploadHistoryPageState extends State<UploadHistoryPage>
    with WidgetsBindingObserver {
  List<Map<String, dynamic>>? rows;
  bool loadError = false;
  final checking = <String>{};
  final errors = <String>{};
  StreamSubscription<void>? changes;
  Timer? timer;
  Timer? reloadSoon;
  int cursor = 0;
  int generation = 0;
  bool foreground = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    changes = StorageService.receiptChanges(widget.token).listen((_) {
      if (foreground) {
        reloadSoon ??= Timer(const Duration(milliseconds: 150), () {
          reloadSoon = null;
          unawaited(reload());
        });
      }
    });
    start();
  }

  void start() {
    foreground = true;
    unawaited(reload(checkPending: true));
    timer ??= Timer.periodic(
      const Duration(seconds: 15),
      (_) => reload(checkPending: true),
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      start();
    } else {
      foreground = false;
      timer?.cancel();
      timer = null;
      reloadSoon?.cancel();
      reloadSoon = null;
    }
  }

  Future<void> reload({bool checkPending = false}) async {
    final version = ++generation;
    try {
      final saved = await StorageService.getUploadReceipts(
        widget.token,
        currentEnrollmentOnly: true,
      );
      if (!mounted || generation != version || !foreground) return;
      saved.sort(
        (a, b) => (b['receivedAt'] as String? ?? '').compareTo(
          a['receivedAt'] as String? ?? '',
        ),
      );
      setState(() {
        rows = saved;
        loadError = false;
      });
      if (checkPending &&
          checking.isEmpty &&
          await StorageService.currentStudyMatches(widget.token)) {
        if (!mounted ||
            !foreground ||
            generation != version ||
            checking.isNotEmpty) {
          return;
        }
        final pending = saved
            .where(
              (r) => const {
                'awaiting-delivery',
                'awaiting-processing',
                'awaiting-storage',
              }.contains(r['processingState']),
            )
            .toList();
        if (pending.isNotEmpty) {
          await refresh(pending[cursor++ % pending.length]);
        }
      }
    } catch (_) {
      if (mounted && generation == version) setState(() => loadError = true);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    changes?.cancel();
    timer?.cancel();
    reloadSoon?.cancel();
    super.dispose();
  }

  Future<void> refresh(Map<String, dynamic> receipt) async {
    final id = receipt['acceptanceId'] as String;
    setState(() {
      checking.add(id);
      errors.remove(id);
    });
    final client = HttpClient();
    try {
      final token = widget.token;
      if (!await StorageService.currentStudyMatches(token)) {
        throw StateError('Study link unavailable');
      }
      final sender = HealthUploader(
        client: client,
        endpoint: HealthSyncService().endpointFor(token),
      );
      final status = await sender.status(id, token);
      if (status['rawSha256'] != receipt['rawSha256'] ||
          status['readingCount'] != receipt['readingCount']) {
        throw const FormatException(
          'Receipt no longer matches the accepted upload',
        );
      }
      final current = {
        ...receipt,
        ...status,
        'checkedAt': DateTime.now().toUtc().toIso8601String(),
      };
      await StorageService.saveUploadReceipt(token, current);
    } catch (_) {
      if (mounted) setState(() => errors.add(id));
    } finally {
      client.close(force: true);
      if (mounted) setState(() => checking.remove(id));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Upload history')),
      body: buildReceipts(),
    );
  }

  Widget buildReceipts() {
    final ordered = rows;
    if (loadError && ordered == null) {
      return const Center(child: Text('Could not load saved receipts.'));
    }
    if (ordered == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (ordered.isEmpty) {
      return const Center(child: Text('No uploads saved for this study link.'));
    }
    return ListView.builder(
      itemCount: ordered.length,
      itemBuilder: (context, index) {
        final id = ordered[index]['acceptanceId'] as String;
        final r = ordered[index];
        final stored = r['storedConfirmedCount'];
        final total = r['recordCount'] ?? r['readingCount'];
        final state = r['processingState'];
        final checked = DateTime.tryParse(
          r['checkedAt'] as String? ?? '',
        )?.toLocal();
        return ListTile(
          title: Text(
            '${r['sourceLabel'] ?? 'Study upload'} · ${r['readingCount']} readings',
          ),
          subtitle: Text(
            [
              if (stored is int)
                'Storage confirmed: $stored of $total'
              else
                'Upload accepted',
              if (state != null && state != 'storage-observed')
                'Processing: $state',
              if (checked != null)
                'Last checked: ${MaterialLocalizations.of(context).formatShortDate(checked)} ${TimeOfDay.fromDateTime(checked).format(context)}',
              'Receipt $id',
              if (errors.contains(id))
                'Refresh unavailable. Showing the last saved receipt.',
            ].join('\n'),
          ),
          trailing: IconButton(
            tooltip: 'Refresh storage status',
            icon: const Icon(Icons.refresh),
            onPressed:
                checking.contains(id) ||
                    StorageService.isCodeExpired(widget.token)
                ? null
                : () => refresh(r),
          ),
        );
      },
    );
  }
}
