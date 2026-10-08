import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../app_config.dart';
import '../theme/app_theme.dart';

/// Charité logo with the study band below it, in the style of Charité
/// newsletters (white logo area, blue title band).
class BrandHeader extends StatelessWidget {
  const BrandHeader({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 20),
          child: SvgPicture.asset(
            'assets/branding/charite_logo.svg',
            height: 44,
            semanticsLabel: AppConfig.institution,
          ),
        ),
        Container(
          margin: const EdgeInsets.only(right: 72),
          padding: const EdgeInsets.fromLTRB(24, 12, 16, 12),
          color: AppColors.blue,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${AppConfig.appName} Study',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
              ),
              Text(
                AppConfig.institute,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Colors.white.withValues(alpha: 0.85),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// A Charité outline icon from assets/branding, tinted in a CD colour.
class CharitePictogram extends StatelessWidget {
  const CharitePictogram(
    this.asset, {
    super.key,
    this.size = 96,
    this.color = AppColors.blue,
  });

  final String asset;
  final double size;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return SvgPicture.asset(
      'assets/branding/$asset.svg',
      width: size,
      height: size,
      colorFilter: ColorFilter.mode(color, BlendMode.srcIn),
    );
  }
}
