import 'package:flutter/material.dart';

import '../app_config.dart';
import '../services/cloud_connector_service.dart';
import '../state/app_state.dart';

Future<bool?> _applySyncModeChoice(
  BuildContext context,
  AppState state,
  bool? keepLocal,
) async {
  if (keepLocal == null) {
    await state.load();
    return null;
  }
  await state.setLocalHealthSyncEnabled(keepLocal);
  await state.load();
  if (context.mounted) {
    final label = state.cloudTileLabel;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          keepLocal
              ? 'Parallel sync active (${AppConfig.healthStore} + $label).'
              : '$label-only mode active. Local phone uploads paused.',
        ),
      ),
    );
  }
  return keepLocal;
}

/// Prompts the user whether to sync local health data in parallel with cloud connections or use cloud only
Future<bool?> promptSyncModeAfterConnect(
  BuildContext context,
  AppState state,
  CloudProvider provider,
) async {
  final multipleActive = state.connectedCloudProviders.length > 1;
  final names = state.cloudNamesList;
  final keepLocal = await showDialog<bool>(
    context: context,
    useRootNavigator: true,
    builder: (ctx) => AlertDialog(
      title: Text('${provider.name} Cloud connected'),
      content: Text(
        multipleActive
            ? '$names now send your wearable data directly via the cloud without needing phone uploads.\n\n'
                  'Do you also want to continue syncing ${AppConfig.healthStore} in parallel, or use Cloud only?'
            : '${provider.name} now sends your wearable data directly via the cloud without needing phone uploads.\n\n'
                  'Do you also want to continue syncing ${AppConfig.healthStore} in parallel, or use ${provider.name} Cloud only?',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: Text(
            multipleActive ? 'Cloud only' : '${provider.name} Cloud only',
          ),
        ),
        FilledButton(
          style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
          onPressed: () => Navigator.pop(ctx, true),
          child: Text('Both (${AppConfig.healthStore} + Cloud)'),
        ),
      ],
    ),
  );
  if (!context.mounted) return keepLocal;
  return _applySyncModeChoice(context, state, keepLocal);
}

/// Prompts once after restoring existing cloud connections (e.g. reinstall or QR rescan)
Future<bool?> promptSyncModeAfterRestore(
  BuildContext context,
  AppState state,
  List<CloudProvider> restored,
) async {
  if (restored.isEmpty) return null;
  if (restored.length == 1) {
    return promptSyncModeAfterConnect(context, state, restored.first);
  }
  final names = restored.map((p) => p.name).join(', ');
  final keepLocal = await showDialog<bool>(
    context: context,
    useRootNavigator: true,
    builder: (ctx) => AlertDialog(
      title: Text('${restored.length} cloud connections restored'),
      content: Text(
        'Your existing cloud connections ($names) send wearable data directly via the cloud without needing phone uploads.\n\n'
        'Do you also want to sync ${AppConfig.healthStore} in parallel, or use Cloud only?',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('Cloud only'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
          onPressed: () => Navigator.pop(ctx, true),
          child: Text('Both (${AppConfig.healthStore} + Cloud)'),
        ),
      ],
    ),
  );
  if (!context.mounted) return keepLocal;
  return _applySyncModeChoice(context, state, keepLocal);
}
