import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import get_settings

logger = logging.getLogger(__name__)


class ConnectionStore:
    """Manages pending OAuth 2.0 PKCE states and linked patient <-> provider accounts"""

    def __init__(self, storage_path: Optional[str] = None):
        self._settings = get_settings()
        self._storage_path = storage_path or self._settings.storage_path
        self._lock = threading.RLock()
        self._pending_states: Dict[str, Dict[str, Any]] = {}
        self._connections: Dict[str, Dict[str, Any]] = {}
        self._sync_windows: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _key(self, provider: str, patient_id: str) -> str:
        return f"{provider.lower()}:{patient_id}"

    def _load(self) -> None:
        with self._lock:
            if not self._storage_path or not os.path.exists(self._storage_path):
                return
            try:
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._connections = data.get("connections", {})
                self._pending_states = data.get("pending_states", {})
                self._sync_windows = data.get("sync_windows", {})
            except Exception as e:
                logger.warning("Could not load connections store from %s: %s", self._storage_path, e)

    def _persist(self) -> None:
        with self._lock:
            if not self._storage_path:
                return
            try:
                parent = os.path.dirname(self._storage_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                tmp_path = f"{self._storage_path}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "connections": self._connections,
                            "pending_states": self._pending_states,
                            "sync_windows": self._sync_windows,
                        },
                        f,
                        indent=2,
                    )
                os.replace(tmp_path, self._storage_path)
            except Exception as e:
                logger.debug("Using in-memory store (could not write %s: %s)", self._storage_path, e)

    def save_pending_state(
        self,
        state: str,
        provider: str,
        patient_id: str,
        code_verifier: str,
        redirect_uri: str,
        return_url: Optional[str] = None,
        allow_pre_auth: bool = False,
    ) -> None:
        with self._lock:
            self._pending_states[state] = {
                "provider": provider.lower(),
                "patient_id": patient_id,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "return_url": return_url,
                "allow_pre_auth": bool(allow_pre_auth),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._persist()

    def pop_pending_state(self, state: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._pending_states.pop(state, None)
            if entry is not None:
                self._persist()
            return entry

    def save_connection(
        self,
        provider: str,
        patient_id: str,
        provider_user_id: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: Optional[int] = None,
        refresh_token_expires_in: Optional[int] = None,
        scope: Optional[str] = None,
        permissions: Optional[List[str]] = None,
        allow_pre_auth_history: Optional[bool] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        now_ts = int(now.timestamp())
        effective_expires_in = max(0, int(expires_in) - 600) if expires_in else 85800 # Safety buffer
        expires_at = now_ts + effective_expires_in
        refresh_expires_at = (
            now_ts + int(refresh_token_expires_in) - 600 if refresh_token_expires_in else None
        )

        with self._lock:
            key = self._key(provider, patient_id)
            existing = self._connections.get(key, {})
            resolved_pre_auth = (
                bool(allow_pre_auth_history)
                if allow_pre_auth_history is not None
                else bool(existing.get("allow_pre_auth_history", False))
            )
            record = {
                "provider": provider.lower(),
                "patient_id": patient_id,
                "provider_user_id": provider_user_id,
                "access_token": access_token,
                "refresh_token": refresh_token or existing.get("refresh_token"),
                "expires_at": expires_at,
                "refresh_expires_at": refresh_expires_at,
                "scope": scope or existing.get("scope", ""),
                "permissions": permissions if permissions is not None else existing.get("permissions", []),
                "allow_pre_auth_history": resolved_pre_auth,
                "linked_at": existing.get("linked_at", now.isoformat()),
                "updated_at": now.isoformat(),
            }
            self._connections[key] = record
            self._persist()
            return record

    def get_connection(self, provider: str, patient_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._connections.get(self._key(provider, patient_id))

    def get_connection_by_provider_user_id(
        self, provider: str, provider_user_id: str
    ) -> Optional[Dict[str, Any]]:
        provider_lower = provider.lower()
        with self._lock:
            for conn in self._connections.values():
                if (
                    conn.get("provider") == provider_lower
                    and conn.get("provider_user_id") == provider_user_id
                ):
                    return conn
        return None

    def resolve_patient_id(self, provider: str, provider_user_id: str) -> Optional[str]:
        conn = self.get_connection_by_provider_user_id(provider, provider_user_id)
        return conn.get("patient_id") if conn else None

    def update_permissions(
        self, provider: str, provider_user_id: str, permissions: List[str]
    ) -> bool:
        with self._lock:
            conn = self.get_connection_by_provider_user_id(provider, provider_user_id)
            if not conn:
                return False
            conn["permissions"] = permissions
            conn["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._persist()
            return True

    def set_pre_auth_history(
        self, provider: str, patient_id: str, allow: bool
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._connections.get(self._key(provider, patient_id))
            if not conn:
                return None
            conn["allow_pre_auth_history"] = bool(allow)
            conn["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._persist()
            return conn

    def delete_connection(self, provider: str, patient_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            removed = self._connections.pop(self._key(provider, patient_id), None)
            prefix = f"{provider.lower()}:{patient_id}:"
            stale_keys = [k for k in self._sync_windows if k.startswith(prefix)]
            for k in stale_keys:
                self._sync_windows.pop(k, None)
            if removed is not None or stale_keys:
                self._persist()
            return removed

    def should_skip_sync_window(
        self,
        key: str,
        *,
        max_attempts: int = 3,
        now: Optional[datetime] = None,
    ) -> tuple[bool, Optional[str]]:
        """Prevents infinite retry loops for triggered or exhausted windows"""
        with self._lock:
            entry = self._sync_windows.get(key)
            if not entry:
                return False, None
            status = entry.get("status")
            if status in ("triggered", "already_requested"):
                return True, f"already_{status}"
            if status == "failed_permanent":
                return True, "failed_permanent"
            attempts = int(entry.get("attempts", 0))
            if attempts >= max_attempts:
                return True, "max_attempts_reached"
            next_retry_raw = entry.get("next_retry_at")
            if next_retry_raw:
                try:
                    next_retry = datetime.fromisoformat(next_retry_raw)
                    current = now or datetime.now(timezone.utc)
                    if current < next_retry:
                        return True, "cooldown_active"
                except ValueError:
                    pass
            return False, None

    def record_sync_window(
        self,
        key: str,
        *,
        status: str,
        status_code: Optional[int] = None,
        error: Optional[str] = None,
        max_attempts: int = 3,
        next_retry_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            existing = self._sync_windows.get(key, {})
            attempts = int(existing.get("attempts", 0)) + 1
            effective_status = (
                "failed_permanent"
                if status == "failed_retryable" and attempts >= max_attempts
                else status
            )
            record = {
                "status": effective_status,
                "attempts": attempts,
                "last_status_code": status_code,
                "last_error": error,
                "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
                "updated_at": now_iso,
            }
            self._sync_windows[key] = record
            self._persist()
            return record

    def delete_connection_by_provider_user_id(
        self, provider: str, provider_user_id: str
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self.get_connection_by_provider_user_id(provider, provider_user_id)
            if not conn:
                return None
            return self.delete_connection(provider, conn["patient_id"])

    def list_connections(
        self, provider: Optional[str] = None, patient_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        provider_lower = provider.lower() if provider else None
        results = []
        with self._lock:
            for conn in self._connections.values():
                if provider_lower and conn.get("provider") != provider_lower:
                    continue
                if patient_id is not None and conn.get("patient_id") != patient_id:
                    continue
                results.append(
                    {
                        "provider": conn["provider"],
                        "patient_id": conn["patient_id"],
                        "provider_user_id": conn.get("provider_user_id"),
                        "permissions": conn.get("permissions", []),
                        "scope": conn.get("scope", ""),
                        "allow_pre_auth_history": bool(conn.get("allow_pre_auth_history", False)),
                        "expires_at": conn.get("expires_at"),
                        "linked_at": conn.get("linked_at"),
                        "updated_at": conn.get("updated_at"),
                    }
                )
        return results


_store_instance: Optional[ConnectionStore] = None


def get_store() -> ConnectionStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = ConnectionStore()
    return _store_instance
