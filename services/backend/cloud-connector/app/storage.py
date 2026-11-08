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
    ) -> None:
        with self._lock:
            self._pending_states[state] = {
                "provider": provider.lower(),
                "patient_id": patient_id,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "return_url": return_url,
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

    def delete_connection(self, provider: str, patient_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            removed = self._connections.pop(self._key(provider, patient_id), None)
            if removed is not None:
                self._persist()
            return removed

    def delete_connection_by_provider_user_id(
        self, provider: str, provider_user_id: str
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self.get_connection_by_provider_user_id(provider, provider_user_id)
            if not conn:
                return None
            return self.delete_connection(provider, conn["patient_id"])

    def list_connections(self, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        provider_lower = provider.lower() if provider else None
        results = []
        with self._lock:
            for conn in self._connections.values():
                if provider_lower and conn.get("provider") != provider_lower:
                    continue
                results.append(
                    {
                        "provider": conn["provider"],
                        "patient_id": conn["patient_id"],
                        "provider_user_id": conn.get("provider_user_id"),
                        "permissions": conn.get("permissions", []),
                        "scope": conn.get("scope", ""),
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
