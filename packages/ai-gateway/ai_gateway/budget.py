"""
Budget Manager — Token consumption tracking and cost enforcement.

Tracks cumulative token usage, calculates costs using configurable
price-per-token tables, and enforces hard budget caps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class BudgetExhausted(Exception):
    """Raised when the cost budget is exhausted."""

    current_spend: float
    max_budget: float
    period_days: int

    def __str__(self) -> str:
        return (
            f"Budget exhausted: ${self.current_spend:.4f} / ${self.max_budget:.2f} "
            f"(period: {self.period_days} days)"
        )


@dataclass
class UsageRecord:
    """A single LLM usage record."""

    timestamp: float
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class BudgetManager:
    """
    Tracks token consumption and cost, enforcing hard budget caps.

    Usage:
        budget = BudgetManager(max_budget_usd=10.0, budget_period_days=30)

        # After each LLM call:
        budget.record_usage(
            model_id="gemini/gemini-2.5-flash",
            prompt_tokens=500,
            completion_tokens=200,
            cost_per_input_token=0.0,
            cost_per_output_token=0.0,
        )

        # Check remaining budget:
        budget.remaining_budget_usd()

        # Register a warning callback:
        budget.on_warning(lambda spend, max_b: print(f"Warning: ${spend:.2f}/{max_b:.2f}"))
    """

    def __init__(
        self,
        max_budget_usd: float = 10.0,
        budget_period_days: int = 30,
        warn_at_percent: float = 80.0,
    ) -> None:
        self.max_budget_usd = max_budget_usd
        self.budget_period_days = budget_period_days
        self.warn_at_percent = warn_at_percent

        self._records: list[UsageRecord] = []
        self._total_spend: float = 0.0
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._period_start: float = time.time()
        self._warning_callbacks: list[Callable[[float, float], None]] = []
        self._warning_fired: bool = False

    def _maybe_reset_period(self) -> None:
        """Reset counters if the budget period has elapsed."""
        elapsed = time.time() - self._period_start
        if elapsed >= self.budget_period_days * 86400:
            self._records.clear()
            self._total_spend = 0.0
            self._total_prompt_tokens = 0
            self._total_completion_tokens = 0
            self._period_start = time.time()
            self._warning_fired = False

    def record_usage(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_per_input_token: float = 0.0,
        cost_per_output_token: float = 0.0,
    ) -> UsageRecord:
        """
        Record token usage and cost for a completed LLM call.

        Raises BudgetExhausted if the cumulative spend exceeds max_budget_usd.
        """
        self._maybe_reset_period()

        cost = (prompt_tokens * cost_per_input_token) + (
            completion_tokens * cost_per_output_token
        )

        # Check budget BEFORE recording
        if self._total_spend + cost > self.max_budget_usd:
            raise BudgetExhausted(
                current_spend=self._total_spend + cost,
                max_budget=self.max_budget_usd,
                period_days=self.budget_period_days,
            )

        record = UsageRecord(
            timestamp=time.time(),
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
        )
        self._records.append(record)
        self._total_spend += cost
        self._total_prompt_tokens += prompt_tokens
        self._total_completion_tokens += completion_tokens

        # Fire warning if threshold crossed
        if not self._warning_fired:
            threshold = self.max_budget_usd * (self.warn_at_percent / 100.0)
            if self._total_spend >= threshold:
                self._warning_fired = True
                for cb in self._warning_callbacks:
                    cb(self._total_spend, self.max_budget_usd)

        return record

    def check_budget(self) -> None:
        """Pre-flight check: raise BudgetExhausted if budget is already exceeded."""
        self._maybe_reset_period()
        if self._total_spend >= self.max_budget_usd:
            raise BudgetExhausted(
                current_spend=self._total_spend,
                max_budget=self.max_budget_usd,
                period_days=self.budget_period_days,
            )

    def remaining_budget_usd(self) -> float:
        """Return remaining budget in USD."""
        self._maybe_reset_period()
        return max(0.0, self.max_budget_usd - self._total_spend)

    def get_summary(self) -> dict:
        """Return a summary of usage and budget status."""
        self._maybe_reset_period()
        return {
            "total_spend_usd": round(self._total_spend, 6),
            "max_budget_usd": self.max_budget_usd,
            "remaining_usd": round(self.remaining_budget_usd(), 6),
            "percent_used": round(
                (self._total_spend / self.max_budget_usd * 100) if self.max_budget_usd > 0 else 0,
                2,
            ),
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
            "total_requests": len(self._records),
            "budget_period_days": self.budget_period_days,
        }

    def on_warning(self, callback: Callable[[float, float], None]) -> None:
        """Register a callback that fires when spend crosses the warning threshold."""
        self._warning_callbacks.append(callback)

    def get_records(self, last_n: Optional[int] = None) -> list[UsageRecord]:
        """Return usage records, optionally limited to the last N."""
        if last_n is not None:
            return self._records[-last_n:]
        return list(self._records)
