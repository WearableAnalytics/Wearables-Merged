import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../storage_service.dart';

class CloudConnectionStatus {
  const CloudConnectionStatus({
    required this.connected,
    required this.provider,
    required this.patientId,
    this.providerUserId,
    this.linkedAt,
    this.permissions = const [],
  });

  final bool connected;
  final String provider;
  final String patientId;
  final String? providerUserId;
  final DateTime? linkedAt;
  final List<String> permissions;
}

class CloudConnectorException implements Exception {
  const CloudConnectorException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

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

  /// Builds the OAuth authorization initiation URL to open in the system/in-app browser (GET /cloud/auth/{provider}/login?patient_id=...)
  Uri buildOAuthLoginUri(
    String deviceId, {
    String provider = 'garmin',
    String? returnUrl,
  }) {
    final base = baseUriFor(deviceId);
    final patientId = patientIdFor(deviceId);
    final basePath = base.path.endsWith('/')
        ? base.path.substring(0, base.path.length - 1)
        : base.path;
    return base.replace(
      path: '$basePath/auth/${Uri.encodeComponent(provider)}/login',
      queryParameters: {
        'patient_id': patientId,
        if (returnUrl != null && returnUrl.isNotEmpty) 'return_url': returnUrl,
      },
    );
  }

  /// Queries the server (GET /cloud/connections?provider=...) to verify whether the participant currently has an active cloud connection
  Future<CloudConnectionStatus> fetchConnectionStatus(
    String deviceId, {
    String provider = 'garmin',
  }) async {
    final base = baseUriFor(deviceId);
    final patientId = patientIdFor(deviceId);
    final basePath = base.path.endsWith('/')
        ? base.path.substring(0, base.path.length - 1)
        : base.path;
    final uri = base.replace(
      path: '$basePath/connections',
      queryParameters: {'provider': provider},
    );

    final client = _clientFactory()..connectionTimeout = timeout;
    try {
      final request = await client.getUrl(uri).timeout(timeout);
      request.headers.set(HttpHeaders.acceptHeader, 'application/json');
      if (deviceId.isNotEmpty) {
        request.headers.set(
          HttpHeaders.authorizationHeader,
          'Bearer $deviceId',
        );
      }
      final response = await request.close().timeout(timeout);
      final body = await response
          .transform(utf8.decoder)
          .join()
          .timeout(timeout);

      if (response.statusCode != 200) {
        throw CloudConnectorException(
          'Failed to query cloud connections',
          statusCode: response.statusCode,
        );
      }

      final decoded = jsonDecode(body);
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
            );
          }
        }
      }

      return CloudConnectionStatus(
        connected: false,
        provider: provider,
        patientId: patientId,
      );
    } finally {
      client.close(force: true);
    }
  }

  /// Communicates with the server (DELETE /cloud/connections/{provider}/{patientId}) to deregister the user at the cloud provider (e.g. Garmin API deregistration)
  /// and delete the stored OAuth tokens on the server
  Future<void> disconnect(String deviceId, {String provider = 'garmin'}) async {
    final base = baseUriFor(deviceId);
    final patientId = patientIdFor(deviceId);
    final basePath = base.path.endsWith('/')
        ? base.path.substring(0, base.path.length - 1)
        : base.path;
    final uri = base.replace(
      path:
          '$basePath/connections/${Uri.encodeComponent(provider)}/${Uri.encodeComponent(patientId)}',
    );

    final client = _clientFactory()..connectionTimeout = timeout;
    try {
      final request = await client.deleteUrl(uri).timeout(timeout);
      request.headers.set(HttpHeaders.acceptHeader, 'application/json');
      if (deviceId.isNotEmpty) {
        request.headers.set(
          HttpHeaders.authorizationHeader,
          'Bearer $deviceId',
        );
      }
      final response = await request.close().timeout(timeout);
      await response.drain<void>().timeout(timeout);

      // 200 OK = disconnected on server; 404 Not Found = already absent on server
      if (response.statusCode != 200 && response.statusCode != 404) {
        throw CloudConnectorException(
          'Server could not remove $provider connection',
          statusCode: response.statusCode,
        );
      }
    } finally {
      client.close(force: true);
    }
  }
}
