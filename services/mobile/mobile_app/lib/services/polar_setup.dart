import 'dart:convert';
import 'dart:typed_data';

import 'package:collection/collection.dart';
import 'package:crypto/crypto.dart';
import 'package:fixnum/fixnum.dart';
import 'package:protobuf/protobuf.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:universal_ble/universal_ble.dart';

import 'polar_files.dart';

// Field numbers and units follow Polar's proto2 user_physdata, user_id,
// types and pftp_request definitions. Embedded messages use wire type 2.
Uint8List _message(void Function(CodedBufferWriter) build) {
  final out = CodedBufferWriter();
  build(out);
  return out.toBuffer();
}

extension on CodedBufferWriter {
  void bytes(int tag, List<int> value) =>
      writeField(tag, PbFieldType.OY, value);
  void number(int tag, int value) => writeField(tag, PbFieldType.O3, value);
}

Uint8List _date(DateTime t) => _message(
  (w) => w
    ..number(1, t.year)
    ..number(2, t.month)
    ..number(3, t.day),
);

Uint8List polarSetupClock(DateTime t, {required bool system}) {
  t = system ? t.toUtc() : t.toLocal();
  final time = _message(
    (w) => w
      ..number(1, t.hour)
      ..number(2, t.minute)
      ..number(3, t.second)
      ..number(4, t.millisecond),
  );
  return _message(
    (w) => w
      ..bytes(1, _date(t))
      ..bytes(2, time)
      ..number(3, system ? 1 : t.timeZoneOffset.inMinutes),
  );
}

class PolarSetupProfile {
  const PolarSetupProfile({
    required this.birthday,
    required this.sex,
    required this.height,
    required this.weight,
    required this.maximum,
    required this.resting,
    required this.vo2,
    required this.training,
    required this.typicalDay,
    required this.sleepMinutes,
  });

  final DateTime birthday;
  final double height, weight;
  final int sex, maximum, resting, vo2, training, typicalDay, sleepMinutes;

  Uint8List encode(DateTime now) {
    final today = now.toLocal();
    if (!birthday.isBefore(DateTime(today.year, today.month, today.day)) ||
        birthday.year < 1900 ||
        ![1, 2].contains(sex) ||
        !height.isFinite ||
        height < 90 ||
        height > 240 ||
        !weight.isFinite ||
        weight < 15 ||
        weight > 300 ||
        maximum < 100 ||
        maximum > 240 ||
        resting < 20 ||
        resting > 120 ||
        resting >= maximum ||
        vo2 < 10 ||
        vo2 > 95 ||
        ![10, 20, 30, 40, 50, 60].contains(training) ||
        ![1, 2, 3].contains(typicalDay) ||
        sleepMinutes < 300 ||
        sleepMinutes > 660) {
      throw const FormatException('Check the device profile values.');
    }
    final modified = polarSetupClock(now, system: true);
    Uint8List field(int type, Object value) => _message(
      (w) => w
        ..writeField(1, type, value)
        ..bytes(2, modified),
    );
    return _message(
      (w) => w
        ..bytes(1, field(PbFieldType.OY, _date(birthday)))
        ..bytes(2, field(PbFieldType.O3, sex))
        ..bytes(3, field(PbFieldType.OF, weight))
        ..bytes(4, field(PbFieldType.OF, height))
        ..bytes(5, field(PbFieldType.O3, maximum))
        ..bytes(6, field(PbFieldType.O3, resting))
        ..bytes(10, field(PbFieldType.O3, vo2))
        ..bytes(11, field(PbFieldType.O3, training))
        ..bytes(12, field(PbFieldType.O3, typicalDay))
        ..bytes(17, field(PbFieldType.O3, sleepMinutes))
        ..bytes(100, modified),
    );
  }
}

enum PolarSetupState { fresh, interrupted, configured }

class PolarSetup {
  PolarSetup(this.files);
  final PolarFiles files;
  static const userPath = '/U/0/USERID.BPB';
  static const profilePath = '/U/0/S/PHYSDATA.BPB';
  final _prefs = SharedPreferencesAsync();
  String get _key => 'polar_ftu_pending_${files.device}';

  Future<void> checkModel() async {
    final info = await files.read('/DEVICE.BPB');
    final name = info == null
        ? null
        : polarMessage(info).getField(7)?.lengthDelimited.singleOrNull;
    bool matches(List<int>? value) =>
        value != null &&
        RegExp(
          r'^(polar\s+)?360$',
          caseSensitive: false,
        ).hasMatch(utf8.decode(value).replaceAll('\u0000', '').trim());
    if (matches(name)) return;
    final dis = await UniversalBle.read(files.device, '180a', '2a24');
    if (!matches(dis)) {
      throw UnsupportedError('Could not identify this band as a Polar 360.');
    }
  }

  Future<PolarSetupState> state() async {
    final user = await files.read(userPath);
    if (user == null) return PolarSetupState.fresh;
    final id = polarMessage(user);
    if (!id.hasField(1)) {
      if (id.asMap().isNotEmpty) {
        throw const FormatException('Unrecognised device setup state');
      }
      return PolarSetupState.fresh;
    }
    if (id.getField(1)!.varints.length != 1) {
      throw const FormatException('Invalid device identifier');
    }
    // Resume only our own interrupted setup, identified by its complete marker
    // (including timestamp). A previously configured band is never reconfigured.
    return await _prefs.getString(_key) == base64Encode(user)
        ? PolarSetupState.interrupted
        : PolarSetupState.configured;
  }

  // The Bluetooth address can survive a reset. Bind sharing to the device's
  // actual setup marker as well, so a replacement wearer needs a new grant.
  Future<String?> identity() async {
    final bytes = await files.read(userPath);
    if (bytes == null || polarMessage(bytes).getField(1)?.varints.length != 1) {
      return null;
    }
    return sha256.convert(bytes).toString();
  }

  Future<PolarSetupState> inspect() async {
    await checkModel();
    return state();
  }

  Future<bool> configure(PolarSetupProfile profile, DateTime now) async {
    final phys = profile.encode(now);
    await checkModel();
    if (await state() == PolarSetupState.configured) return false;
    await files.setupQuery(13); // Acquire the band's synchronization session.
    await files.setupNotification(8);
    var started = false;
    var stopped = false;
    late List<int> marker;
    try {
      await files.setupNotification(0);
      started = true;
      final current = await state();
      if (current == PolarSetupState.configured) return false;
      marker = current == PolarSetupState.interrupted
          ? base64Decode((await _prefs.getString(_key))!)
          : _message(
              (w) => w
                ..writeField(1, PbFieldType.OU6, Int64(-1))
                ..bytes(100, polarSetupClock(now, system: true)),
            );
      // Keep only the SDK's account-free identifier marker for recovery.
      await _prefs.setString(_key, base64Encode(marker));
      await files.setupQuery(3, polarSetupClock(now, system: false));
      await files.setupQuery(1, polarSetupClock(now, system: true));
      if (current == PolarSetupState.fresh) {
        await files.putSetupFile(userPath, marker);
      }
      await files.putSetupFile(profilePath, phys);
      if (!const ListEquality<int>().equals(
            await files.read(userPath),
            marker,
          ) ||
          !const ListEquality<int>().equals(
            await files.read(profilePath),
            phys,
          )) {
        throw StateError('Band did not confirm the setup values');
      }
      await files.setupNotification(1, [8, 1]);
      stopped = true;
    } finally {
      try {
        if (started && !stopped) await files.setupNotification(1, [8, 0]);
      } finally {
        await files.setupNotification(9);
      }
    }
    await _prefs.remove(_key);
    return true;
  }
}
