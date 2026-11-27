import 'package:flutter/foundation.dart';
import 'package:url_launcher/url_launcher.dart';

import '../app_config.dart';
import '../services/cloud_connector_service.dart';
import '../services/health_sync_service.dart';
import '../services/notification_service.dart';
import '../services/sync_activity_notifier.dart';
import '../storage_service.dart';

/// Outcome of removing a cloud provider connection
class CloudDisconnectResult {
  const CloudDisconnectResult({
    required this.provider,
    required this.serverDisconnected,
    required this.removedLocally,
    this.authRejected = false,
  });

  final String provider;
  final bool serverDisconnected;
  final bool removedLocally;
  final bool authRejected;
}

/// Shared, listenable view of the study link and sync state for all tabs.
class AppState extends ChangeNotifier {
  AppState({
    HealthSyncService? syncService,
    CloudConnectorService? cloudService,
    Future<bool> Function(Uri)? urlLauncher,
    DateTime Function()? clock,
    bool? enableHistoryModeOverride,
  }) : _syncService = syncService ?? HealthSyncService(),
       _cloudService = cloudService ?? CloudConnectorService(),
       _urlLauncher =
           urlLauncher ??
           ((uri) => launchUrl(uri, mode: LaunchMode.inAppBrowserView)),
       _clock = clock ?? DateTime.now,
       _enableHistoryModeOverride = enableHistoryModeOverride {
    SyncActivityNotifier.isSyncing.addListener(_onSyncActivity);
    SyncActivityNotifier.progress.addListener(notifyListeners);
  }

  static const Duration historySyncCooldown = Duration(seconds: 10);

  final HealthSyncService _syncService;
  final CloudConnectorService _cloudService;
  final Future<bool> Function(Uri) _urlLauncher;
  final DateTime Function() _clock;
  final bool? _enableHistoryModeOverride;
  final Map<String, DateTime> _lastHistorySyncAt = {};

  bool loaded = false;
  String deviceId = '';
  DateTime? lastSendTime;
  DateTime initialSyncStart = DateTime.now();

  /// Whether local phone health store sync is enabled
  bool localHealthSyncEnabled = true;

  /// Map of provider ID (lowercase, e.g. 'garmin') -> connection status
  final Map<String, CloudConnectionStatus> cloudConnections = {};
  final Map<String, CloudProviderCapabilities> cloudCapabilities = {};
  final Set<String> _busyProviders = {};

  /// Emits when OAuth deep link (wearables://oauth-callback) returns for verifying
  final ValueNotifier<int> oauthCallbackCount = ValueNotifier(0);

  void notifyOAuthCallback() {
    oauthCallbackCount.value++;
  }

  bool isCloudBusy(String provider) =>
      _busyProviders.contains(provider.toLowerCase());
  bool isCloudConnected(String provider) =>
      cloudConnections[provider.toLowerCase()]?.connected ?? false;
  String? cloudUserId(String provider) =>
      cloudConnections[provider.toLowerCase()]?.providerUserId;
  DateTime? cloudLinkedAt(String provider) =>
      cloudConnections[provider.toLowerCase()]?.linkedAt;
  CloudProviderCapabilities cloudCapabilitiesFor(String provider) =>
      cloudCapabilities[provider.toLowerCase()] ??
      const CloudProviderCapabilities();
  bool get _manualHistoryMode =>
      _enableHistoryModeOverride ?? AppConfig.enableCloudHistoryMode;
  bool isCloudHistorySupported(String provider) =>
      cloudCapabilitiesFor(provider).supportsHistoricalBackfill ||
      CloudProvider.find(provider).supportsHistoricalBackfill;
  bool isCloudBackfillEnabled(String provider) =>
      cloudCapabilitiesFor(provider).backfillEnabled ||
      (_manualHistoryMode && isCloudHistorySupported(provider));
  bool isCloudPreAuthAllowed(String provider) =>
      isCloudBackfillEnabled(provider) &&
      (cloudCapabilitiesFor(provider).preAuthHistoryAllowed ||
          AppConfig.enableCloudPreAuthHistory);
  bool cloudAllowPreAuthHistory(String provider) =>
      cloudConnections[provider.toLowerCase()]?.allowPreAuthHistory ?? false;
  bool cloudHasHistoricalPermission(String provider) =>
      cloudConnections[provider.toLowerCase()]?.hasHistoricalPermission ?? false;
  Duration cloudHistoryCooldownRemaining(String provider) {
    final last = _lastHistorySyncAt[provider.toLowerCase()];
    if (last == null) return Duration.zero;
    final elapsed = _clock().difference(last);
    if (elapsed >= historySyncCooldown) return Duration.zero;
    return historySyncCooldown - elapsed;
  }

  bool isCloudHistoryOnCooldown(String provider) =>
      cloudHistoryCooldownRemaining(provider) > Duration.zero;

  /// True when at least one Cloud connection is active
  bool get hasAnyCloudConnection =>
      cloudConnections.values.any((c) => c.connected);

  /// True when any Cloud connection is currently running an async network call
  bool get isAnyCloudBusy => _busyProviders.isNotEmpty;

  /// Returns all currently connected active cloud providers
  List<CloudProvider> get connectedCloudProviders => CloudProvider.activeProviders
      .where((p) => isCloudConnected(p.id))
      .toList();

  /// Returns all active cloud providers that are not currently connected
  List<CloudProvider> get availableCloudProviders => CloudProvider.activeProviders
      .where((p) => !isCloudConnected(p.id))
      .toList();

  /// Returns the primary active cloud provider
  CloudProvider? get primaryCloudProvider {
    for (final entry in cloudConnections.entries) {
      if (entry.value.connected) {
        return CloudProvider.find(entry.key);
      }
    }
    return null;
  }

  /// Comma-separated list of all connected cloud provider names
  String get cloudNamesList =>
      connectedCloudProviders.map((p) => p.name).join(', ');

  /// Concise summary of connected cloud providers (e.g. "Garmin", "Garmin & Oura", "3 Cloud providers")
  String get cloudSummaryLabel {
    final connected = connectedCloudProviders;
    if (connected.isEmpty) return 'Cloud';
    if (connected.length == 1) return connected.first.name;
    if (connected.length == 2) {
      return '${connected[0].name} & ${connected[1].name}';
    }
    return '${connected.length} Cloud providers';
  }

  /// Label for tiles
  String get cloudTileLabel {
    final connected = connectedCloudProviders;
    if (connected.isEmpty) return 'Cloud';
    if (connected.length == 1) return '${connected.first.name} Cloud';
    return cloudSummaryLabel;
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
          final existing = cloudConnections[provider.id];
          final userId = await StorageService.getCloudUserId(provider.id);
          final linkedAt = await StorageService.getCloudLinkedAt(provider.id);
          cloudConnections[provider.id] = CloudConnectionStatus(
            connected: true,
            provider: provider.id,
            patientId: currentPatientId,
            providerUserId: userId,
            linkedAt: linkedAt,
            permissions: existing?.permissions ?? const [],
            allowPreAuthHistory: existing?.allowPreAuthHistory ?? false,
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
    final trimmed = code.trim();
    final oldPatientId = isLinked ? _cloudService.patientIdFor(deviceId) : null;
    final newPatientId = _cloudService.patientIdFor(trimmed);
    if (oldPatientId == null || oldPatientId != newPatientId) {
      await StorageService.clearAllCloudConnections(
        CloudProvider.knownProviders.map((p) => p.id),
      );
      cloudConnections.clear();
    }
    await StorageService.setCustomDeviceId(trimmed);
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
  Uri cloudOAuthLoginUri(
    String provider, {
    String? returnUrl = 'wearables://oauth-callback',
    bool allowPreAuth = false,
  }) =>
      _cloudService.buildOAuthLoginUri(
        deviceId,
        provider: provider,
        returnUrl: returnUrl,
        allowPreAuth: allowPreAuth,
      );

  Future<void> _handleCloudAuthError(CloudConnectorException e) async {
    if (e.isAuthError && StorageService.isStudyCode(deviceId)) {
      await StorageService.markCodeRejected(deviceId);
      codeRejected = true;
      notifyListeners();
    }
  }

  Future<void> _clearLocalCloudConnection(String provider) async {
    final key = provider.toLowerCase();
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
  }

  Future<void> _refreshCapabilitiesQuietly() async {
    try {
      final caps = await _cloudService.fetchProviderCapabilities(deviceId);
      cloudCapabilities
        ..clear()
        ..addAll(caps);
    } catch (_) {}
  }

  /// Refreshes backend provider capabilities (e.g. whether Garmin backfill is active)
  Future<void> refreshCloudCapabilities() async {
    await _refreshCapabilitiesQuietly();
    notifyListeners();
  }

  /// Opens the cloud provider's OAuth 2.0 PKCE login page in the browser
  /// Initiates the OAuth session via an authenticated POST with the case JWT
  Future<bool> startCloudConnect(
    String provider, {
    bool allowPreAuth = false,
  }) async {
    if (!isLinked || isCodeUnusable) return false;
    try {
      final uri = await _cloudService.initiateOAuthLogin(
        deviceId,
        provider: provider,
        returnUrl: 'wearables://oauth-callback',
        allowPreAuth: allowPreAuth,
      );
      return await _urlLauncher(uri);
    } on CloudConnectorException catch (e) {
      if (e.isAuthError) {
        await _handleCloudAuthError(e);
      }
      rethrow;
    }
  }

  /// Queries the Cloud Connector server for a specific provider
  Future<CloudConnectionStatus> refreshCloudStatus(String provider) async {
    final key = provider.toLowerCase();
    _busyProviders.add(key);
    notifyListeners();
    try {
      await _refreshCapabilitiesQuietly();
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
      if (!status.connected && !localHealthSyncEnabled && !hasAnyCloudConnection) {
        await StorageService.setLocalHealthSyncEnabled(true);
        localHealthSyncEnabled = true;
      }
      return status;
    } on CloudConnectorException catch (e) {
      await _handleCloudAuthError(e);
      rethrow;
    } finally {
      _busyProviders.remove(key);
      notifyListeners();
    }
  }

  Future<List<CloudProvider>> _reconcileAllConnections() async {
    await _refreshCapabilitiesQuietly();
    final activeMap = await _cloudService.fetchAllConnectionStatuses(deviceId);
    final activeProviders = <CloudProvider>[];
    final currentPatientId = _cloudService.patientIdFor(deviceId);
    var changed = false;

    for (final provider in CloudProvider.activeProviders) {
      final wasConnected = isCloudConnected(provider.id);
      final serverStatus = activeMap[provider.id];
      if (serverStatus != null && serverStatus.connected) {
        cloudConnections[provider.id] = serverStatus;
        await StorageService.setCloudConnection(
          provider: provider.id,
          connected: true,
          providerUserId: serverStatus.providerUserId,
          linkedAt: serverStatus.linkedAt,
        );
        if (!wasConnected) changed = true;
        activeProviders.add(provider);
      } else {
        cloudConnections[provider.id] = CloudConnectionStatus(
          connected: false,
          provider: provider.id,
          patientId: currentPatientId,
        );
        if (wasConnected) {
          await StorageService.setCloudConnection(
            provider: provider.id,
            connected: false,
          );
          changed = true;
        }
      }
    }

    if (!localHealthSyncEnabled && !hasAnyCloudConnection) {
      await StorageService.setLocalHealthSyncEnabled(true);
      localHealthSyncEnabled = true;
      changed = true;
    }
    if (changed || activeProviders.isNotEmpty || cloudCapabilities.isNotEmpty) {
      notifyListeners();
    }
    return activeProviders;
  }

  /// Refreshes all cloud provider connections in one server request
  Future<List<CloudProvider>> refreshAllCloudStatuses() async {
    if (!isLinked || isCodeUnusable) return const [];
    final keys = CloudProvider.activeProviders.map((p) => p.id).toList();
    _busyProviders.addAll(keys);
    notifyListeners();
    try {
      return await _reconcileAllConnections();
    } on CloudConnectorException catch (e) {
      await _handleCloudAuthError(e);
      rethrow;
    } finally {
      _busyProviders.removeAll(keys);
      notifyListeners();
    }
  }

  /// Reconciles active cloud providers with the server in a single request & updates local storage
  /// Returns the list of providers that are active on the server
  Future<List<CloudProvider>> restoreCloudConnections() async {
    if (!isLinked || isCodeUnusable) return const [];
    try {
      return await _reconcileAllConnections();
    } on CloudConnectorException catch (e) {
      if (e.isAuthError) {
        await _handleCloudAuthError(e);
      }
      return const [];
    } catch (_) {
      return const [];
    }
  }

  /// Updates pre-auth historical backfill preference on the server
  Future<bool> setCloudPreAuthHistory(String provider, bool allow) async {
    final key = provider.toLowerCase();
    _busyProviders.add(key);
    notifyListeners();
    try {
      final saved = await _cloudService.setPreAuthHistory(
        deviceId,
        provider: provider,
        allowPreAuth: allow,
      );
      final current = cloudConnections[key];
      if (current != null) {
        cloudConnections[key] = CloudConnectionStatus(
          connected: current.connected,
          provider: current.provider,
          patientId: current.patientId,
          providerUserId: current.providerUserId,
          linkedAt: current.linkedAt,
          permissions: current.permissions,
          allowPreAuthHistory: saved,
        );
      }
      return saved;
    } on CloudConnectorException catch (e) {
      await _handleCloudAuthError(e);
      rethrow;
    } finally {
      _busyProviders.remove(key);
      notifyListeners();
    }
  }

  /// Triggers asynchronous historical backfill on server for provider.
  Future<HistoricalBackfillResult> triggerCloudHistorySync(
    String provider, {
    int days = 30,
    bool allowPreAuth = false,
  }) async {
    final key = provider.toLowerCase();
    final remaining = cloudHistoryCooldownRemaining(key);
    if (remaining > Duration.zero) {
      final secs = (remaining.inMilliseconds / 1000).ceil();
      throw CloudConnectorException(
        'Please wait ${secs}s before requesting historical $provider data again.',
      );
    }
    _busyProviders.add(key);
    notifyListeners();
    try {
      final result = await _cloudService.triggerHistoricalBackfill(
        deviceId,
        provider: provider,
        days: days,
        allowPreAuth: allowPreAuth,
      );
      _lastHistorySyncAt[key] = _clock();
      return result;
    } on CloudConnectorException catch (e) {
      await _handleCloudAuthError(e);
      rethrow;
    } finally {
      _busyProviders.remove(key);
      notifyListeners();
    }
  }

  /// Communicates with the Cloud Connector server (DELETE /cloud/connections/{provider}/{patientId}) to deregister the provider on the server and clear local state.
  /// When [localOnly] is false and the token is unusable or rejected (401/403), keeps the local state intact and returns `authRejected: true` so the UI does not falsely hide an active server-side link without warning
  Future<CloudDisconnectResult> disconnectCloud(
    String provider, {
    bool localOnly = false,
  }) async {
    final key = provider.toLowerCase();
    _busyProviders.add(key);
    notifyListeners();
    try {
      if (localOnly) {
        await _clearLocalCloudConnection(provider);
        return CloudDisconnectResult(
          provider: provider,
          serverDisconnected: false,
          removedLocally: true,
          authRejected: isCodeUnusable,
        );
      }

      if (isCodeUnusable) {
        return CloudDisconnectResult(
          provider: provider,
          serverDisconnected: false,
          removedLocally: false,
          authRejected: true,
        );
      }

      try {
        await _cloudService.disconnect(deviceId, provider: provider);
        await _clearLocalCloudConnection(provider);
        return CloudDisconnectResult(
          provider: provider,
          serverDisconnected: true,
          removedLocally: true,
        );
      } on CloudConnectorException catch (e) {
        if (e.isAuthError) {
          await _handleCloudAuthError(e);
          return CloudDisconnectResult(
            provider: provider,
            serverDisconnected: false,
            removedLocally: false,
            authRejected: true,
          );
        }
        rethrow;
      }
    } finally {
      _busyProviders.remove(key);
      notifyListeners();
    }
  }

  /// Disconnects all currently active cloud provider connections
  Future<List<CloudDisconnectResult>> disconnectAllCloudConnections({
    bool localOnly = false,
  }) async {
    final providers = connectedCloudProviders.map((p) => p.id).toList();
    final results = <CloudDisconnectResult>[];
    for (final providerId in providers) {
      final res = await disconnectCloud(providerId, localOnly: localOnly);
      results.add(res);
      if (res.authRejected && !res.removedLocally) {
        break;
      }
    }
    return results;
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
          await refreshAllCloudStatuses();
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
    oauthCallbackCount.dispose();
    super.dispose();
  }
}
