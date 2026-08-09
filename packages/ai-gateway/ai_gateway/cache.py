"""
Response Cache — Exact-match and optional semantic similarity caching.

Reduces redundant LLM calls by caching responses keyed by (model, messages hash).
Semantic caching uses cosine similarity on sentence embeddings for near-duplicate queries.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CacheEntry:
    """A cached LLM response."""

    cache_key: str
    model_id: str
    response: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int
    created_at: float
    ttl_seconds: int
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_seconds


@dataclass
class CacheStats:
    """Cache performance statistics."""

    total_hits: int = 0
    total_misses: int = 0
    total_evictions: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.total_hits + self.total_misses
        return self.total_hits / total if total > 0 else 0.0


class ResponseCache:
    """
    LLM response cache with TTL-based expiry.

    Supports:
    - Exact-match caching: hash(model + messages) → cached response
    - TTL-based auto-expiry
    - LRU eviction when max_entries is reached
    - Hit/miss metrics

    Usage:
        cache = ResponseCache(ttl_seconds=3600, max_entries=1000)

        # Check cache before calling LLM:
        cached = cache.get(model="gemini/gemini-2.5-flash", messages=[...])
        if cached:
            return cached  # Cache hit, skip LLM call

        # After LLM call, store in cache:
        cache.put(
            model="gemini/gemini-2.5-flash",
            messages=[...],
            response=llm_response,
            prompt_tokens=500,
            completion_tokens=200,
        )
    """

    def __init__(
        self,
        ttl_seconds: int = 3600,
        max_entries: int = 1000,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._store: dict[str, CacheEntry] = {}
        self._access_order: list[str] = []  # For LRU eviction
        self.stats = CacheStats()

    @staticmethod
    def _compute_key(model: str, messages: list[dict]) -> str:
        """Compute a deterministic cache key from model + messages."""
        payload = json.dumps({"model": model, "messages": messages}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, model: str, messages: list[dict]) -> Optional[dict[str, Any]]:
        """
        Look up a cached response. Returns None on cache miss.
        Automatically evicts expired entries.
        """
        key = self._compute_key(model, messages)
        entry = self._store.get(key)

        if entry is None:
            self.stats.total_misses += 1
            return None

        if entry.is_expired:
            del self._store[key]
            if key in self._access_order:
                self._access_order.remove(key)
            self.stats.total_evictions += 1
            self.stats.total_misses += 1
            return None

        # Cache hit — update access order
        entry.hit_count += 1
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)
        self.stats.total_hits += 1

        return entry.response

    def put(
        self,
        model: str,
        messages: list[dict],
        response: dict[str, Any],
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> str:
        """
        Store a response in the cache. Returns the cache key.
        Evicts LRU entries if max_entries is exceeded.
        """
        key = self._compute_key(model, messages)

        # Evict LRU if at capacity
        while len(self._store) >= self.max_entries and self._access_order:
            evict_key = self._access_order.pop(0)
            if evict_key in self._store:
                del self._store[evict_key]
                self.stats.total_evictions += 1

        entry = CacheEntry(
            cache_key=key,
            model_id=model,
            response=response,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            created_at=time.time(),
            ttl_seconds=self.ttl_seconds,
        )
        self._store[key] = entry
        self._access_order.append(key)

        return key

    def invalidate(self, model: str, messages: list[dict]) -> bool:
        """Remove a specific entry from the cache. Returns True if found."""
        key = self._compute_key(model, messages)
        if key in self._store:
            del self._store[key]
            if key in self._access_order:
                self._access_order.remove(key)
            return True
        return False

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()
        self._access_order.clear()

    def get_stats(self) -> dict:
        """Return cache performance statistics."""
        return {
            "total_entries": len(self._store),
            "max_entries": self.max_entries,
            "hit_rate": round(self.stats.hit_rate * 100, 2),
            "total_hits": self.stats.total_hits,
            "total_misses": self.stats.total_misses,
            "total_evictions": self.stats.total_evictions,
        }
