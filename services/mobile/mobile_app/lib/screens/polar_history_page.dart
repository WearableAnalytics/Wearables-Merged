import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/cloud_connector_service.dart';
import '../storage_service.dart';

class PolarHistoryPage extends StatefulWidget {
  const PolarHistoryPage({super.key, required this.token});
  final String token;
  @override
  State<PolarHistoryPage> createState() => _PolarHistoryPageState();
}

class _PolarHistoryPageState extends State<PolarHistoryPage> {
  static const categories = {
    'pulse': 'Continuous heart rate',
    'activity': 'Steps and activity intensity',
    'training': 'Workout duration, distance and energy',
    'sleep': 'Sleep stages and score',
    'recovery': 'Nightly breathing rate and mean RMSSD',
    'temperature': 'Skin temperature',
    'intervals': 'Pulse intervals and quality',
    'contact': 'Skin contact',
  };
  final selected = <String>{};
  final zone = TextEditingController(text: 'Europe/Berlin');
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 15);
  late final base = CloudConnectorService().baseUriFor(widget.token);
  DateTime day = DateTime.now();
  String? session;
  Map<String, dynamic>? preview;
  bool busy = false;
  bool shared = false;
  String message = '';

  Future<dynamic> request(String method, String path, [Object? body]) async {
    final endpoint = base.replace(
      path: '${base.path.replaceFirst(RegExp(r"/$"), "")}/polar/$path',
    );
    final req = await client.openUrl(method, endpoint);
    req.followRedirects = false;
    req.headers.set(HttpHeaders.authorizationHeader, 'Bearer ${widget.token}');
    if (body != null) {
      req.headers.contentType = ContentType.json;
      req.write(jsonEncode(body));
    }
    final response = await req.close().timeout(const Duration(minutes: 3));
    final raw = await response
        .transform(utf8.decoder)
        .join()
        .timeout(const Duration(seconds: 30));
    if (response.statusCode == 503 && path == 'sessions') {
      throw const HttpException(
        'Polar Flow import is unavailable on this study server.',
      );
    }
    if (response.statusCode >= 400) {
      throw HttpException('HTTP ${response.statusCode}');
    }
    return raw.isEmpty ? null : jsonDecode(raw);
  }

  Future<void> act(Future<void> Function() task) async {
    setState(() {
      busy = true;
      message = '';
    });
    try {
      await task();
    } catch (e) {
      if (mounted) {
        message = e is HttpException
            ? 'Request failed (${e.message}). Check the connection or start a new authorization.'
            : 'Request could not be completed.';
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> authorize() async {
    final result = await request('POST', 'sessions', {
      'day': day.toIso8601String().split('T').first,
      'timezone': zone.text.trim(),
      'streams': selected.toList(),
    });
    if (!mounted) return;
    session = result['session'] as String;
    final url = Uri.parse(result['url'] as String);
    if (url.origin != 'https://auth.polar.com' ||
        url.path != '/oauth/authorize' ||
        !await launchUrl(url, mode: LaunchMode.externalApplication)) {
      throw const FormatException('Invalid Polar authorization URL');
    }
    message =
        'After authorizing in Polar, return here and preview the readings.';
  }

  @override
  void dispose() {
    client.close(force: true);
    zone.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Polar Flow history')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (session == null) ...[
            ListTile(
              title: const Text('Recording date'),
              subtitle: Text(day.toIso8601String().split('T').first),
              onTap: busy
                  ? null
                  : () async {
                      final picked = await showDatePicker(
                        context: context,
                        initialDate: day,
                        firstDate: DateTime(2010),
                        lastDate: DateTime.now(),
                      );
                      if (picked != null && mounted) {
                        setState(() => day = picked);
                      }
                    },
            ),
            TextField(
              controller: zone,
              enabled: !busy,
              decoration: const InputDecoration(
                labelText: 'Recording time zone (IANA)',
              ),
            ),
            for (final entry in categories.entries)
              CheckboxListTile(
                title: Text(entry.value),
                value: selected.contains(entry.key),
                onChanged: busy
                    ? null
                    : (v) => setState(() {
                        if (v == true) {
                          selected.add(entry.key);
                        } else {
                          selected.remove(entry.key);
                        }
                      }),
              ),
            FilledButton(
              onPressed: busy || selected.isEmpty ? null : () => act(authorize),
              child: const Text('Authorize in Polar Flow'),
            ),
          ] else if (preview == null)
            FilledButton(
              onPressed: busy
                  ? null
                  : () => act(() async {
                      preview = Map<String, dynamic>.from(
                        await request('POST', 'sessions/$session/preview'),
                      );
                      if (preview!.isEmpty) {
                        message =
                            'No supported readings found. Check your date and sync your watch in Polar Flow.';
                      }
                    }),
              child: const Text('Preview readings'),
            ),
          if (preview != null) ...[
            for (final entry in preview!.entries)
              ListTile(
                title: Text(entry.key.toLowerCase().replaceAll('_', ' ')),
                trailing: Text('${entry.value}'),
              ),
            if (!shared && preview!.isNotEmpty)
              FilledButton(
                onPressed: busy
                    ? null
                    : () => act(() async {
                        final result = await request(
                          'POST',
                          'sessions/$session/share',
                        );
                        final receipts = (result['receipts'] as List)
                            .cast<String>();
                        for (final detail
                            in result['receiptDetails'] as List? ?? const []) {
                          await StorageService.saveUploadReceipt(widget.token, {
                            ...Map<String, dynamic>.from(detail as Map),
                            'sourceLabel': 'Polar Flow',
                            'receivedAt': DateTime.now()
                                .toUtc()
                                .toIso8601String(),
                          });
                        }
                        message =
                            'Accepted for processing. Receipts: ${receipts.join(", ")}';
                        shared = true;
                      }),
                child: Text('Share with linked study via ${base.host}'),
              ),
          ],
          if (session != null)
            TextButton(
              onPressed: busy
                  ? null
                  : () => act(() async {
                      try {
                        await request('DELETE', 'sessions/$session');
                      } finally {
                        session = null;
                        preview = null;
                        shared = false;
                      }
                    }),
              child: const Text('End session'),
            ),
          if (busy) const LinearProgressIndicator(),
          if (message.isNotEmpty) Text(message),
        ],
      ),
    );
  }
}
