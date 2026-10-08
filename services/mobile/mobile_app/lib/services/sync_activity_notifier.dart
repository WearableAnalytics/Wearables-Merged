import 'package:flutter/foundation.dart';

/// Tracks whether any health-data sync is currently running (manual or automatic).
/// Uses a simple reference count so overlapping syncs keep the indicator active
/// until every caller finishes.
enum SyncOutcome { success, nothingToSend, failure }

class SyncActivityNotifier {
  SyncActivityNotifier._();

  static final ValueNotifier<bool> isSyncing = ValueNotifier<bool>(false);
  static final ValueNotifier<SyncOutcome?> lastResult = ValueNotifier(null);

  /// Share of the current sync's time range already uploaded (0–1), or null.
  static final ValueNotifier<double?> progress = ValueNotifier(null);
  static int _inFlight = 0;

  static SyncActivityScope startSync() {
    if (_inFlight == 0) {
      lastResult.value = null;
      progress.value = null;
    }
    _inFlight += 1;
    isSyncing.value = true;
    return SyncActivityScope._();
  }

  static void reportProgress(double value) {
    progress.value = value.clamp(0.0, 1.0);
  }

  static void reportResult(SyncOutcome outcome) {
    lastResult.value = outcome;
  }

  static void _finish() {
    _inFlight = _inFlight > 0 ? _inFlight - 1 : 0;
    if (_inFlight == 0) {
      progress.value = null;
      isSyncing.value = false;
    }
  }
}

/// Disposable handle to ensure sync activity is decremented even on errors.
class SyncActivityScope {
  bool _closed = false;
  SyncActivityScope._();

  void close() {
    if (_closed) return;
    _closed = true;
    SyncActivityNotifier._finish();
  }
}
