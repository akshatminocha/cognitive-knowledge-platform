"""
Evaluator — Golden dataset benchmark runner.

Runs the agent against a golden Q&A dataset and scores responses
for correctness, groundedness, and latency.

Golden datasets are JSON files with known-good question-answer pairs
that serve as regression tests for agent quality.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class GoldenQA:
    """A single golden Q&A pair for evaluation."""

    question_id: str
    question: str
    expected_answer: str
    category: str = "general"
    difficulty: str = "medium"  # easy, medium, hard
    metadata: dict = field(default_factory=dict)


@dataclass
class EvalResult:
    """Result of evaluating a single golden Q&A pair."""

    question_id: str
    question: str
    expected_answer: str
    actual_answer: str
    is_correct: bool = False
    similarity_score: float = 0.0
    latency_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class BenchmarkReport:
    """Aggregate report from a full benchmark run."""

    total_questions: int = 0
    correct_count: int = 0
    accuracy: float = 0.0
    avg_similarity: float = 0.0
    avg_latency_ms: float = 0.0
    results: list[EvalResult] = field(default_factory=list)
    by_category: dict[str, dict] = field(default_factory=dict)
    by_difficulty: dict[str, dict] = field(default_factory=dict)
    run_timestamp: str = ""
    model_used: str = ""


def _token_overlap_score(expected: str, actual: str) -> float:
    """
    Compute token overlap similarity between expected and actual answers.

    Simple but effective for evaluating factual Q&A correctness.
    """
    if not expected.strip() or not actual.strip():
        return 0.0

    expected_tokens = set(expected.lower().split())
    actual_tokens = set(actual.lower().split())

    # Remove common stopwords
    stopwords = {
        "the", "a", "an", "is", "are", "was", "of", "in", "to", "and",
        "for", "it", "that", "this", "with", "on", "at", "by", "from",
    }
    expected_tokens -= stopwords
    actual_tokens -= stopwords

    if not expected_tokens:
        return 1.0  # Empty expected = always correct

    overlap = expected_tokens & actual_tokens
    # F1-style score
    precision = len(overlap) / len(actual_tokens) if actual_tokens else 0
    recall = len(overlap) / len(expected_tokens) if expected_tokens else 0

    if precision + recall == 0:
        return 0.0

    f1 = 2 * (precision * recall) / (precision + recall)
    return round(f1, 4)


class Evaluator:
    """
    Golden dataset benchmark runner.

    Loads golden Q&A datasets, runs the agent against each question,
    and produces aggregate quality reports.

    Usage:
        evaluator = Evaluator()
        dataset = evaluator.load_dataset("evaluation/datasets/golden_qa.json")

        report = await evaluator.run_benchmark(
            dataset=dataset,
            agent_fn=runner.run,  # The agent's run function
            model_name="gemini-2.5-flash",
        )

        print(f"Accuracy: {report.accuracy:.1%}")
        print(f"Avg latency: {report.avg_latency_ms:.0f}ms")
    """

    def __init__(self, similarity_threshold: float = 0.5) -> None:
        self.similarity_threshold = similarity_threshold

    def load_dataset(self, path: str | Path) -> list[GoldenQA]:
        """Load a golden Q&A dataset from a JSON file."""
        filepath = Path(path)
        if not filepath.exists():
            raise FileNotFoundError(f"Dataset not found: {filepath}")

        with open(filepath) as f:
            data = json.load(f)

        questions = []
        for item in data.get("questions", []):
            questions.append(GoldenQA(
                question_id=item.get("id", ""),
                question=item["question"],
                expected_answer=item["expected_answer"],
                category=item.get("category", "general"),
                difficulty=item.get("difficulty", "medium"),
                metadata=item.get("metadata", {}),
            ))

        logger.info(f"Loaded {len(questions)} golden Q&A pairs from {filepath}")
        return questions

    async def run_benchmark(
        self,
        dataset: list[GoldenQA],
        agent_fn: Callable,
        model_name: str = "",
    ) -> BenchmarkReport:
        """
        Run the full benchmark against a golden dataset.

        Args:
            dataset: List of GoldenQA pairs to evaluate.
            agent_fn: Async function that takes a query string and returns
                       an object with a .final_response attribute.
            model_name: Name of the model being evaluated (for reporting).
        """
        report = BenchmarkReport(
            total_questions=len(dataset),
            model_used=model_name,
            run_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        for qa in dataset:
            result = await self._evaluate_single(qa, agent_fn)
            report.results.append(result)

        # Calculate aggregates
        report.correct_count = sum(1 for r in report.results if r.is_correct)
        report.accuracy = (
            report.correct_count / report.total_questions
            if report.total_questions > 0
            else 0.0
        )
        report.avg_similarity = (
            sum(r.similarity_score for r in report.results) / len(report.results)
            if report.results
            else 0.0
        )
        report.avg_latency_ms = (
            sum(r.latency_ms for r in report.results) / len(report.results)
            if report.results
            else 0.0
        )

        # Group by category
        report.by_category = self._group_results(
            report.results, dataset, key="category"
        )
        report.by_difficulty = self._group_results(
            report.results, dataset, key="difficulty"
        )

        logger.info(
            f"Benchmark complete: {report.accuracy:.1%} accuracy "
            f"({report.correct_count}/{report.total_questions}), "
            f"avg latency: {report.avg_latency_ms:.0f}ms"
        )

        return report

    async def _evaluate_single(
        self, qa: GoldenQA, agent_fn: Callable
    ) -> EvalResult:
        """Evaluate a single golden Q&A pair."""
        start = time.monotonic()

        try:
            run_result = await agent_fn(qa.question)
            actual = run_result.final_response
            latency = (time.monotonic() - start) * 1000

            score = _token_overlap_score(qa.expected_answer, actual)

            return EvalResult(
                question_id=qa.question_id,
                question=qa.question,
                expected_answer=qa.expected_answer,
                actual_answer=actual,
                is_correct=score >= self.similarity_threshold,
                similarity_score=score,
                latency_ms=latency,
            )

        except Exception as e:
            return EvalResult(
                question_id=qa.question_id,
                question=qa.question,
                expected_answer=qa.expected_answer,
                actual_answer="",
                latency_ms=(time.monotonic() - start) * 1000,
                error=str(e),
            )

    def _group_results(
        self,
        results: list[EvalResult],
        dataset: list[GoldenQA],
        key: str,
    ) -> dict[str, dict]:
        """Group results by a category key (category or difficulty)."""
        qa_map = {qa.question_id: qa for qa in dataset}
        groups: dict[str, list[EvalResult]] = {}

        for result in results:
            qa = qa_map.get(result.question_id)
            group_val = getattr(qa, key, "unknown") if qa else "unknown"
            groups.setdefault(group_val, []).append(result)

        return {
            group: {
                "total": len(items),
                "correct": sum(1 for r in items if r.is_correct),
                "accuracy": sum(1 for r in items if r.is_correct) / len(items),
                "avg_similarity": sum(r.similarity_score for r in items) / len(items),
            }
            for group, items in groups.items()
        }

    def export_report(self, report: BenchmarkReport, path: str | Path) -> None:
        """Export a benchmark report to JSON."""
        filepath = Path(path)
        data = {
            "model": report.model_used,
            "timestamp": report.run_timestamp,
            "summary": {
                "total": report.total_questions,
                "correct": report.correct_count,
                "accuracy": report.accuracy,
                "avg_similarity": report.avg_similarity,
                "avg_latency_ms": report.avg_latency_ms,
            },
            "by_category": report.by_category,
            "by_difficulty": report.by_difficulty,
            "results": [
                {
                    "id": r.question_id,
                    "question": r.question,
                    "expected": r.expected_answer,
                    "actual": r.actual_answer,
                    "correct": r.is_correct,
                    "similarity": r.similarity_score,
                    "latency_ms": r.latency_ms,
                    "error": r.error,
                }
                for r in report.results
            ],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Exported benchmark report to {filepath}")
