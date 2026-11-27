import asyncio
import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from .config import get_settings

logger = logging.getLogger(__name__)


class OutboxFullError(RuntimeError):
    """Raised when persisting another webhook batch would exceed outbox disk limits"""


class OutboxQueue:
    """File-backed FIFO outbox"""

    def __init__(self, outbox_dir: Optional[str] = None, max_bytes: Optional[int] = None):
        settings = get_settings()
        self._dir = outbox_dir or settings.resolved_outbox_dir
        self._max_bytes = max_bytes if max_bytes is not None else settings.outbox_max_bytes
        self._lock = threading.RLock()
        self._seq = 0

    @property
    def outbox_dir(self) -> str:
        return self._dir

    def _list_files_unlocked(self) -> List[str]:
        if not os.path.isdir(self._dir):
            return []
        files = [
            f for f in os.listdir(self._dir) if f.endswith(".json") and not f.startswith(".")
        ]
        files.sort()
        return [os.path.join(self._dir, f) for f in files]

    def _total_bytes_unlocked(self, paths: List[str]) -> int:
        total = 0
        for p in paths:
            try:
                total += os.path.getsize(p)
            except OSError:
                pass
        return total

    def has_pending(self) -> bool:
        """Fast check without stat calls"""
        with self._lock:
            if not os.path.isdir(self._dir):
                return False
            for name in os.listdir(self._dir):
                if name.endswith(".json") and not name.startswith("."):
                    return True
            return False

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            paths = self._list_files_unlocked()
            return {
                "outbox_dir": self._dir,
                "pending_count": len(paths),
                "pending_bytes": self._total_bytes_unlocked(paths),
                "max_bytes": self._max_bytes,
            }

    def enqueue(self, payloads: List[Dict[str, Any]]) -> int:
        """Atomically writes payload batches to disk before returning 200 OK to webhook caller"""
        if not payloads:
            return 0
        serialized = [json.dumps(p, default=str).encode("utf-8") for p in payloads]
        incoming_bytes = sum(len(b) for b in serialized)

        with self._lock:
            os.makedirs(self._dir, exist_ok=True)
            existing = self._list_files_unlocked()
            current_bytes = self._total_bytes_unlocked(existing)
            if current_bytes + incoming_bytes > self._max_bytes:
                raise OutboxFullError(
                    f"Outbox capacity exceeded ({current_bytes + incoming_bytes} > {self._max_bytes} bytes)"
                )

            now_ms = int(time.time() * 1000)
            written = 0
            for raw_bytes in serialized:
                self._seq = (self._seq + 1) % 1_000_000
                name = f"{now_ms:013d}_{self._seq:06d}_{uuid.uuid4().hex[:12]}.json"
                final_path = os.path.join(self._dir, name)
                tmp_path = f"{final_path}.tmp"
                try:
                    with open(tmp_path, "wb") as f:
                        f.write(raw_bytes)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp_path, final_path)
                    written += 1
                except Exception:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
                    raise
            return written

    def drain_once(self, publish_fn: Callable[[Dict[str, Any]], bool]) -> tuple[int, int]:
        """Publishes pending outbox files in FIFO order; deletes each file only after Kafka ACK"""
        with self._lock:
            paths = self._list_files_unlocked()

        sent = 0
        total = len(paths)
        for idx, path in enumerate(paths):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception as exc:
                logger.error("Corrupt outbox file %s removed to unblock queue: %s", path, exc)
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue

            try:
                ok = bool(publish_fn(payload))
            except Exception as exc:
                logger.warning("Outbox Kafka publish raised error for %s: %s", path, exc)
                ok = False

            if not ok:
                return sent, total - idx

            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            sent += 1

        return sent, 0


class OutboxWorker:
    """Async background loop draining persisted webhook payloads to Kafka with bounded backoff"""

    def __init__(
        self,
        outbox_provider: Callable[[], OutboxQueue],
        publish_fn_provider: Callable[[], Callable[[Dict[str, Any]], bool]],
    ):
        self._get_outbox = outbox_provider
        self._get_publish_fn = publish_fn_provider
        self._wakeup = asyncio.Event()
        self._stop = False
        self._task: Optional[asyncio.Task] = None

    def notify(self) -> None:
        self._wakeup.set()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop = False
        self._wakeup = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="cloud-connector-outbox-worker")

    async def stop(self) -> None:
        self._stop = True
        self._wakeup.set()
        if self._task is not None:
            try:
                await self._task
            except Exception:
                pass
            self._task = None

    async def _run(self) -> None:
        failures = 0
        while not self._stop:
            settings = get_settings()
            base_interval = settings.outbox_poll_interval
            max_backoff = settings.outbox_max_backoff
            self._wakeup.clear()

            try:
                outbox = self._get_outbox()
                publish_fn = self._get_publish_fn()
                sent, remaining = await asyncio.to_thread(outbox.drain_once, publish_fn)
                if remaining > 0 and sent == 0:
                    failures += 1
                    wait_seconds = min(max_backoff, base_interval * (2 ** min(failures - 1, 5)))
                else:
                    failures = 0
                    wait_seconds = 0.0 if remaining > 0 else base_interval
            except Exception as exc:
                failures += 1
                wait_seconds = min(max_backoff, base_interval * (2 ** min(failures - 1, 5)))
                logger.warning("Outbox worker iteration failed: %s", exc)

            if wait_seconds <= 0:
                continue

            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=wait_seconds)
            except asyncio.TimeoutError:
                pass


_outbox_instance: Optional[OutboxQueue] = None


def get_outbox() -> OutboxQueue:
    global _outbox_instance
    if _outbox_instance is None:
        _outbox_instance = OutboxQueue()
    return _outbox_instance
