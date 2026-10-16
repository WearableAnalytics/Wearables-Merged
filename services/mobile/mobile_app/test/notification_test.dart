import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:charite_wearables/services/health_sync_service.dart';
import 'package:charite_wearables/services/notification_service.dart';
import 'package:charite_wearables/storage_service.dart';

// {"caseId":"x","exp":1700000000} and {"caseId":"x","exp":4102444800}.
const _expired =
    'eyJhbGciOiJIUzI1NiJ9.eyJjYXNlSWQiOiJ4IiwiZXhwIjoxNzAwMDAwMDAwfQ.c2ln';
const _valid =
    'eyJhbGciOiJIUzI1NiJ9.eyJjYXNlSWQiOiJ4IiwiZXhwIjo0MTAyNDQ0ODAwfQ.c2ln';
const _noExp = 'eyJhbGciOiJIUzI1NiJ9.eyJjYXNlSWQiOiJ4In0.c2ln';

void main() {
  group('action notifications', () {
    final now = DateTime(2026, 10, 16, 12);
    bool notify(String reason, String? last, Duration? ago) =>
        NotificationService.shouldNotify(
          reason: reason,
          lastReason: last,
          lastAt: ago == null ? null : now.subtract(ago),
          now: now,
        );

    test('first problem is announced', () {
      expect(notify('permission', null, null), isTrue);
    });

    test('never more than one per hour', () {
      expect(
        notify('code', 'permission', const Duration(minutes: 59)),
        isFalse,
      );
      expect(notify('code', 'permission', const Duration(hours: 1)), isTrue);
    });

    test('the same problem is repeated at most daily', () {
      expect(
        notify('permission', 'permission', const Duration(hours: 5)),
        isFalse,
      );
      expect(
        notify('permission', 'permission', const Duration(days: 1)),
        isTrue,
      );
    });

    test('only problems the user can fix are announced', () {
      expect(
        NotificationService.actionReason(HealthSyncStatus.permissionDenied),
        'permission',
      );
      expect(
        NotificationService.actionReason(HealthSyncStatus.codeExpired),
        'code',
      );
      for (final status in [
        HealthSyncStatus.success,
        HealthSyncStatus.failed,
        HealthSyncStatus.protectedDataUnavailable,
      ]) {
        expect(NotificationService.actionReason(status), isNull);
      }
    });
  });

  group('personal code expiry', () {
    test('reads the exp claim', () {
      expect(StorageService.isCodeExpired(_expired), isTrue);
      expect(StorageService.isCodeExpired(_valid), isFalse);
      expect(StorageService.isCodeExpired(_noExp), isFalse);
      expect(StorageService.isCodeExpired('iOS_123_456'), isFalse);
    });

    test('a refused code stays unusable until a new one is linked', () async {
      SharedPreferences.setMockInitialValues({'device_id': _valid});
      expect(await StorageService.isLinkedCodeUnusable(), isFalse);
      await StorageService.markCodeRejected(_valid);
      expect(await StorageService.isLinkedCodeUnusable(), isTrue);
      await StorageService.setCustomDeviceId(_valid);
      expect(await StorageService.isLinkedCodeUnusable(), isFalse);
    });
  });
}
