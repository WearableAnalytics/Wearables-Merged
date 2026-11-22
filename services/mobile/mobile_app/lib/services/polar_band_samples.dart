import 'dart:typed_data';

import 'package:protobuf/protobuf.dart';

import 'polar_files.dart';
import 'polar_recording.dart';

typedef BandReading = ({
  PolarMetric metric,
  DateTime time,
  num value,
  String id,
});

extension on UnknownFieldSet {
  int integer(int tag, {int? fallback}) {
    final n = getField(tag)?.varints.singleOrNull;
    if (n != null) return n.toInt();
    if (fallback != null) return fallback;
    throw const FormatException('Missing Polar field');
  }

  Iterable<UnknownFieldSet> messages(int tag) =>
      (getField(tag)?.lengthDelimited ?? <List<int>>[]).map(polarMessage);

  Iterable<int> numbers(int tag) sync* {
    final field = getField(tag);
    if (field == null) return;
    for (final n in field.varints) {
      yield n.toInt();
    }
    for (final packed in field.lengthDelimited) {
      final reader = CodedBufferReader(packed);
      while (!reader.isAtEnd()) {
        yield reader.readUint32();
      }
    }
  }
}

// The band's automatic samples encode study-local calendar dates and wall times.
// Use the recorded session time + sample ordinal as identity across file rewrites.
Iterable<BandReading> polarAutomaticSamples(List<int> bytes) sync* {
  final message = polarMessage(bytes);
  final date = message.messages(1).single;
  final year = date.integer(1), month = date.integer(2), day = date.integer(3);
  DateTime start(UnknownFieldSet session) {
    final clock = session.messages(2).single;
    final h = clock.integer(1), m = clock.integer(2), s = clock.integer(3);
    final ms = clock.integer(4, fallback: 0);
    final at = DateTime(year, month, day, h, m, s, ms);
    if (at.year != year ||
        at.month != month ||
        at.day != day ||
        at.hour != h ||
        at.minute != m ||
        at.second != s ||
        at.millisecond != ms) {
      throw const FormatException('Invalid Polar recording time');
    }
    return at.toUtc();
  }

  for (final session in message.messages(2)) {
    final at = start(session);
    final origin = at.millisecondsSinceEpoch;
    var i = 0;
    for (final bpm in session.numbers(3)) {
      if (bpm > 0 && bpm <= 250) {
        yield (
          metric: PolarMetric.heartRate,
          time: at.add(Duration(seconds: i)),
          value: bpm,
          id: 'hr-$origin-${session.integer(1)}-$i',
        );
      }
      i++;
    }
  }
  for (final session in message.messages(3)) {
    var at = start(session);
    final origin = at.millisecondsSinceEpoch;
    final ppi = session.messages(3).single;
    final flags = ppi.numbers(3).iterator;
    var interval = 0, i = 0;
    for (final delta in ppi.numbers(1)) {
      interval += (delta >> 1) ^ -(delta & 1);
      if (interval < 0 || !flags.moveNext()) {
        throw const FormatException('Invalid interval series');
      }
      if (interval > 0 && (flags.current & 7) == 1) {
        yield (
          metric: PolarMetric.pulseInterval,
          time: at,
          value: interval,
          id: 'ppi-$origin-$i',
        );
      }
      at = at.add(Duration(milliseconds: interval));
      i++;
    }
    if (flags.moveNext()) throw const FormatException('Invalid interval flags');
  }
}

Iterable<BandReading> polarTemperatureSamples(
  DateTime localDay,
  List<int> bytes,
) sync* {
  final period = polarMessage(bytes);
  if (period.integer(1, fallback: 0) != 1) return;
  for (final sample in period.messages(4)) {
    final delta = sample.integer(1, fallback: 0);
    final bits = sample.getField(2)?.fixed32s.singleOrNull ?? 0;
    final value = (ByteData(4)..setUint32(0, bits)).getFloat32(0);
    if (!value.isFinite ||
        value < -40 ||
        value > 125 ||
        delta < 0 ||
        delta >= const Duration(hours: 25).inMilliseconds) {
      throw const FormatException('Invalid skin temperature sample');
    }
    final at = localDay.add(Duration(milliseconds: delta)).toUtc();
    yield (
      metric: PolarMetric.skinTemperature,
      time: at,
      value: value,
      id: 'temp-${at.millisecondsSinceEpoch}',
    );
  }
}
