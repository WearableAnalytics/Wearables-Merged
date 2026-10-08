import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../app_config.dart';
import '../theme/app_theme.dart';

/// Charité logo on the left, Wearables W mark on the right.
class BrandHeader extends StatelessWidget {
  const BrandHeader({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 8),
          child: Row(
            children: [
              SvgPicture.asset(
                'assets/branding/charite_logo.svg',
                height: 44,
                semanticsLabel: AppConfig.institution,
              ),
              const Spacer(),
              Image.asset(
                'assets/branding/wearables_mark.png',
                height: 34,
                semanticLabel: 'Wearables',
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

/// Quiet sender line for the bottom of a screen.
class InstituteFooter extends StatelessWidget {
  const InstituteFooter({super.key});

  @override
  Widget build(BuildContext context) {
    return Text(
      '${AppConfig.institute}\n${AppConfig.institution}',
      textAlign: TextAlign.center,
      style: Theme.of(context).textTheme.bodySmall?.copyWith(
        color: AppColors.grey,
        height: 1.4,
      ),
    );
  }
}
