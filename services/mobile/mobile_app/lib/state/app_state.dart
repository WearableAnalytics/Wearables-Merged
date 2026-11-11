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
           ((uri) => launchUrl(uri, mode: LaunchMode.inAppBrowserView)) {
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

  /// Map of provider ID (lowercase, e.g. 'garmin') -> connection status
  final Map<String, CloudConnectionStatus> cloudConnections = {};
  final Set<String> _busyProviders = {};

  bool isCloudBusy(String provider) =>
      _busyProviders.contains(provider.toLowerCase());
  bool isCloudConnected(String provider) =>
      cloudConnections[provider.toLowerCase()]?.connected ?? false;
  String? cloudUserId(String provider) =>
      cloudConnections[provider.toLowerCase()]?.providerUserId;
  DateTime? cloudLinkedAt(String provider) =>
      cloudConnections[provider.toLowerCase()]?.linkedAt;

  /// True when at least one Cloud connection is active
  bool get hasAnyCloudConnection =>
      cloudConnections.values.any((c) => c.connected);

  /// True when any Cloud connection is currently running an async network call
  bool get isAnyCloudBusy => _busyProviders.isNotEmpty;

  /// Returns the primary active cloud provider
  CloudProvider? get primaryCloudProvider {
    for (final entry in cloudConnections.entries) {
      if (entry.value.connected) {
        return CloudProvider.find(entry.key);
      }
    }
    return null;
  }

  /// True when Cloud is active and local phone upload is turned off
  bool get isCloudOnlyMode => !localHealthSyncEnabled && hasAnyCloudConnection;

  /// True when both local HealthKit/Health Connect and Cloud are active
  bool get isParallelSyncMode =>
      localHealthSyncEnabled && hasAnyCloudConnection;

  // Backward compatible properties for Garmin
  bool get garminConnected => isCloudConnected('garmin');
  String? get garminUserId => cloudUserId('garmin');
  DateTime? get garminLinkedAt => cloudLinkedAt('garmin');
  bool get garminBusy => isCloudBusy('garmin');

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
    try {
      deviceId = await StorageService.getOrCreateDeviceId();
      lastSendTime = await StorageService.getLastDataSendTime();
      initialSyncStart = await StorageService.getInitialSyncStart();
      localHealthSyncEnabled = await StorageService.isLocalHealthSyncEnabled();

      final currentPatientId = _cloudService.patientIdFor(deviceId);
      for (final provider in CloudProvider.knownProviders) {
        final connected = await StorageService.isCloudConnected(provider.id);
        if (connected) {
          final userId = await StorageService.getCloudUserId(provider.id);
          final linkedAt = await StorageService.getCloudLinkedAt(provider.id);
          cloudConnections[provider.id] = CloudConnectionStatus(
            connected: true,
            provider: provider.id,
            patientId: currentPatientId,
            providerUserId: userId,
            linkedAt: linkedAt,
          );
        } else {
          cloudConnections[provider.id] = CloudConnectionStatus(
            connected: false,
            provider: provider.id,
            patientId: currentPatientId,
          );
        }
      }

      codeExpired = StorageService.isCodeExpired(deviceId);
      codeRejected = await StorageService.isLinkedCodeRejected();
    } catch (e, st) {
      debugPrint('Error loading app state: $e\n$st');
    } finally {
      loaded = true;
      notifyListeners();
    }
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

  /// Builds the OAuth 2.0 PKCE login URL for any cloud provider
  Uri cloudOAuthLoginUri(String provider, {String? returnUrl = 'wearables://oauth-callback'}) =>
      _cloudService.buildOAuthLoginUri(
        deviceId,
        provider: provider,
        returnUrl: returnUrl,
      );

  /// Opens the cloud provider's OAuth 2.0 PKCE login page in the browser
  Future<bool> startCloudConnect(String provider) async {
    if (!isLinked) return false;
    final uri = cloudOAuthLoginUri(provider);
    return _urlLauncher(uri);
  }

  /// Queries the Cloud Connector server for a specific provider
  Future<CloudConnectionStatus> refreshCloudStatus(String provider) async {
    final key = provider.toLowerCase();
    _busyProviders.add(key);
    notifyListeners();
    try {
      final status = await _cloudService.fetchConnectionStatus(
        deviceId,
        provider: provider,
      );
      cloudConnections[key] = status;
      await StorageService.setCloudConnection(
        provider: provider,
        connected: status.connected,
        providerUserId: status.providerUserId,
        linkedAt: status.linkedAt,
      );
      return status;
    } finally {
      _busyProviders.remove(key);
      notifyListeners();
    }
  }

  /// Communicates with the Cloud Connector server (DELETE /cloud/connections/{provider}/{patientId}) to deregister the provider on the server and clear local state.
  Future<void> disconnectCloud(String provider) async {
    final key = provider.toLowerCase();
    _busyProviders.add(key);
    notifyListeners();
    try {
      await _cloudService.disconnect(deviceId, provider: provider);
      await StorageService.setCloudConnection(
        provider: provider,
        connected: false,
      );
      cloudConnections[key] = CloudConnectionStatus(
        connected: false,
        provider: provider,
        patientId: _cloudService.patientIdFor(deviceId),
      );
      if (!localHealthSyncEnabled && !hasAnyCloudConnection) {
        await StorageService.setLocalHealthSyncEnabled(true);
        localHealthSyncEnabled = true;
      }
    } finally {
      _busyProviders.remove(key);
      notifyListeners();
    }
  }

  // Backward compatible methods for Garmin
  Uri get garminOAuthLoginUri => cloudOAuthLoginUri('garmin');
  Future<bool> startGarminConnect() => startCloudConnect('garmin');
  Future<CloudConnectionStatus> refreshGarminStatus() =>
      refreshCloudStatus('garmin');
  Future<void> disconnectGarmin() => disconnectCloud('garmin');

  Future<HealthSyncResult?> syncNow() async {
    if (isSyncing) return null;
    if (!localHealthSyncEnabled) {
      if (hasAnyCloudConnection) {
        try {
          for (final entry in cloudConnections.entries) {
            if (entry.value.connected) {
              await refreshCloudStatus(entry.key);
            }
          }
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
