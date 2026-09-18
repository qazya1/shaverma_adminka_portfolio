"""Minimal in-process rate limiter for brute-force protection on auth
endpoints.

This is intentionally simple: a fixed-window counter per key, kept in
memory and guarded by a lock. It is enough to blunt naive brute-force /
credential-stuffing attempts against a two-admin system running as a
single process.

It is NOT a substitute for a shared (e.g. Redis-backed) limiter in a
multi-process/multi-instance deployment -- if the admin panel is ever
scaled horizontally, replace this with a shared store. Documented as a
known limitation in the README.
"""

import threading
import time
from dataclasses import dataclass, field


@dataclass
class _Window:
    count: int = 0
    window_started_at: float = field(default_factory=time.monotonic)


class InMemoryRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._buckets: dict[str, _Window] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """Register an attempt for `key`. Return True if it is allowed,
        False if the key has exceeded the limit for the current window.
        """

        now = time.monotonic()
        with self._lock:
            window = self._buckets.get(key)
            if window is None or (now - window.window_started_at) > self._window_seconds:
                window = _Window(count=0, window_started_at=now)
                self._buckets[key] = window
            window.count += 1
            return window.count <= self._max_attempts

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def reset_all(self) -> None:
        """Clear every bucket. Mainly for tests -- the limiter instances
        used by the API live for the whole process, so without this,
        state from one test bleeds into the rate-limit window of the
        next."""

        with self._lock:
            self._buckets.clear()
