import 'package:flutter/foundation.dart';

/// Tracks whether any health-data sync is currently running (manual or automatic).
/// Uses a simple reference count so overlapping syncs keep the indicator active
/// until every caller finishes.
class SyncActivityNotifier {
  SyncActivityNotifier._();

  static final ValueNotifier<bool> isSyncing = ValueNotifier<bool>(false);
  static int _inFlight = 0;

  static SyncActivityScope startSync() {
    _inFlight += 1;
    isSyncing.value = true;
    return SyncActivityScope._();
  }

  static void _finish() {
    _inFlight = _inFlight > 0 ? _inFlight - 1 : 0;
    if (_inFlight == 0) {
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
