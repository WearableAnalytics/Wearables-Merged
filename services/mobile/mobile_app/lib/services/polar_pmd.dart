import 'dart:async';
import 'dart:typed_data';

import 'package:universal_ble/universal_ble.dart';

import 'polar_recording.dart';

// Polar Measurement Data service, online measurement protocol.
// https://github.com/polarofficial/polar-ble-sdk/tree/master/technical_documentation
const polarPmdService = 'fb005c80-02e7-f387-1cad-8acd2d8df0c8';
const _control = 'fb005c81-02e7-f387-1cad-8acd2d8df0c8';
const _data = 'fb005c82-02e7-f387-1cad-8acd2d8df0c8';

List<int> _temperatureWords(ByteData d, bool compressed) {
  final words = <int>[];
  var offset = 10;
  if (d.lengthInBytes < offset + 4) {
    throw const FormatException('Short temperature frame');
  }
  if (!compressed) {
    if ((d.lengthInBytes - offset) % 4 != 0) {
      throw const FormatException('Truncated temperature');
    }
    while (offset < d.lengthInBytes) {
      words.add(d.getUint32(offset, Endian.little));
      offset += 4;
    }
    return words;
  }
  var previous = d.getUint32(offset, Endian.little);
  words.add(previous);
  offset += 4;
  while (offset < d.lengthInBytes) {
    if (offset + 2 > d.lengthInBytes) {
      throw const FormatException('Incomplete delta header');
    }
    final width = d.getUint8(offset++);
    final count = d.getUint8(offset++);
    final size = (width * count + 7) ~/ 8;
    if (width > 32 || offset + size > d.lengthInBytes) {
      throw const FormatException('Invalid delta frame');
    }
    var bit = 0;
    for (var i = 0; i < count; i++) {
      var delta = 0;
      for (var k = 0; k < width; k++, bit++) {
        delta |= ((d.getUint8(offset + bit ~/ 8) >> (bit % 8)) & 1) << k;
      }
      previous = (previous + (width == 0 ? 0 : delta.toSigned(width)))
          .toUnsigned(32);
      words.add(previous);
    }
    offset += size;
  }
  return words;
}

List<PolarSample> decodePolarFrame(
  Uint8List bytes,
  int type,
  DateTime receivedAt, {
  required int sampleHz,
}) {
  if (bytes.isEmpty || bytes.first != type) return [];
  if (bytes.length < 10) throw const FormatException('Incomplete Polar frame');
  final d = ByteData.sublistView(bytes);
  final ns = d.getUint64(1, Endian.little);
  // Some PPI streams omit the clock. Anchor those packets to reception on the phone.
  final end = ns == 0
      ? receivedAt.toUtc()
      : DateTime.utc(2000).add(Duration(microseconds: ns ~/ 1000));
  if (type == 3) {
    if (bytes[9] != 0 || (bytes.length - 10) % 6 != 0) {
      throw const FormatException('Unexpected PPI format');
    }
    var at = end;
    final samples = <PolarSample>[];
    for (var pos = bytes.length - 6; pos >= 10; pos -= 6) {
      final interval = d.getUint16(pos + 1, Endian.little);
      final flags = bytes[pos + 5];
      if (interval > 0 &&
          flags & 1 == 0 &&
          (flags & 4 == 0 || flags & 2 != 0)) {
        samples.add((value: interval, time: at));
      }
      at = at.subtract(Duration(milliseconds: interval));
    }
    return samples.reversed.toList();
  }
  if ((type != 7 && type != 12) || bytes[9] & 127 != 0 || sampleHz < 1) {
    throw const FormatException('Unexpected temperature format');
  }
  final words = _temperatureWords(d, bytes[9] & 128 != 0);
  final samples = <PolarSample>[];
  for (var i = 0; i < words.length; i++) {
    final word = ByteData(4)..setUint32(0, words[i], Endian.little);
    final value = word.getFloat32(0, Endian.little);
    if (!value.isFinite) continue;
    samples.add((
      value: value,
      time: end.subtract(
        Duration(
          microseconds: ((words.length - 1 - i) * 1000000 / sampleHz).round(),
        ),
      ),
    ));
  }
  return samples;
}

class PolarPmd {
  PolarPmd(this.device);
  final String device;
  int? _startedType;
  StreamSubscription<Uint8List>? _dataSub, _controlSub;
  void Function(Uint8List)? _onReply;

  Future<List<int>> _command(
    int opcode,
    int type, [
    List<int> settings = const [],
  ]) async {
    final result = Completer<List<int>>();
    final payload = <int>[];
    _onReply = (bytes) {
      if (result.isCompleted ||
          bytes.length < 4 ||
          bytes[0] != 0xf0 ||
          bytes[1] != opcode ||
          bytes[2] != type) {
        return;
      }
      if (bytes[3] != 0) {
        result.completeError(
          StateError('Polar rejected the stream command (status ${bytes[3]}).'),
        );
        return;
      }
      if (bytes.length > 5) payload.addAll(bytes.skip(5));
      if (bytes.length == 4 || bytes[4] == 0) result.complete(payload);
    };
    try {
      final responses = await Future.wait<dynamic>([
        result.future.timeout(const Duration(seconds: 8)),
        UniversalBle.write(
          device,
          polarPmdService,
          _control,
          Uint8List.fromList([opcode, type, ...settings]),
        ),
      ], eagerError: true);
      return responses.first as List<int>;
    } finally {
      _onReply = null;
    }
  }

  Future<void> start(
    PolarMetric metric,
    String name,
    void Function(List<PolarSample>) onSamples,
    void Function(Object) onError,
  ) async {
    final features = await UniversalBle.read(device, polarPmdService, _control);
    if (features.length < 3 || features.first != 15) {
      throw StateError('Polar streaming capabilities unavailable.');
    }
    final int type;
    if (metric == PolarMetric.pulseInterval && features[1] & 8 != 0) {
      type = 3;
    } else if (metric == PolarMetric.skinTemperature &&
        features[1] & 128 != 0) {
      type = 7;
    } else if (metric == PolarMetric.skinTemperature &&
        RegExp(r'^Polar (360|Loop)\b', caseSensitive: false).hasMatch(name) &&
        features[2] & 16 != 0) {
      // The 360/Loop uses a wrist skin sensor; other devices may report ambient temperature.
      type = 12;
    } else {
      throw StateError('This Polar does not offer the selected live stream.');
    }
    _controlSub = UniversalBle.characteristicValueStream(
      device,
      _control,
    ).listen((v) => _onReply?.call(v), onError: onError);
    await UniversalBle.subscribeIndications(device, polarPmdService, _control);
    var hz = 1;
    final settings = <int>[];
    if (type != 3) {
      final available = await _command(1, type);
      const widths = {0: 2, 1: 2, 2: 2, 3: 4, 4: 1, 5: 4};
      for (var i = 0; i < available.length;) {
        if (i + 2 > available.length) {
          throw const FormatException('Incomplete stream settings');
        }
        final key = available[i++], count = available[i++];
        final width = widths[key];
        if (width == null ||
            count == 0 ||
            i + width * count > available.length) {
          throw const FormatException('Unsupported stream settings');
        }
        if (key != 5) {
          final values = [
            for (var n = 0; n < count; n++)
              available.sublist(i + n * width, i + (n + 1) * width),
          ];
          int number(List<int> b) =>
              b.asMap().entries.fold(0, (a, e) => a | (e.value << (8 * e.key)));
          values.sort((a, b) => number(a).compareTo(number(b)));
          final choice = key == 1 ? values.last : values.first;
          settings.addAll([key, 1, ...choice]);
          if (key == 0) hz = number(choice);
        }
        i += width * count;
      }
    }
    _dataSub = UniversalBle.characteristicValueStream(device, _data).listen((
      v,
    ) {
      try {
        onSamples(decodePolarFrame(v, type, DateTime.now(), sampleHz: hz));
      } on FormatException catch (e) {
        onError(e);
      }
    }, onError: onError);
    await UniversalBle.subscribeNotifications(device, polarPmdService, _data);
    await _command(2, type, settings);
    _startedType = type;
  }

  Future<void> close() async {
    try {
      if (_startedType != null) await _command(3, _startedType!);
    } finally {
      await _dataSub?.cancel();
      await _controlSub?.cancel();
    }
  }
}
