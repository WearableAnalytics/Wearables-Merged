import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:url_launcher/url_launcher.dart';

import '../app_config.dart';

Future<void> openStudyInfo() async {
  if (AppConfig.studyInfoUrl.isEmpty) return;
  await launchUrl(
    Uri.parse(AppConfig.studyInfoUrl),
    mode: LaunchMode.inAppBrowserView,
  );
}

class StudyInfoLink extends StatelessWidget {
  const StudyInfoLink({super.key});

  @override
  Widget build(BuildContext context) {
    return TextButton.icon(
      onPressed: openStudyInfo,
      icon: const Icon(Symbols.info_sharp, size: 20),
      label: const Text('About the platform'),
    );
  }
}
