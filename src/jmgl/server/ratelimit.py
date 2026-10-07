"""Rate limiting: in-memory sliding window (per process) or Redis fixed window (shared).

With several replicas, set JMGL_RATE_LIMIT_REDIS_URL so limits are global, or enforce
limits at the edge (Cloud Armor / API gateway / ingress). See docs/DEPLOYMENT.md.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Protocol


class Limiter(Protocol):
    def hit(self, bucket: str, limit: int, cost: int = 1) -> int | None:
        """Record `cost` hits; return None if allowed, else seconds until retry."""

    def reset(self) -> None: ...


class MemoryLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, bucket: str, limit: int, cost: int = 1) -> int | None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[bucket]
            while q and now - q[0] >= 60:
                q.popleft()
            if len(q) + cost > limit:
                oldest = q[0] if q else now
                return max(1, int(60 - (now - oldest)) + 1)
            q.extend([now] * cost)
            if len(self._hits) > 100_000:  # bound memory under key/IP churn
                for k in [k for k, v in self._hits.items() if not v][:50_000]:
                    del self._hits[k]
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RedisLimiter:
    """Fixed one-minute windows in Redis (INCRBY + EXPIRE), shared by all replicas."""

    def __init__(self, url: str = "", client=None) -> None:
        if client is None:
            import redis  # optional dependency: pip install "jmgl[redis]"
            client = redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
        self._r = client

    def hit(self, bucket: str, limit: int, cost: int = 1) -> int | None:
        now = time.time()
        window = int(now // 60)
        key = f"jmgl:rl:{bucket}:{window}"
        try:
            pipe = self._r.pipeline()
            pipe.incrby(key, cost)
            pipe.expire(key, 120)
            count = int(pipe.execute()[0])
        except Exception:  # fail open on limiter outage; edge limits still apply
            return None
        if count > limit:
            return max(1, int(60 - (now % 60)) + 1)
        return None

    def reset(self) -> None:
        for k in self._r.scan_iter("jmgl:rl:*"):
            self._r.delete(k)


def make_limiter(redis_url: str) -> Limiter:
    return RedisLimiter(redis_url) if redis_url else MemoryLimiter()
