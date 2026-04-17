"""Local file-based lock implementation."""

from __future__ import annotations

import fcntl
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO


class FileLock:
    """A non-blocking file lock stored in the user's home directory."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path.home() / ".platform-cli" / "install.lock"
        self._handle: TextIO | None = None

    def acquire(self, path: Path | None = None, timeout_minutes: int = 30) -> bool:
        """Acquire the file lock if it is not held or has expired."""

        if path is not None:
            self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._is_stale(timeout_minutes):
            self.path.unlink(missing_ok=True)

        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False

        handle.seek(0)
        handle.truncate(0)
        payload = {
            "pid": os.getpid(),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        handle.write(json.dumps(payload))
        handle.flush()
        self._handle = handle
        return True

    def release(self) -> None:
        """Release the current file lock."""

        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None
        self.path.unlink(missing_ok=True)

    def is_locked(self) -> bool:
        """Return whether the lock file is currently held."""

        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
        return False

    def _is_stale(self, timeout_minutes: int) -> bool:
        if not self.path.exists():
            return False
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            return True
        timestamp = payload.get("timestamp")
        if not isinstance(timestamp, str):
            return True
        created = datetime.fromisoformat(timestamp)
        return datetime.now(UTC) - created > timedelta(minutes=timeout_minutes)
