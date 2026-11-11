import 'package:flutter/material.dart';

import '../app_config.dart';
import '../services/cloud_connector_service.dart';
import '../state/app_state.dart';

/// Prompts the user whether to sync local health data in parallel with the cloud provider or use the cloud connection only
Future<bool?> promptSyncModeAfterConnect(
  BuildContext context,
  AppState state,
  CloudProvider provider,
) async {
  final keepLocal = await showDialog<bool>(
    context: context,
    useRootNavigator: true,
    builder: (ctx) => AlertDialog(
      title: Text('${provider.name} Cloud connected'),
      content: Text(
        '${provider.name} now sends your wearable data directly via the cloud without needing phone uploads.\n\n'
        'Do you also want to continue syncing ${AppConfig.healthStore} in parallel, or use ${provider.name} Cloud only?',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: Text('${provider.name} Cloud only'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
          onPressed: () => Navigator.pop(ctx, true),
          child: Text('Both (${AppConfig.healthStore} + Cloud)'),
        ),
      ],
    ),
  );
  if (keepLocal == null) return null;
  await state.setLocalHealthSyncEnabled(keepLocal);
  if (context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          keepLocal
              ? 'Parallel sync active (${AppConfig.healthStore} + ${provider.name} Cloud).'
              : '${provider.name} Cloud-only mode active. Local phone uploads paused.',
        ),
      ),
    );
  }
  return keepLocal;
}
