import 'package:flutter/material.dart';

/// Charité corporate colours (Charité-Blau, -Dunkelblau, -Hellblau, -Koralle,
/// -Dunkelgrau) plus neutral surfaces and a status green.
class AppColors {
  AppColors._();

  static const blue = Color(0xFF294D91);
  static const darkBlue = Color(0xFF12264E);
  static const lightBlue = Color(0xFF4679B8);
  static const blueSoft = Color(0xFFE9EEF6);
  static const coral = Color(0xFFCB655D);
  static const coralSoft = Color(0xFFF9E8E6);
  static const grey = Color(0xFF81898E);
  static const success = Color(0xFF2E8B57);
  static const successSoft = Color(0xFFE4F2EA);
  static const background = Color(0xFFF5F6F8);
  static const surface = Colors.white;
  static const outline = Color(0xFFE1E4E8);
  static const text = Color(0xFF12264E);
  static const textMuted = Color(0xFF5F676C);
}

ThemeData buildAppTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: AppColors.blue,
    primary: AppColors.blue,
    onPrimary: Colors.white,
    secondary: AppColors.lightBlue,
    surface: AppColors.surface,
    onSurface: AppColors.text,
    onSurfaceVariant: AppColors.textMuted,
    outlineVariant: AppColors.outline,
    error: AppColors.coral,
  );

  final base = ThemeData(colorScheme: scheme, useMaterial3: true);
  final text = base.textTheme.apply(
    bodyColor: AppColors.text,
    displayColor: AppColors.text,
  );

  return base.copyWith(
    scaffoldBackgroundColor: AppColors.background,
    // Functional icons: Material Symbols Sharp, unfilled, light weight (Charité CD).
    iconTheme: const IconThemeData(
      weight: 200,
      fill: 0,
      grade: 0,
      opticalSize: 24,
    ),
    textTheme: text.copyWith(
      headlineMedium: text.headlineMedium?.copyWith(
        fontWeight: FontWeight.w700,
        letterSpacing: -0.5,
      ),
      headlineSmall: text.headlineSmall?.copyWith(
        fontWeight: FontWeight.w700,
        letterSpacing: -0.3,
      ),
      titleLarge: text.titleLarge?.copyWith(fontWeight: FontWeight.w700),
      titleMedium: text.titleMedium?.copyWith(fontWeight: FontWeight.w600),
      bodyMedium: text.bodyMedium?.copyWith(height: 1.45),
      bodySmall: text.bodySmall?.copyWith(color: AppColors.textMuted),
    ),
    appBarTheme: AppBarTheme(
      titleTextStyle: text.titleLarge?.copyWith(
        fontSize: 22,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.3,
      ),
      backgroundColor: AppColors.background,
      surfaceTintColor: Colors.transparent,
      foregroundColor: AppColors.text,
      elevation: 0,
      centerTitle: false,
    ),
    cardTheme: CardThemeData(
      color: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: AppColors.outline),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.blue,
        foregroundColor: Colors.white,
        minimumSize: const Size.fromHeight(56),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: text.titleMedium?.copyWith(fontSize: 17),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.blue,
        minimumSize: const Size.fromHeight(52),
        side: const BorderSide(color: AppColors.outline, width: 1.5),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: text.titleMedium?.copyWith(fontSize: 16),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: AppColors.blue,
        textStyle: text.titleMedium?.copyWith(fontSize: 16),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      indicatorColor: AppColors.blueSoft,
      elevation: 0,
      height: 72,
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => text.labelSmall?.copyWith(
          fontSize: 12,
          fontWeight: states.contains(WidgetState.selected)
              ? FontWeight.w700
              : FontWeight.w500,
          color: states.contains(WidgetState.selected)
              ? AppColors.blue
              : AppColors.textMuted,
        ),
      ),
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          weight: states.contains(WidgetState.selected) ? 400 : 200,
          fill: 0,
          color: states.contains(WidgetState.selected)
              ? AppColors.blue
              : AppColors.textMuted,
        ),
      ),
    ),
    listTileTheme: const ListTileThemeData(
      iconColor: AppColors.blue,
      contentPadding: EdgeInsets.symmetric(horizontal: 20, vertical: 2),
    ),
    dividerTheme: const DividerThemeData(
      color: AppColors.outline,
      thickness: 1,
      space: 1,
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: AppColors.darkBlue,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
  );
}
