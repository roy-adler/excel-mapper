from datetime import datetime, timedelta
from threading import Lock


class LockManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._ttl_seconds = 30
        self._locks: dict[str, tuple[str, datetime]] = {}

    def _cleanup(self) -> None:
        now = datetime.utcnow()
        expired = [k for k, (_, expiry) in self._locks.items() if expiry <= now]
        for key in expired:
            self._locks.pop(key, None)

    def acquire(self, session_key: str, field_key: str, owner: str) -> bool:
        scoped_key = f"{session_key}:{field_key}"
        with self._lock:
            self._cleanup()
            existing = self._locks.get(scoped_key)
            if existing and existing[0] != owner:
                return False
            self._locks[scoped_key] = (owner, datetime.utcnow() + timedelta(seconds=self._ttl_seconds))
            return True

    def release(self, session_key: str, field_key: str, owner: str) -> None:
        scoped_key = f"{session_key}:{field_key}"
        with self._lock:
            existing = self._locks.get(scoped_key)
            if existing and existing[0] == owner:
                self._locks.pop(scoped_key, None)

    def heartbeat(self, session_key: str, field_key: str, owner: str) -> bool:
        scoped_key = f"{session_key}:{field_key}"
        with self._lock:
            existing = self._locks.get(scoped_key)
            if not existing or existing[0] != owner:
                return False
            self._locks[scoped_key] = (owner, datetime.utcnow() + timedelta(seconds=self._ttl_seconds))
            return True


lock_manager = LockManager()
