"""Thread-safe synchronization primitives for multi-device orchestration."""

from __future__ import annotations

import threading


class VariableStore:
    """Thread-safe key-value store for captured cross-device values (room codes, invite links)."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._lock = threading.Lock()

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = value

    def get(self, key: str, default: str = "") -> str:
        with self._lock:
            return self._data.get(key, default)

    def snapshot(self) -> dict[str, str]:
        """Return a copy of the current variable state for safe use in format_map()."""
        with self._lock:
            return dict(self._data)


class AbortEvent:
    """Fail-fast signal across threads. abort() is idempotent; first reason wins."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason: str = ""
        self._lock = threading.Lock()

    def abort(self, reason: str = "") -> None:
        with self._lock:
            if not self._event.is_set():
                self._reason = reason
                self._event.set()

    def is_aborted(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason
