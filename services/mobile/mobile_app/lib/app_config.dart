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
}
