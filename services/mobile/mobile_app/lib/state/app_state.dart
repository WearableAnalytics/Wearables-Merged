import 'package:flutter/foundation.dart';

import '../services/health_sync_service.dart';
import '../services/sync_activity_notifier.dart';
import '../storage_service.dart';

/// Shared, listenable view of the study link and sync state for all tabs.
class AppState extends ChangeNotifier {
  AppState({HealthSyncService? syncService})
    : _syncService = syncService ?? HealthSyncService() {
    SyncActivityNotifier.isSyncing.addListener(_onSyncActivity);
    SyncActivityNotifier.progress.addListener(notifyListeners);
  }

  final HealthSyncService _syncService;

  bool loaded = false;
  String deviceId = '';
  DateTime? lastSendTime;
  DateTime initialSyncStart = DateTime.now();

  bool get isLinked => StorageService.isStudyCode(deviceId);
  bool get isSyncing => SyncActivityNotifier.isSyncing.value;
  double? get progress => SyncActivityNotifier.progress.value;
  SyncOutcome? get lastOutcome => SyncActivityNotifier.lastResult.value;

  Future<void> load() async {
    deviceId = await StorageService.getOrCreateDeviceId();
    lastSendTime = await StorageService.getLastDataSendTime();
    initialSyncStart = await StorageService.getInitialSyncStart();
    loaded = true;
    notifyListeners();
  }

  /// Stores a new study code. [resetLastSync] makes the next upload start
  /// from [initialSyncStart] again.
  Future<void> linkStudyCode(String code, {required bool resetLastSync}) async {
    await StorageService.setCustomDeviceId(code.trim());
    if (resetLastSync) {
      await StorageService.clearLastDataSendTime();
    }
    await load();
  }

  Future<void> resetLastSync() async {
    await StorageService.clearLastDataSendTime();
    await load();
  }

  Future<void> setInitialSyncStart(DateTime start) async {
    await StorageService.setInitialSyncStart(start);
    await load();
  }

  Future<HealthSyncResult?> syncNow() async {
    if (isSyncing) return null;
    final result = await _syncService.sendSinceLastSync();
    await load();
    return result;
  }

  void _onSyncActivity() {
    if (!SyncActivityNotifier.isSyncing.value) {
      // Background or startup syncs also move the last-sync time.
      load();
    } else {
      notifyListeners();
    }
  }

  @override
  void dispose() {
    SyncActivityNotifier.isSyncing.removeListener(_onSyncActivity);
    SyncActivityNotifier.progress.removeListener(notifyListeners);
    super.dispose();
  }
}
