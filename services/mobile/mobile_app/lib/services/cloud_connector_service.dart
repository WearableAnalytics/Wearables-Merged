import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../storage_service.dart';

/// Descriptor for a supported cloud wearable provider
class CloudProvider {
  const CloudProvider({
    required this.id,
    required this.name,
    required this.displayName,
    required this.description,
    this.icon,
    this.enabled = true,
    this.supportsHistoricalBackfill = false,
  });

  /// Unique provider key matching the backend route (e.g. garmin)
  final String id;

  /// Short brand name (e.g. Garmin)
  final String name;

  /// Full display name (e.g. Garmin Connect)
  final String displayName;

  /// Human-readable explanation of what this provider syncs
  final String description;

  /// UI icon
  final IconData? icon;

  /// Whether this provider is enabled for participant connection
  final bool enabled;

  /// Whether this provider supports server-side historical backfill in principle
  final bool supportsHistoricalBackfill;

  static const garmin = CloudProvider(
    id: 'garmin',
    name: 'Garmin',
    displayName: 'Garmin Connect',
    description: 'Cloud sync for Garmin watches and devices.',
    icon: Symbols.watch_sharp,
    enabled: true,
    supportsHistoricalBackfill: true,
  );

  static const fitbit = CloudProvider(
    id: 'fitbit',
    name: 'Google Health',
    displayName: 'Google Health (Fitbit & Pixel Watch)',
    description: 'Cloud sync for Fitbit, Pixel Watch and Health Connect.',
    icon: Symbols.watch_button_sharp,
    enabled: true,
  );

  static const oura = CloudProvider(
    id: 'oura',
    name: 'Oura',
    displayName: 'Oura Ring',
    description: 'Cloud sync for Oura Ring.',
    icon: Symbols.ring_volume_sharp,
    enabled: true,
  );

  static const whoop = CloudProvider(
    id: 'whoop',
    name: 'Whoop',
    displayName: 'Whoop Strap',
    description: 'Cloud sync for Whoop Strap.',
    icon: Symbols.vital_signs_sharp,
    enabled: true,
  );

  static const withings = CloudProvider(
    id: 'withings',
    name: 'Withings',
    displayName: 'Withings Health',
    description: 'Cloud sync for Withings scales and devices.',
    icon: Symbols.monitor_weight_sharp,
    enabled: true,
  );

  static const polar = CloudProvider(
    id: 'polar',
    name: 'Polar',
    displayName: 'Polar Flow',
    description: 'Cloud sync for Polar watches and sensors.',
    icon: Symbols.cardiology_sharp,
    enabled: true,
  );

  /// Active providers currently enabled in the mobile app UI
  static const List<CloudProvider> activeProviders = [
    garmin,
    polar,
    fitbit,
    oura,
    whoop,
    withings,
  ];

  /// Catalog of all known cloud providers for seamless future extensions
  static const List<CloudProvider> knownProviders = [
    garmin,
    fitbit,
    oura,
    whoop,
    withings,
    polar,
  ];

  static CloudProvider find(String id) {
    return knownProviders.firstWhere(
      (p) => p.id.toLowerCase() == id.toLowerCase(),
      orElse: () => CloudProvider(
        id: id,
        name: id.isNotEmpty ? '${id[0].toUpperCase()}${id.substring(1)}' : id,
        displayName: id,
        description: 'Direct cloud sync for $id.',
      ),
    );
  }
}

class CloudProviderCapabilities {
  const CloudProviderCapabilities({
    this.supportsHistoricalBackfill = false,
    this.backfillEnabled = false,
    this.preAuthHistoryAllowed = false,
  });

  factory CloudProviderCapabilities.fromJson(Map<String, dynamic> json) {
    return CloudProviderCapabilities(
      supportsHistoricalBackfill: json['supports_historical_backfill'] == true,
      backfillEnabled: json['backfill_enabled'] == true,
      preAuthHistoryAllowed: json['pre_auth_history_allowed'] == true,
    );
  }

  final bool supportsHistoricalBackfill;
  final bool backfillEnabled;
  final bool preAuthHistoryAllowed;
}

class HistoricalBackfillResult {
  const HistoricalBackfillResult({
    required this.provider,
    required this.patientId,
    required this.status,
    required this.preAuthApplied,
    this.triggered = const [],
    this.alreadyRequested = const [],
    this.skipped = const {},
    this.failed = const {},
  });

  factory HistoricalBackfillResult.fromJson(Map<String, dynamic> json) {
    return HistoricalBackfillResult(
      provider: (json['provider'] as String?) ?? '',
      patientId: (json['patient_id'] as String?) ?? '',
      status: (json['status'] as String?) ?? 'unknown',
      preAuthApplied: json['pre_auth_applied'] == true,
      triggered:
          (json['triggered'] as List?)?.whereType<String>().toList() ?? const [],
      alreadyRequested:
          (json['already_requested'] as List?)?.whereType<String>().toList() ??
              const [],
      skipped: (json['skipped'] as Map?)?.map(
            (k, v) => MapEntry(k.toString(), v.toString()),
          ) ??
          const {},
      failed: (json['failed'] as Map?)?.map(
            (k, v) => MapEntry(k.toString(), v.toString()),
          ) ??
          const {},
    );
  }

  final String provider;
  final String patientId;
  final String status;
  final bool preAuthApplied;
  final List<String> triggered;
  final List<String> alreadyRequested;
  final Map<String, String> skipped;
  final Map<String, String> failed;
}

class CloudConnectionStatus {
  const CloudConnectionStatus({
    required this.connected,
    required this.provider,
    required this.patientId,
    this.providerUserId,
    this.linkedAt,
    this.permissions = const [],
    this.allowPreAuthHistory = false,
  });

  final bool connected;
  final String provider;
  final String patientId;
  final String? providerUserId;
  final DateTime? linkedAt;
  final List<String> permissions;
  final bool allowPreAuthHistory;

  bool get hasHistoricalPermission =>
      permissions.contains('HISTORICAL_DATA_EXPORT');
}

class CloudConnectorException implements Exception {
  const CloudConnectorException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  bool get isAuthError => statusCode == 401 || statusCode == 403;

  @override
  String toString() => statusCode != null
      ? 'CloudConnectorException(status $statusCode): $message'
      : 'CloudConnectorException: $message';
}

/// Client for the Wearables Cloud Connector backend (`/cloud`), managing OAuth provider linking (Garmin Connect etc.)
class CloudConnectorService {
  CloudConnectorService({
    Uri? baseUri,
    HttpClient Function()? clientFactory,
    this.timeout = const Duration(seconds: 15),
  }) : _baseUri =
           baseUri ??
           Uri.parse(
             const String.fromEnvironment(
               'CLOUD_CONNECTOR_URL',
               defaultValue: 'https://wearables.charite.de/cloud',
             ),
           ),
       _clientFactory = clientFactory ?? HttpClient.new;

  final Uri _baseUri;
  final HttpClient Function() _clientFactory;
  final Duration timeout;

  /// Resolves the target cloud-connector base URI
  /// In [kDebugMode], a study code JWT may specify a custom local gateway
  Uri baseUriFor(String deviceId) {
    if (kDebugMode) {
      final custom = StorageService.cloudEndpoint(deviceId);
      if (custom != null) {
        final parsed = Uri.tryParse(custom);
        if (parsed != null) return parsed;
      }
    }
    return _baseUri;
  }

  /// Resolves the patient identifier used by the cloud-connector for [deviceId]
  String patientIdFor(String deviceId) {
    return StorageService.patientIdFromCode(deviceId) ?? deviceId;
  }

  Uri _endpointUri(
    String deviceId,
    String subPath, {
    Map<String, String>? queryParameters,
  }) {
    final base = baseUriFor(deviceId);
    final basePath = base.path.endsWith('/')
        ? base.path.substring(0, base.path.length - 1)
        : base.path;
    return base.replace(
      path: '$basePath$subPath',
      queryParameters:
          queryParameters != null && queryParameters.isNotEmpty
              ? queryParameters
              : null,
    );
  }

  String _extractErrorDetail(String body, String fallback) {
    if (body.isNotEmpty) {
      try {
        final decoded = jsonDecode(body);
        if (decoded is Map<String, dynamic> && decoded['detail'] is String) {
          return decoded['detail'] as String;
        }
      } catch (_) {}
    }
    return fallback;
  }

  Future<dynamic> _sendJsonRequest(
    String deviceId, {
    required String method,
    required String subPath,
    Map<String, String>? queryParameters,
    Map<String, dynamic>? body,
    Set<int> acceptedStatusCodes = const {200},
    String errorMessage = 'Cloud connector request failed',
  }) async {
    final uri = _endpointUri(
      deviceId,
      subPath,
      queryParameters: queryParameters,
    );
    final client = _clientFactory()..connectionTimeout = timeout;
    try {
      final request = await client.openUrl(method, uri).timeout(timeout);
      request.headers.set(HttpHeaders.acceptHeader, 'application/json');
      if (deviceId.isNotEmpty) {
        request.headers.set(
          HttpHeaders.authorizationHeader,
          'Bearer $deviceId',
        );
      }
      if (body != null) {
        request.headers.contentType = ContentType.json;
        request.write(jsonEncode(body));
      }
      final response = await request.close().timeout(timeout);
      final rawBody = await response
          .transform(utf8.decoder)
          .join()
          .timeout(timeout);
      if (!acceptedStatusCodes.contains(response.statusCode)) {
        throw CloudConnectorException(
          _extractErrorDetail(rawBody, errorMessage),
          statusCode: response.statusCode,
        );
      }
      if (rawBody.trim().isEmpty) return const <String, dynamic>{};
      return jsonDecode(rawBody);
    } finally {
      client.close(force: true);
    }
  }

  /// Builds the OAuth authorization initiation URL to open in the system/in-app browser (GET /cloud/auth/{provider}/login?patient_id=...)
  Uri buildOAuthLoginUri(
    String deviceId, {
    String provider = 'garmin',
    String? returnUrl,
    bool allowPreAuth = false,
  }) {
    final patientId = patientIdFor(deviceId);
    return _endpointUri(
      deviceId,
      '/auth/${Uri.encodeComponent(provider)}/login',
      queryParameters: {
        'patient_id': patientId,
        if (returnUrl != null && returnUrl.isNotEmpty) 'return_url': returnUrl,
        if (allowPreAuth) 'allow_pre_auth': 'true',
      },
    );
  }

  /// Initiates OAuth 2.0 PKCE with authenticated POST /cloud/auth/{provider}/login for JWT
  Future<Uri> initiateOAuthLogin(
    String deviceId, {
    String provider = 'garmin',
    String? returnUrl = 'wearables://oauth-callback',
    bool allowPreAuth = false,
  }) async {
    final decoded = await _sendJsonRequest(
      deviceId,
      method: 'POST',
      subPath: '/auth/${Uri.encodeComponent(provider)}/login',
      body: {
        if (returnUrl != null && returnUrl.isNotEmpty) 'return_url': returnUrl,
        if (allowPreAuth) 'allow_pre_auth': true,
      },
      acceptedStatusCodes: const {200, 201},
      errorMessage: 'Failed to initiate $provider OAuth login',
    );
    if (decoded is Map<String, dynamic> &&
        decoded['authorization_url'] is String) {
      final authUri = Uri.tryParse(decoded['authorization_url'] as String);
      if (authUri != null) return authUri;
    }
    throw const FormatException('Unexpected OAuth initiation payload');
  }

  /// Queries GET /cloud/providers to discover server side backfill and pre-auth capabilities
  Future<Map<String, CloudProviderCapabilities>> fetchProviderCapabilities(
    String deviceId,
  ) async {
    final decoded = await _sendJsonRequest(
      deviceId,
      method: 'GET',
      subPath: '/providers',
      errorMessage: 'Failed to query provider capabilities',
    );
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('Unexpected provider capabilities payload');
    }
    final rawCaps = decoded['capabilities'];
    if (rawCaps is! Map<String, dynamic>) {
      return const {};
    }
    final result = <String, CloudProviderCapabilities>{};
    rawCaps.forEach((key, value) {
      if (value is Map<String, dynamic>) {
        result[key.toLowerCase()] = CloudProviderCapabilities.fromJson(value);
      }
    });
    return result;
  }

  /// Queries the server (GET /cloud/connections?provider=...) to verify whether the participant currently has an active cloud connection
  Future<CloudConnectionStatus> fetchConnectionStatus(
    String deviceId, {
    String provider = 'garmin',
  }) async {
    final patientId = patientIdFor(deviceId);
    final decoded = await _sendJsonRequest(
      deviceId,
      method: 'GET',
      subPath: '/connections',
      queryParameters: {'provider': provider},
      errorMessage: 'Failed to query cloud connections',
    );
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('Unexpected cloud connections payload');
    }
    final list = decoded['connections'];
    if (list is List) {
      for (final item in list) {
        if (item is Map<String, dynamic> &&
            item['patient_id'] == patientId &&
            (item['provider'] as String?)?.toLowerCase() ==
                provider.toLowerCase()) {
          final linkedAtRaw = item['linked_at'];
          final permsRaw = item['permissions'];
          return CloudConnectionStatus(
            connected: true,
            provider: provider,
            patientId: patientId,
            providerUserId: item['provider_user_id'] as String?,
            linkedAt: linkedAtRaw is String
                ? DateTime.tryParse(linkedAtRaw)
                : null,
            permissions: permsRaw is List
                ? permsRaw.whereType<String>().toList()
                : const [],
            allowPreAuthHistory: item['allow_pre_auth_history'] == true,
          );
        }
      }
    }

    return CloudConnectionStatus(
      connected: false,
      provider: provider,
      patientId: patientId,
    );
  }

  /// Updates patient option for pre-auth historical backfill (PUT /cloud/connections/{provider}/{patientId}/pre-auth).
  Future<bool> setPreAuthHistory(
    String deviceId, {
    String provider = 'garmin', // Only default
    required bool allowPreAuth,
  }) async {
    final patientId = patientIdFor(deviceId);
    final decoded = await _sendJsonRequest(
      deviceId,
      method: 'PUT',
      subPath:
          '/connections/${Uri.encodeComponent(provider)}/${Uri.encodeComponent(patientId)}/pre-auth',
      body: {'allow_pre_auth_history': allowPreAuth},
      errorMessage: 'Could not update pre-auth history preference',
    );
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('Unexpected pre-auth response payload');
    }
    return decoded['allow_pre_auth_history'] == true;
  }

  /// Requests historical backfill on the server (POST /cloud/sync/{provider}/history)
  Future<HistoricalBackfillResult> triggerHistoricalBackfill(
    String deviceId, {
    String provider = 'garmin',
    int days = 30,
    bool allowPreAuth = false,
  }) async {
    final patientId = patientIdFor(deviceId);
    final decoded = await _sendJsonRequest(
      deviceId,
      method: 'POST',
      subPath: '/sync/${Uri.encodeComponent(provider)}/history',
      body: {
        'patient_id': patientId,
        'days': days,
        'allow_pre_auth': allowPreAuth,
      },
      errorMessage: 'Could not start historical $provider sync',
    );
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('Unexpected historical backfill payload');
    }
    return HistoricalBackfillResult.fromJson(decoded);
  }

  /// Communicates with the server (DELETE /cloud/connections/{provider}/{patientId}) to deregister the user at the cloud provider (e.g. Garmin API deregistration) and delete the stored OAuth tokens on the server
  Future<void> disconnect(String deviceId, {String provider = 'garmin'}) async {
    final patientId = patientIdFor(deviceId);
    await _sendJsonRequest(
      deviceId,
      method: 'DELETE',
      subPath:
          '/connections/${Uri.encodeComponent(provider)}/${Uri.encodeComponent(patientId)}',
      acceptedStatusCodes: const {200, 404},
      errorMessage: 'Server could not remove $provider connection',
    );
  }
}
