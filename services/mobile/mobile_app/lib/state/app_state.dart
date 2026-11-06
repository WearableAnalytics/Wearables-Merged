import 'package:flutter/foundation.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/cloud_connector_service.dart';
import '../services/health_sync_service.dart';
import '../services/notification_service.dart';
import '../services/sync_activity_notifier.dart';
import '../storage_service.dart';

/// Shared, listenable view of the study link and sync state for all tabs.
class AppState extends ChangeNotifier {
  AppState({
    HealthSyncService? syncService,
    CloudConnectorService? cloudService,
    Future<bool> Function(Uri)? urlLauncher,
  }) : _syncService = syncService ?? HealthSyncService(),
       _cloudService = cloudService ?? CloudConnectorService(),
       _urlLauncher =
           urlLauncher ??
           ((uri) => launchUrl(uri, mode: LaunchMode.externalApplication)) {
    SyncActivityNotifier.isSyncing.addListener(_onSyncActivity);
    SyncActivityNotifier.progress.addListener(notifyListeners);
  }

  final HealthSyncService _syncService;
  final CloudConnectorService _cloudService;
  final Future<bool> Function(Uri) _urlLauncher;

  bool loaded = false;
  String deviceId = '';
  DateTime? lastSendTime;
  DateTime initialSyncStart = DateTime.now();

  /// Whether local phone health store sync is enabled
  bool localHealthSyncEnabled = true;

  /// Whether a Cloud connection is linked for this participant
  bool garminConnected = false;
  String? garminUserId;
  DateTime? garminLinkedAt;
  bool garminBusy = false;

  /// True when Cloud is active and local phone upload is turned off
  bool get isCloudOnlyMode => !localHealthSyncEnabled && garminConnected;

  /// True when both local HealthKit/Health Connect and Cloud are active
  bool get isParallelSyncMode => localHealthSyncEnabled && garminConnected;

  /// The personal code expired or was refused; a new QR scan is needed.
  bool codeExpired = false;
  bool codeRejected = false;
  bool get isCodeUnusable => codeExpired || codeRejected;

  bool get isLinked => StorageService.isStudyCode(deviceId);
  bool get isSyncing => SyncActivityNotifier.isSyncing.value;
  double? get progress => SyncActivityNotifier.progress.value;

  /// Shared data ends more than a day ago, e.g. after an interrupted sync.
  bool get isBehind =>
      localHealthSyncEnabled &&
      lastSendTime != null &&
      DateTime.now().difference(lastSendTime!) > const Duration(days: 1);
  SyncOutcome? get lastOutcome => SyncActivityNotifier.lastResult.value;

  Future<void> load() async {
    deviceId = await StorageService.getOrCreateDeviceId();
    lastSendTime = await StorageService.getLastDataSendTime();
    initialSyncStart = await StorageService.getInitialSyncStart();
    localHealthSyncEnabled = await StorageService.isLocalHealthSyncEnabled();
    garminConnected = await StorageService.isGarminConnected();
    garminUserId = await StorageService.getGarminUserId();
    garminLinkedAt = await StorageService.getGarminLinkedAt();
    codeExpired = StorageService.isCodeExpired(deviceId);
    codeRejected = await StorageService.isLinkedCodeRejected();
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

  /// Enables or disables local phone health sync (Apple Health or Health Connect)
  Future<void> setLocalHealthSyncEnabled(bool enabled) async {
    await StorageService.setLocalHealthSyncEnabled(enabled);
    localHealthSyncEnabled = enabled;
    notifyListeners();
  }

  /// Builds the OAuth 2.0 PKCE login URL for the current participant
  Uri get garminOAuthLoginUri => _cloudService.buildOAuthLoginUri(deviceId);

  /// Opens the Garmin OAuth 2.0 PKCE login page in the browser
  Future<bool> startGarminConnect() async {
    if (!isLinked) return false;
    final uri = _cloudService.buildOAuthLoginUri(deviceId);
    return _urlLauncher(uri);
  }

  /// Queries the Cloud Connector server
  Future<CloudConnectionStatus> refreshGarminStatus() async {
    garminBusy = true;
    notifyListeners();
    try {
      final status = await _cloudService.fetchConnectionStatus(
        deviceId,
        provider: 'garmin',
      );
      await StorageService.setGarminConnection(
        connected: status.connected,
        providerUserId: status.providerUserId,
        linkedAt: status.linkedAt,
      );
      garminConnected = status.connected;
      garminUserId = status.providerUserId;
      garminLinkedAt = status.linkedAt;
      return status;
    } finally {
      garminBusy = false;
      notifyListeners();
    }
  }

  /// Communicates with the Cloud Connector server (DELETE /cloud/connections/garmin/{patientId}) to deregister the Garmin connection on the server and clear local state.
  Future<void> disconnectGarmin() async {
    garminBusy = true;
    notifyListeners();
    try {
      await _cloudService.disconnect(deviceId, provider: 'garmin');
      await StorageService.setGarminConnection(connected: false);
      garminConnected = false;
      garminUserId = null;
      garminLinkedAt = null;
      if (!localHealthSyncEnabled) {
        await StorageService.setLocalHealthSyncEnabled(true);
        localHealthSyncEnabled = true;
      }
    } finally {
      garminBusy = false;
      notifyListeners();
    }
  }

  Future<HealthSyncResult?> syncNow() async {
    if (isSyncing) return null;
    if (!localHealthSyncEnabled) {
      if (garminConnected) {
        try {
          await refreshGarminStatus();
        } catch (_) {}
      }
      return null;
    }
    final result = await _syncService.sendSinceLastSync();
    await load();
    await NotificationService.showActionNeeded(result);
    await NotificationService.scheduleInactivityReminder(lastSendTime);
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
