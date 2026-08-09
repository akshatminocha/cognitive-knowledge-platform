"""
Rate Limiter — Sliding window counters for TPM/RPM and daily accumulators for TPD/RPD.

All counters are in-memory. For multi-process deployments, swap with Redis-backed
counters (same interface).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RateLimitExceeded(Exception):
    """Raised when a rate limit is exceeded."""

    limit_type: str  # "tpm", "rpm", "tpd", "rpd"
    current_value: int
    max_value: int
    retry_after_seconds: Optional[float] = None

    def __str__(self) -> str:
        msg = f"Rate limit exceeded: {self.limit_type} = {self.current_value}/{self.max_value}"
        if self.retry_after_seconds is not None:
            msg += f" (retry after {self.retry_after_seconds:.1f}s)"
        return msg


@dataclass
class _SlidingWindowCounter:
    """
    Sliding window counter for per-minute rate limiting.

    Maintains a deque of (timestamp, value) pairs. On each check, evicts
    entries older than the window and sums the remaining values.
    """

    window_seconds: float = 60.0
    max_value: int = 100_000
    _entries: deque = field(default_factory=deque)

    def _evict_expired(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._entries and self._entries[0][0] < cutoff:
            self._entries.popleft()

    def current_total(self) -> int:
        self._evict_expired(time.monotonic())
        return sum(v for _, v in self._entries)

    def check_and_record(self, value: int = 1) -> None:
        """Check if adding `value` would exceed the limit. If not, record it."""
        now = time.monotonic()
        self._evict_expired(now)
        current = sum(v for _, v in self._entries)
        if current + value > self.max_value:
            # Calculate when enough capacity frees up
            retry_after = None
            if self._entries:
                oldest_ts = self._entries[0][0]
                retry_after = (oldest_ts + self.window_seconds) - now
            raise RateLimitExceeded(
                limit_type="per_minute",
                current_value=current,
                max_value=self.max_value,
                retry_after_seconds=retry_after,
            )
        self._entries.append((now, value))

    def reset(self) -> None:
        self._entries.clear()


@dataclass
class _DailyAccumulator:
    """
    Daily accumulator for per-day rate limiting.

    Resets at the start of each UTC day (or after `reset_interval_seconds`).
    """

    max_value: int = 1_000_000
    reset_interval_seconds: float = 86400.0  # 24 hours
    _total: int = 0
    _reset_at: float = field(default_factory=lambda: time.monotonic() + 86400.0)

    def _maybe_reset(self, now: float) -> None:
        if now >= self._reset_at:
            self._total = 0
            self._reset_at = now + self.reset_interval_seconds

    def current_total(self) -> int:
        self._maybe_reset(time.monotonic())
        return self._total

    def check_and_record(self, value: int = 1) -> None:
        now = time.monotonic()
        self._maybe_reset(now)
        if self._total + value > self.max_value:
            retry_after = self._reset_at - now
            raise RateLimitExceeded(
                limit_type="per_day",
                current_value=self._total,
                max_value=self.max_value,
                retry_after_seconds=retry_after,
            )
        self._total += value

    def reset(self) -> None:
        self._total = 0
        self._reset_at = time.monotonic() + self.reset_interval_seconds


class RateLimiter:
    """
    Composite rate limiter enforcing TPM, RPM, TPD, and RPD limits.

    Usage:
        limiter = RateLimiter(tpm=100000, rpm=60, tpd=1000000, rpd=5000)

        # Before sending a request:
        limiter.check_request()  # Raises RateLimitExceeded if RPM/RPD exceeded

        # After receiving a response (with token counts):
        limiter.record_tokens(prompt_tokens=500, completion_tokens=200)
    """

    def __init__(
        self,
        tpm: int = 100_000,
        rpm: int = 60,
        tpd: int = 1_000_000,
        rpd: int = 5_000,
    ) -> None:
        self._tpm = _SlidingWindowCounter(window_seconds=60.0, max_value=tpm)
        self._rpm = _SlidingWindowCounter(window_seconds=60.0, max_value=rpm)
        self._tpd = _DailyAccumulator(max_value=tpd)
        self._rpd = _DailyAccumulator(max_value=rpd)

    def check_request(self) -> None:
        """
        Check if a new request is allowed under RPM and RPD limits.
        Call this BEFORE sending the LLM request.
        Raises RateLimitExceeded if any limit is breached.
        """
        try:
            self._rpm.check_and_record(1)
        except RateLimitExceeded as e:
            e.limit_type = "rpm"
            raise

        try:
            self._rpd.check_and_record(1)
        except RateLimitExceeded as e:
            e.limit_type = "rpd"
            raise

    def record_tokens(self, prompt_tokens: int, completion_tokens: int) -> None:
        """
        Record token consumption after a successful LLM response.
        Call this AFTER receiving the response.
        Raises RateLimitExceeded if token limits are breached.
        """
        total_tokens = prompt_tokens + completion_tokens

        try:
            self._tpm.check_and_record(total_tokens)
        except RateLimitExceeded as e:
            e.limit_type = "tpm"
            raise

        try:
            self._tpd.check_and_record(total_tokens)
        except RateLimitExceeded as e:
            e.limit_type = "tpd"
            raise

    def get_usage(self) -> dict:
        """Return current usage across all dimensions."""
        return {
            "tpm": {"current": self._tpm.current_total(), "max": self._tpm.max_value},
            "rpm": {"current": self._rpm.current_total(), "max": self._rpm.max_value},
            "tpd": {"current": self._tpd.current_total(), "max": self._tpd.max_value},
            "rpd": {"current": self._rpd.current_total(), "max": self._rpd.max_value},
        }

    def reset_all(self) -> None:
        """Reset all counters."""
        self._tpm.reset()
        self._rpm.reset()
        self._tpd.reset()
        self._rpd.reset()
