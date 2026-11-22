import 'dart:convert';
import 'dart:typed_data';
import 'package:protobuf/protobuf.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:charite_wearables/screens/polar_setup_page.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:charite_wearables/services/polar_files.dart';
import 'package:charite_wearables/services/polar_setup.dart';

final class Band extends PolarFiles {
  Band() : super('test-device');
  final stored = <String, Uint8List>{};
  final events = <String>[];
  bool failProfile = false;
  Uint8List Function(String, Uint8List)? serialize;
  @override
  Future<Uint8List?> read(String path) async => stored[path];
  @override
  Future<void> setupQuery(int id, [List<int> payload = const []]) async =>
      events.add('query:$id');
  @override
  Future<void> setupNotification(
    int id, [
    List<int> payload = const [],
  ]) async => events.add('notify:$id:$payload');
  @override
  Future<void> putSetupFile(String path, List<int> contents) async {
    events.add('put:$path');
    if (path == PolarSetup.profilePath && failProfile) {
      throw StateError('disconnected');
    }
    final bytes = Uint8List.fromList(contents);
    stored[path] = serialize?.call(path, bytes) ?? bytes;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Band band;
  late PolarSetup setup;
  final time = DateTime.utc(2025, 8, 5, 12, 9, 1, 2);
  final profile = PolarSetupProfile(
    birthday: DateTime(1997, 6, 15),
    sex: 2,
    height: 171.5,
    weight: 69.5,
    maximum: 190,
    resting: 55,
    vo2: 45,
    training: 20,
    typicalDay: 2,
    sleepMinutes: 480,
  );
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    band = Band();
    band.stored['/DEVICE.BPB'] = Uint8List.fromList([
      58,
      9,
      ...ascii.encode('Polar 360'),
    ]);
    setup = PolarSetup(band);
  });
  test(
    'profile matches independent protoc encoding from Polar user_physdata.proto',
    () {
      expect(
        base64Encode(profile.encode(time)),
        'CiAKBwjNDxAGGA8SFQoHCOkPEAgYBRIICAwQCRgBIAIYARIZCAISFQoHCOkPEAgYBRIICAwQCRgBIAIYARocDQAAi0ISFQoHCOkPEAgYBRIICAwQCRgBIAIYASIcDQCAK0MSFQoHCOkPEAgYBRIICAwQCRgBIAIYASoaCL4BEhUKBwjpDxAIGAUSCAgMEAkYASACGAEyGQg3EhUKBwjpDxAIGAUSCAgMEAkYASACGAFSGQgtEhUKBwjpDxAIGAUSCAgMEAkYASACGAFaGQgUEhUKBwjpDxAIGAUSCAgMEAkYASACGAFiGQgCEhUKBwjpDxAIGAUSCAgMEAkYASACGAGKARoI4AMSFQoHCOkPEAgYBRIICAwQCRgBIAIYAaIGFQoHCOkPEAgYBRIICAwQCRgBIAIYAQ==',
      );
    },
  );
  test(
    'fresh setup writes both clock queries and profile then verifies, without a grant',
    () async {
      expect(await setup.inspect(), PolarSetupState.fresh);
      expect(band.events, isEmpty);
      expect(await setup.configure(profile, time), isTrue);
      expect(band.events, [
        'query:13',
        'notify:8:[]',
        'notify:0:[]',
        'query:3',
        'query:1',
        'put:/U/0/USERID.BPB',
        'put:/U/0/S/PHYSDATA.BPB',
        'notify:1:[8, 1]',
        'notify:9:[]',
      ]);
      expect(await setup.inspect(), PolarSetupState.configured);

      band.events.clear();
      expect(await setup.configure(profile, time), isFalse);
      expect(
        band.events.where(
          (e) => e.startsWith('put:') || e == 'query:1' || e == 'query:3',
        ),
        isEmpty,
      );
    },
  );
  test(
    'an interrupted first setup is retried without overwriting an existing owner',
    () async {
      band.failProfile = true;
      await expectLater(setup.configure(profile, time), throwsStateError);
      expect(band.events, contains('notify:1:[8, 0]'));
      expect(await setup.inspect(), PolarSetupState.interrupted);
      band.failProfile = false;
      band.events.clear();
      expect(
        await setup.configure(profile, time.add(const Duration(minutes: 1))),
        isTrue,
      );
      expect(band.events.where((e) => e.startsWith('put:')), [
        'put:/U/0/S/PHYSDATA.BPB',
      ]);
      expect(await setup.inspect(), PolarSetupState.configured);
    },
  );
  test(
    'foreign marker after interruption prevents further device edits',
    () async {
      band.failProfile = true;
      await expectLater(setup.configure(profile, time), throwsStateError);
      band.stored[PolarSetup.userPath] = Uint8List.fromList([8, 42]);
      band.events.clear();
      expect(await setup.inspect(), PolarSetupState.configured);
      expect(band.events, isEmpty);
    },
  );
  test(
    'factory metadata without a master identifier allows first-time setup',
    () async {
      final stamp = polarSetupClock(time, system: true);
      band.stored[PolarSetup.userPath] = Uint8List.fromList([
        0xa2,
        0x06,
        stamp.length,
        ...stamp,
      ]);
      expect(await setup.inspect(), PolarSetupState.fresh);
      expect(await setup.identity(), isNull);
      expect(await setup.configure(profile, time), isTrue);
      expect(await setup.inspect(), PolarSetupState.configured);
    },
  );
  test('malformed factory timestamp prevents writing', () async {
    band.stored[PolarSetup.userPath] = Uint8List.fromList([0xa2, 0x06, 0]);
    await expectLater(setup.configure(profile, time), throwsFormatException);
    expect(band.events, isEmpty);
  });
  test(
    'firmware may omit marker milliseconds and add profile fields on readback',
    () async {
      Uint8List encode(UnknownFieldSet fields) {
        final writer = CodedBufferWriter();
        fields.writeToCodedBufferWriter(writer);
        return writer.toBuffer();
      }

      band.serialize = (path, bytes) {
        if (path == PolarSetup.profilePath) {
          return Uint8List.fromList([...bytes, 0x42, 0]);
        }
        final user = polarMessage(bytes);
        final clock = polarMessage(user.getField(100)!.lengthDelimited.single);
        final t = polarMessage(clock.getField(2)!.lengthDelimited.single)
          ..clearField(4);
        clock
          ..clearField(2)
          ..mergeLengthDelimitedField(2, encode(t));
        user
          ..clearField(100)
          ..mergeLengthDelimitedField(100, encode(clock));
        return encode(user);
      };
      band.failProfile = true;
      await expectLater(setup.configure(profile, time), throwsStateError);
      expect(await setup.inspect(), PolarSetupState.interrupted);
      band.failProfile = false;
      expect(await setup.configure(profile, time), isTrue);
      expect(await setup.inspect(), PolarSetupState.configured);
    },
  );
  test(
    'readback rejects a missing participant-entered profile value',
    () async {
      band.serialize = (path, bytes) {
        if (path != PolarSetup.profilePath) return bytes;
        final writer = CodedBufferWriter();
        (polarMessage(bytes)..clearField(6)).writeToCodedBufferWriter(writer);
        return writer.toBuffer();
      };
      await expectLater(setup.configure(profile, time), throwsStateError);
      expect(band.events, isNot(contains('notify:1:[8, 1]')));
    },
  );
  test('ambiguous identifier does not allow a write', () async {
    band.stored[PolarSetup.userPath] = Uint8List.fromList([18, 0]);
    await expectLater(setup.configure(profile, time), throwsFormatException);
    expect(band.events.where((e) => e.startsWith('put:')), isEmpty);
  });
  testWidgets('cancel and incomplete device profiles never submit settings', (
    tester,
  ) async {
    // Mount the whole form so fields remain accessible without scrolling.

    tester.view.physicalSize = const Size(1000, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    PolarSetupProfile? submitted;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () async {
                submitted = await Navigator.push<PolarSetupProfile>(
                  context,
                  MaterialPageRoute(
                    builder: (_) =>
                        const PolarSetupPage(band: 'Test Polar 360'),
                  ),
                );
              },
              child: const Text('Open setup'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open setup'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save settings to this band'));
    await tester.pumpAndSettle();
    expect(find.text('Select your date of birth.'), findsOneWidget);
    expect(submitted, isNull);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(submitted, isNull);
    expect(find.text('Open setup'), findsOneWidget);
  });
  test(
    'sharing identity changes when the same Bluetooth device gets a new owner marker',
    () async {
      expect(await setup.identity(), isNull);
      await setup.configure(profile, time);
      final current = await setup.identity();
      expect(current, isNotNull);
      band.stored[PolarSetup.userPath] = Uint8List.fromList([8, 42]);
      expect(await setup.identity(), isNot(current));
    },
  );
}
