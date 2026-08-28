"""In-process request rate limiting.

A fixed-window counter per identity. This is deliberately the simplest thing that
protects the login route from credential stuffing and stops one client from
saturating the API.

Its limitation is real and worth stating: the counter lives in the process, so N API
replicas allow N times the configured rate. A shared counter would need Redis, which
this project has not approved. For a single-container deployment the limit is exact;
for a horizontally scaled one it is a per-replica cap, and an edge proxy should own
the global limit.
"""

from collections import deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic

# Above this many distinct keys, expired entries are swept before the next check so
# the map cannot grow without bound over a long-running process.
MAX_TRACKED_KEYS = 10_000


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimiter:
    """Allows ``limit`` hits per ``window_seconds`` for each key."""

    def __init__(self, limit: int, window_seconds: float = 60.0):
        if limit <= 0:
            raise ValueError("limit must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str, now: float | None = None) -> RateLimitDecision:
        """Record a hit for ``key`` and report whether it is allowed."""
        current = monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            if len(self._hits) > MAX_TRACKED_KEYS:
                self._prune(cutoff)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = max(1, int(hits[0] + self.window_seconds - current) + 1)
                return RateLimitDecision(False, 0, retry_after)
            hits.append(current)
            return RateLimitDecision(True, self.limit - len(hits), 0)

    def _prune(self, cutoff: float) -> None:
        """Drop keys whose whole window has expired.

        Without this the map would keep one entry per client address seen since
        start-up. Called under the lock.
        """
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            self._hits.pop(key, None)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
