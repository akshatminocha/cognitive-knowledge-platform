"""
CKP Benchmark Runner — CLI for running golden dataset evaluations.

Loads the golden Q&A dataset, runs each question through the agent,
scores the responses, and generates a report.

Usage:
    python -m evaluation.run_benchmarks
    python -m evaluation.run_benchmarks --dataset evaluation/datasets/golden_qa.json
    python -m evaluation.run_benchmarks --model gemini-2.5-flash --output report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

# The Evaluator and GoldenQA types live in the agent-harness package
from agent_harness.evaluator import (
    BenchmarkReport,
    Evaluator,
    GoldenQA,
    _token_overlap_score,
)
from agent_harness.runner import AgentRunner, RunnerConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
DEFAULT_DATASET = Path(__file__).parent / "datasets" / "golden_qa.json"
DEFAULT_OUTPUT = Path(__file__).parent / "reports"


# ---------------------------------------------------------------------------
# Standalone scoring (no agent required)
# ---------------------------------------------------------------------------
def run_offline_evaluation(
    dataset_path: Path,
    mock_answers: Optional[dict[str, str]] = None,
) -> BenchmarkReport:
    """
    Run a quick offline evaluation without the agent.

    Useful for validating the benchmark infrastructure itself,
    or for scoring pre-collected answers.

    Args:
        dataset_path: Path to golden_qa.json
        mock_answers: Optional dict of question_id → answer. If not provided,
                      uses a trivial echo to verify the pipeline runs end-to-end.
    """
    evaluator = Evaluator()
    dataset = evaluator.load_dataset(dataset_path)

    report = BenchmarkReport(
        total_questions=len(dataset),
        model_used="offline-eval",
        run_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    for qa in dataset:
        actual = ""
        if mock_answers and qa.question_id in mock_answers:
            actual = mock_answers[qa.question_id]

        score = _token_overlap_score(qa.expected_answer, actual)

        from agent_harness.evaluator import EvalResult

        report.results.append(
            EvalResult(
                question_id=qa.question_id,
                question=qa.question,
                expected_answer=qa.expected_answer,
                actual_answer=actual,
                is_correct=score >= evaluator.similarity_threshold,
                similarity_score=score,
                latency_ms=0.0,
            )
        )

    # Aggregate
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

    return report


# ---------------------------------------------------------------------------
# Full agent evaluation
# ---------------------------------------------------------------------------
async def run_agent_evaluation(
    dataset_path: Path,
    model: str = "gemini-2.5-flash",
    schema: str = "healthtech",
) -> BenchmarkReport:
    """
    Run the full agent evaluation pipeline.

    Creates an AgentRunner, feeds each golden question through it,
    and scores the responses.
    """
    config = RunnerConfig(
        active_model=model,
        active_schema=schema,
        enable_reflection=True,
        enable_memory=False,  # Disable memory for clean benchmark runs
    )
    runner = AgentRunner(config=config)

    evaluator = Evaluator()
    dataset = evaluator.load_dataset(dataset_path)

    report = await evaluator.run_benchmark(
        dataset=dataset,
        agent_fn=runner.run,
        model_name=model,
    )

    return report


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------
def print_report(report: BenchmarkReport) -> None:
    """Pretty-print a benchmark report to stdout."""
    print("\n" + "=" * 60)
    print("  CKP BENCHMARK REPORT")
    print("=" * 60)
    print(f"  Model:      {report.model_used}")
    print(f"  Timestamp:  {report.run_timestamp}")
    print(f"  Questions:  {report.total_questions}")
    print(f"  Correct:    {report.correct_count}")
    print(f"  Accuracy:   {report.accuracy:.1%}")
    print(f"  Avg Score:  {report.avg_similarity:.3f}")
    print(f"  Avg Latency:{report.avg_latency_ms:.0f}ms")
    print("-" * 60)

    # Results by category
    if report.by_category:
        print("\n  BY CATEGORY:")
        for cat, stats in report.by_category.items():
            print(
                f"    {cat:20s}  "
                f"{stats['correct']}/{stats['total']} "
                f"({stats['accuracy']:.0%})  "
                f"avg_score={stats['avg_similarity']:.3f}"
            )

    # Results by difficulty
    if report.by_difficulty:
        print("\n  BY DIFFICULTY:")
        for diff, stats in report.by_difficulty.items():
            print(
                f"    {diff:20s}  "
                f"{stats['correct']}/{stats['total']} "
                f"({stats['accuracy']:.0%})  "
                f"avg_score={stats['avg_similarity']:.3f}"
            )

    # Individual results
    print("\n  INDIVIDUAL RESULTS:")
    for r in report.results:
        status = "✅" if r.is_correct else "❌"
        print(f"    {status} [{r.question_id}] score={r.similarity_score:.3f}")
        if r.error:
            print(f"       ERROR: {r.error}")

    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="CKP Benchmark Runner — evaluate agent quality against golden datasets"
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to golden_qa.json dataset",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to save JSON report (default: evaluation/reports/)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.5-flash",
        help="Model name to evaluate",
    )
    parser.add_argument(
        "--schema",
        type=str,
        default="healthtech",
        help="Domain schema to use",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run offline evaluation (no agent, validates pipeline only)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(levelname)-7s | %(message)s",
    )

    if not args.dataset.exists():
        print(f"Error: Dataset not found: {args.dataset}", file=sys.stderr)
        sys.exit(1)

    # Run evaluation
    if args.offline:
        logger.info("Running offline evaluation (pipeline validation only)")
        report = run_offline_evaluation(args.dataset)
    else:
        logger.info(f"Running agent evaluation with model={args.model}")
        report = asyncio.run(
            run_agent_evaluation(args.dataset, model=args.model, schema=args.schema)
        )

    # Print report
    print_report(report)

    # Save report
    output_path = args.output
    if output_path is None:
        DEFAULT_OUTPUT.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = DEFAULT_OUTPUT / f"benchmark_{report.model_used}_{timestamp}.json"

    evaluator = Evaluator()
    evaluator.export_report(report, output_path)
    print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    main()
