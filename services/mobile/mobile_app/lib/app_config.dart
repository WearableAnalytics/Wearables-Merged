import 'dart:io';

/// Static app configuration.
class AppConfig {
  AppConfig._();

  static const appName = 'Wearables';
  static const institute = 'Institut für Medizinische Informatik';
  static const institution = 'Charité – Universitätsmedizin Berlin';

  /// Platform wording for user-facing texts.
  static String get deviceName => Platform.isIOS ? 'iPhone' : 'phone';
  static String get healthStore =>
      Platform.isIOS ? 'Apple Health' : 'Health Connect';
  static String get healthAccessHint => Platform.isIOS
      ? 'Check Settings › Health › Data Access.'
      : 'Check Health Connect › App permissions.';

  /// Project page on the medinfo website. Empty hides the link.
  static const studyInfoUrl =
      'https://medinfo.charite.de/en/research/data_analytics_research_group/wearables/';

  /// Set to true to test notification (usable with tipping on version in app)
  static const bool enableNotificationSimulation = false;

  /// Manual pre-build toggle for Garmin historical data backfill UI.
  /// When false (default), the app activates this dynamically via server `GET /providers`
  static const bool enableCloudHistoryMode = bool.fromEnvironment(
    'ENABLE_CLOUD_HISTORY_MODE',
    defaultValue: false,
  );

  /// Optional pre-build toggle for the pre-auth history switch in the backfill dialog
  /// Only applies when history mode is active
  static const bool enableCloudPreAuthHistory = bool.fromEnvironment(
    'ENABLE_CLOUD_PRE_AUTH_HISTORY',
    defaultValue: false,
  );
}
