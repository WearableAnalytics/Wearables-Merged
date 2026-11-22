import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:protobuf/protobuf.dart';
import 'package:universal_ble/universal_ble.dart';

// Read-only Polar PS-FTP. RFC60 GET envelope carried by RFC76 frames.
// Protocol definitions: polarofficial/polar-ble-sdk, technical_documentation.
class PolarFiles {
  PolarFiles(this.device);
  final String device;
  static const service = '0000feee-0000-1000-8000-00805f9b34fb';
  static const pipe = 'fb005c51-02e7-f387-1cad-8acd2d8df0c8';

  Future<void> open() async {
    await UniversalBle.connect(device, timeout: const Duration(seconds: 9));
    final services = await UniversalBle.discoverServices(device);
    final characteristic = services
        .where((s) => s.uuid == service)
        .expand((s) => s.characteristics)
        .where((c) => c.uuid == pipe)
        .firstOrNull;
    if (characteristic == null) {
      throw UnsupportedError('Band history unavailable');
    }
    if (characteristic.properties.contains(CharacteristicProperty.indicate)) {
      await UniversalBle.subscribeIndications(device, service, pipe);
    } else {
      await UniversalBle.subscribeNotifications(device, service, pipe);
    }
  }

  Future<void> close() =>
      UniversalBle.disconnect(device, timeout: const Duration(seconds: 4));

  Future<Uint8List?> read(String path) async {
    final name = ascii.encode(path);
    if (name.length > 100) throw ArgumentError('Polar file path too long');
    final operation = [8, 0, 18, name.length, ...name];
    final request = [operation.length, 0, ...operation];
    final packets = UniversalBle.characteristicValueStream(device, pipe);
    final response = Completer<Uint8List?>();
    final bytes = BytesBuilder(copy: false);
    var sequence = 0;
    final subscription = packets.listen(
      (frame) {
        if (response.isCompleted) return;
        try {
          if (frame.isEmpty ||
              frame.first >> 4 != sequence % 16 ||
              (frame.first & 1) != (sequence == 0 ? 0 : 1)) {
            throw const FormatException('Incomplete Polar file transfer');
          }
          sequence++;
          final status = (frame[0] >> 1) & 3;
          if (status == 0) {
            if (frame.length != 3) {
              throw const FormatException('Invalid Polar reply');
            }
            final error = frame[1] | frame[2] << 8;
            if (error == 103) {
              response.complete(null);
              return;
            }
            if (error != 0) {
              throw StateError('Band file request failed ($error)');
            }
            response.complete(bytes.takeBytes());
            return;
          }
          if (status == 2 || bytes.length + frame.length > 4 * 1024 * 1024) {
            throw const FormatException('Invalid Polar file transfer');
          }
          bytes.add(frame.sublist(1));
          if (status == 1) response.complete(bytes.takeBytes());
        } catch (e, st) {
          response.completeError(e, st);
        }
      },
      onError: (Object e) {
        if (!response.isCompleted) response.completeError(e);
      },
    );
    try {
      Future<void> write() async {
        // 20 bytes also fits an unnegotiated ATT MTU.
        for (var offset = 0; offset < request.length; offset += 19) {
          final end = (offset + 19).clamp(0, request.length);
          final flags =
              ((offset ~/ 19 % 16) << 4) |
              (offset == 0 ? 0 : 1) |
              (end == request.length ? 2 : 6);
          await UniversalBle.write(
            device,
            service,
            pipe,
            Uint8List.fromList([flags, ...request.sublist(offset, end)]),
            timeout: const Duration(seconds: 5),
          );
        }
      }

      final (data, _) = await (
        response.future.timeout(const Duration(seconds: 18)),
        write(),
      ).wait;
      return data;
    } finally {
      await subscription.cancel();
    }
  }
}

UnknownFieldSet polarMessage(List<int> data) {
  final reader = CodedBufferReader(data);
  final message = UnknownFieldSet()..mergeFromCodedBufferReader(reader);
  reader.checkLastTagWas(0);
  return message;
}

typedef PolarEntry = ({String name, String? revision});

Iterable<PolarEntry> polarDirectory(List<int> bytes) sync* {
  for (final entry
      in polarMessage(bytes).getField(1)?.lengthDelimited ?? <List<int>>[]) {
    final item = polarMessage(entry);
    final name = item.getField(1)?.lengthDelimited.single;
    final modified = item.getField(4)?.lengthDelimited.singleOrNull;
    final size = item.getField(2)?.varints.singleOrNull;
    if (name != null) {
      yield (
        name: utf8.decode(name),
        revision: modified == null || modified.isEmpty || size == null
            ? null
            : '$size:${base64.encode(modified)}',
      );
    }
  }
}
