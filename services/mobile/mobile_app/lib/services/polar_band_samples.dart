import 'dart:typed_data';

import 'package:protobuf/protobuf.dart';

import 'polar_files.dart';
import 'polar_recording.dart';

typedef BandReading = ({
  PolarMetric metric,
  DateTime time,
  DateTime? end,
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
          end: null,
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
          end: null,
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
      end: null,
      metric: PolarMetric.skinTemperature,
      time: at,
      value: value,
      id: 'temp-${at.millisecondsSinceEpoch}',
    );
  }
}

// PbLocalDateTime optionally carries its UTC offset in minutes. Preserve it
// when present, including across the repeated hour at the end of summer time.
DateTime _localTimestamp(UnknownFieldSet msg) {
  final d = msg.messages(1).single, t = msg.messages(2).single;
  final year = d.integer(1), month = d.integer(2), day = d.integer(3);
  final h = t.integer(1),
      m = t.integer(2),
      s = t.integer(3),
      ms = t.integer(4, fallback: 0);
  final offset = msg.getField(4)?.varints.singleOrNull?.toSigned(32).toInt();
  final wall = offset == null
      ? DateTime(year, month, day, h, m, s, ms)
      : DateTime.utc(year, month, day, h, m, s, ms);
  if (wall.year != year ||
      wall.month != month ||
      wall.day != day ||
      wall.hour != h ||
      wall.minute != m ||
      wall.second != s ||
      wall.millisecond != ms ||
      (offset?.abs() ?? 0) > 14 * 60) {
    throw const FormatException('Invalid Polar calendar timestamp');
  }
  return wall.toUtc().subtract(Duration(minutes: offset ?? 0));
}

BandReading _period(PolarMetric metric, DateTime at, DateTime end, num value) =>
    (
      metric: metric,
      time: at.toUtc(),
      end: end.toUtc(),
      value: value,
      id: '${metric.name}-${at.millisecondsSinceEpoch}',
    );

Iterable<BandReading> polarActivitySamples(List<int> bytes) sync* {
  final file = polarMessage(bytes);
  for (final (tag, intervalTag, metric) in [
    (5, 3, PolarMetric.steps),
    (4, 2, PolarMetric.activityMet),
  ]) {
    if (!file.hasField(tag)) continue;
    var at = _localTimestamp(file.messages(1).single);
    final span = file.messages(intervalTag).single;
    final interval = Duration(
      hours: span.integer(1, fallback: 0),
      minutes: span.integer(2, fallback: 0),
      seconds: span.integer(3, fallback: 0),
      milliseconds: span.integer(4, fallback: 0),
    );
    if (interval <= Duration.zero || interval > const Duration(days: 1)) {
      throw const FormatException('Invalid activity sampling interval');
    }
    final values = metric == PolarMetric.steps
        ? file.numbers(tag)
        : _floatSamples(file.getField(tag)!);
    for (final value in values) {
      final end = at.add(interval);
      if (!value.isFinite || value < 0) {
        throw const FormatException('Invalid activity sample');
      }
      yield _period(metric, at, end, value);
      at = end;
    }
  }
}

Iterable<double> _floatSamples(UnknownFieldSetField field) sync* {
  for (final n in field.fixed32s) {
    yield (ByteData(4)..setUint32(0, n)).getFloat32(0);
  }
  for (final bytes in field.lengthDelimited) {
    if (bytes.length % 4 != 0) {
      throw const FormatException('Invalid packed MET sample');
    }
    final data = ByteData.sublistView(Uint8List.fromList(bytes));
    for (var i = 0; i < bytes.length; i += 4) {
      yield data.getFloat32(i, Endian.little);
    }
  }
}

Iterable<BandReading> polarWorkout(List<int> bytes) sync* {
  final file = polarMessage(bytes);
  if (!file.hasField(20)) return; // Active session has no final end time.
  final at = _localTimestamp(file.messages(1).single),
      end = _localTimestamp(file.messages(20).single);
  if (!end.isAfter(at)) throw const FormatException('Invalid training session');
  yield _period(
    PolarMetric.workoutTime,
    at,
    end,
    end.difference(at).inMilliseconds / 60000,
  );
  if (file.hasField(7)) {
    yield _period(PolarMetric.workoutEnergy, at, end, file.integer(7));
  }
}

Iterable<BandReading> polarDailyTotals(DateTime day, List<int> bytes) sync* {
  final file = polarMessage(bytes), date = file.messages(1).single;
  if (date.integer(1) != day.year ||
      date.integer(2) != day.month ||
      date.integer(3) != day.day) {
    throw const FormatException('Unexpected daily summary date');
  }
  final end = DateTime(day.year, day.month, day.day + 1);
  for (final (tag, metric) in [
    (3, PolarMetric.activityEnergy),
    (5, PolarMetric.basalEnergy),
  ]) {
    if (file.hasField(tag)) yield _period(metric, day, end, file.integer(tag));
  }
  final bits = file.getField(8)?.fixed32s.singleOrNull;
  if (bits != null) {
    final meters = (ByteData(4)..setUint32(0, bits)).getFloat32(0);
    if (!meters.isFinite || meters < 0) {
      throw const FormatException('Invalid activity distance');
    }
    yield _period(PolarMetric.activityDistance, day, end, meters);
  }
}

(DateTime, DateTime) polarSleepWindow(List<int> bytes) {
  final file = polarMessage(bytes);
  final start = _localTimestamp(file.messages(1).single),
      end = _localTimestamp(file.messages(2).single);
  if (!end.isAfter(start) || end.difference(start) > const Duration(days: 1)) {
    throw const FormatException('Invalid Polar sleep window');
  }
  return (start, end);
}

Iterable<BandReading> polarSleepPhases(List<int> bytes) sync* {
  final (start, end) = polarSleepWindow(bytes);
  final phases = polarMessage(bytes).messages(5).toList();
  for (var i = 0; i < phases.length; i++) {
    DateTime boundary(int n) =>
        start.add(Duration(seconds: phases[n].integer(1, fallback: 0)));
    final at = boundary(i),
        until = i + 1 < phases.length ? boundary(i + 1) : end;
    if (at.isBefore(start) || until.isBefore(at) || until.isAfter(end)) {
      throw const FormatException('Invalid Polar sleep phase');
    }
    final state = phases[i]
        .getField(2)
        ?.varints
        .singleOrNull
        ?.toSigned(32)
        .toInt();
    final metric = switch (state) {
      -2 => PolarMetric.sleepAwake,
      -3 => PolarMetric.sleepRem,
      -5 => PolarMetric.sleepLight,
      -6 => PolarMetric.sleepDeep,
      _ => null,
    };
    if (metric != null && until.isAfter(at)) {
      if (metric != PolarMetric.sleepAwake) {
        yield _period(
          PolarMetric.sleepAsleep,
          at,
          until,
          until.difference(at).inMilliseconds / 60000,
        );
      }
      yield _period(
        metric,
        at,
        until,
        until.difference(at).inMilliseconds / 60000,
      );
    }
  }
}

// Polar summarizes the four hours beginning 30 minutes after sleep onset.
Iterable<BandReading> polarNightlyRecovery(
  DateTime day,
  (DateTime, DateTime) sleep,
  List<int> bytes,
) sync* {
  final file = polarMessage(bytes), date = file.messages(20).single;
  if (date.integer(1) != day.year ||
      date.integer(2) != day.month ||
      date.integer(3) != day.day) {
    throw const FormatException('Unexpected recovery date');
  }
  final at = sleep.$1.add(const Duration(minutes: 30)),
      end = at.add(const Duration(hours: 4));
  if (end.isAfter(sleep.$2)) return;
  for (final (tag, metric) in [
    (9, PolarMetric.nightlyHrv),
    (10, PolarMetric.nightlyBreathing),
  ]) {
    if (!file.hasField(tag)) continue;
    final n = file.getField(tag)!.varints.single.toSigned(32).toInt();
    if (n <= 0) continue;
    yield _period(metric, at, end, tag == 9 ? n : 60000 / n);
  }
}
