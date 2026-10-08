import 'package:flutter/material.dart';

import '../screens/qr_scan_page.dart';
import '../storage_service.dart';
import '../theme/app_theme.dart';

/// Opens the camera scanner and returns a valid study code, or null.
Future<String?> scanStudyCode(BuildContext context) async {
  final value = await Navigator.of(context).push<String>(
    MaterialPageRoute(builder: (_) => const QrScanPage()),
  );
  if (!context.mounted || value == null) return null;
  return _validated(context, value);
}

/// Asks for the study code as text and returns it if valid, or null.
Future<String?> enterStudyCodeManually(BuildContext context) async {
  final controller = TextEditingController();
  final value = await showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    backgroundColor: AppColors.surface,
    builder: (ctx) => Padding(
      padding: EdgeInsets.fromLTRB(
        24,
        0,
        24,
        24 + MediaQuery.of(ctx).viewInsets.bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Enter study code', style: Theme.of(ctx).textTheme.titleLarge),
          const SizedBox(height: 8),
          Text(
            'Paste the code from your study information sheet or the study '
            'portal. It is a long sequence of letters and numbers.',
            style: Theme.of(ctx).textTheme.bodyMedium?.copyWith(
                  color: AppColors.textMuted,
                ),
          ),
          const SizedBox(height: 20),
          TextField(
            controller: controller,
            autofocus: true,
            minLines: 3,
            maxLines: 5,
            style: const TextStyle(fontFamily: 'Menlo', fontSize: 13),
            decoration: InputDecoration(
              hintText: 'eyJhbGciOi…',
              filled: true,
              fillColor: AppColors.background,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide.none,
              ),
            ),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(controller.text),
            child: const Text('Link study code'),
          ),
        ],
      ),
    ),
  );
  WidgetsBinding.instance.addPostFrameCallback((_) => controller.dispose());
  if (!context.mounted || value == null) return null;
  return _validated(context, value);
}

String? _validated(BuildContext context, String raw) {
  final value = raw.trim();
  if (value.isEmpty) return null;
  if (!StorageService.isStudyCode(value)) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(
          'That does not look like a study code. Please check it and try again.',
        ),
      ),
    );
    return null;
  }
  return value;
}
