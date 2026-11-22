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

class _UploadHistoryPageState extends State<UploadHistoryPage> {
  late final entries = StorageService.getUploadReceipts(widget.token);
  final updated = <String, Map<String, dynamic>>{};
  final checking = <String>{};
  final errors = <String>{};

  Future<void> refresh(Map<String, dynamic> receipt) async {
    final id = receipt['acceptanceId'] as String;
    setState(() {
      checking.add(id);
      errors.remove(id);
    });
    final client = HttpClient();
    try {
      final token = widget.token;
      if (await StorageService.getOrCreateDeviceId() != token ||
          StorageService.isCodeExpired(token) ||
          await StorageService.isLinkedCodeRejected()) {
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
      if (mounted) setState(() => updated[id] = current);
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
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: entries,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return const Center(child: Text('Could not load saved receipts.'));
          }
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final rows = snapshot.data!;
          if (rows.isEmpty) {
            return const Center(
              child: Text('No uploads saved for this study link.'),
            );
          }
          final ordered = [...rows]
            ..sort(
              (a, b) => (b['receivedAt'] as String? ?? '').compareTo(
                a['receivedAt'] as String? ?? '',
              ),
            );
          return ListView.builder(
            itemCount: ordered.length,
            itemBuilder: (context, index) {
              final id = ordered[index]['acceptanceId'] as String;
              final r = updated[id] ?? ordered[index];
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
        },
      ),
    );
  }
}
