"""Polite, block-resistant request pacing: a rate limiter + a circuit breaker.

Today's block came from a thundering herd — thousands of detail fetches at
concurrency 10, three scrapers in parallel, retry storms. These two primitives
stop that:

  RateLimiter   — thread-safe minimum spacing between requests, with jitter, so a
                  concurrent detail pass trickles instead of bursts.
  CircuitBreaker — after N consecutive throttle signals (HTTP 403/429 or a run of
                  empty detail responses), trip and fail fast (ThrottledError)
                  rather than hammering a clearly-throttling endpoint. Partial
                  progress is already cached, so the run resumes cleanly later.
"""
from __future__ import annotations

import random
import threading
import time


class ThrottledError(Exception):
    """Raised when the circuit breaker trips — back off and resume later."""


class RateLimiter:
    """Ensure >= 1/rps seconds between acquisitions (plus jitter). Thread-safe.

    rps<=0 disables limiting. ``sleep`` is injectable for tests."""

    def __init__(self, rps: float = 3.0, jitter: float = 0.3, sleep=time.sleep,
                 clock=time.monotonic):
        self.min_interval = (1.0 / rps) if rps and rps > 0 else 0.0
        self.jitter = max(0.0, jitter)
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._next = 0.0

    def acquire(self) -> None:
        if self.min_interval <= 0 and self.jitter <= 0:
            return
        with self._lock:
            now = self._clock()
            wait = max(0.0, self._next - now)
            extra = random.uniform(0, self.jitter) if self.jitter else 0.0
            self._next = max(now, self._next) + self.min_interval + extra
        if wait > 0:
            self._sleep(wait)


class CircuitBreaker:
    """Trip after ``threshold`` consecutive throttle signals. Any success resets."""

    def __init__(self, threshold: int = 8):
        self.threshold = threshold
        self._consec = 0
        self._lock = threading.Lock()
        self.tripped = False

    def record_success(self) -> None:
        with self._lock:
            self._consec = 0

    def record_throttle(self) -> bool:
        """Note a throttle signal; return True if the breaker is now tripped."""
        with self._lock:
            self._consec += 1
            if self._consec >= self.threshold:
                self.tripped = True
            return self.tripped

    def check(self) -> None:
        """Raise ThrottledError if already tripped (call before each request)."""
        if self.tripped:
            raise ThrottledError(
                f"circuit breaker tripped after {self.threshold} consecutive throttle "
                f"signals — backing off; partial progress is cached, resume later")


def backoff_delay(attempt: int, base: float = 1.0, cap: float = 30.0,
                  jitter: float = 0.5) -> float:
    """Exponential backoff with jitter: base*2^attempt, capped, + random jitter."""
    return min(cap, base * (2 ** attempt)) + random.uniform(0, jitter)
