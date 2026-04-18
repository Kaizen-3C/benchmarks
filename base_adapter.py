"""Base adapter for external code generation benchmarks."""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkTask:
    """A single benchmark problem."""

    task_id: str
    prompt: str
    test_code: str
    entry_point: str
    canonical_solution: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """Result of running CD-AOR on one benchmark task."""

    task_id: str
    passed: bool
    generated_code: str
    error: Optional[str] = None
    confidence: float = 0.0
    steps_taken: int = 0
    duration_seconds: float = 0.0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    # Per-signal scores from the final evaluator pass (0.0 - 1.0 each).
    # Empty {} when the evaluator did not run successfully.  Populated by
    # runner.py from BootstrapResult.final_signals.  Used to diagnose cases
    # where composite confidence is pinned at a ceiling because 5/6 signals
    # silently returned 0.0.
    signal_scores: Dict[str, float] = field(default_factory=dict)


@dataclass
class BenchmarkReport:
    """Aggregate benchmark results."""

    benchmark_name: str
    total_tasks: int
    passed: int
    failed: int
    pass_at_1: float
    avg_confidence: float
    avg_steps: float
    avg_duration: float
    total_cost: float
    results: List[TaskResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "benchmark": self.benchmark_name,
            "total": self.total_tasks,
            "passed": self.passed,
            "failed": self.failed,
            "pass@1": round(self.pass_at_1, 4),
            "avg_confidence": round(self.avg_confidence, 4),
            "avg_steps": round(self.avg_steps, 2),
            "avg_duration_s": round(self.avg_duration, 2),
            "total_cost_usd": round(self.total_cost, 2),
        }


class BenchmarkAdapter(ABC):
    """Abstract base for benchmark dataset adapters."""

    def __init__(self, data_dir: Path, workspace_root: Path):
        self.data_dir = data_dir
        self.workspace_root = workspace_root

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def load_tasks(self) -> List[BenchmarkTask]:
        ...

    @abstractmethod
    def task_to_workspace(self, task: BenchmarkTask, workspace_path: Path) -> None:
        ...

    @abstractmethod
    def evaluate_output(self, task: BenchmarkTask, workspace_path: Path) -> TaskResult:
        ...

    def compute_metrics(self, results: List[TaskResult]) -> BenchmarkReport:
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        return BenchmarkReport(
            benchmark_name=self.name(),
            total_tasks=total,
            passed=passed,
            failed=total - passed,
            pass_at_1=passed / total if total > 0 else 0.0,
            avg_confidence=sum(r.confidence for r in results) / total if total else 0.0,
            avg_steps=sum(r.steps_taken for r in results) / total if total else 0.0,
            avg_duration=sum(r.duration_seconds for r in results) / total if total else 0.0,
            total_cost=sum(r.cost_usd for r in results),
            results=results,
        )

    def save_results(self, report: BenchmarkReport, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = output_dir / f"{self.name()}_{timestamp}.json"
        data = report.to_dict()
        data["per_task"] = [
            {
                "task_id": r.task_id,
                "passed": r.passed,
                "confidence": r.confidence,
                "steps": r.steps_taken,
                "duration_s": round(r.duration_seconds, 2),
                "cost_usd": round(r.cost_usd, 6),
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                # Per-signal breakdown from the final evaluator pass.  Round
                # to 4 decimals for readability; keys are SignalType values
                # (e.g. "test_pass_rate", "adr_compliance").
                "signals": {k: round(v, 4) for k, v in r.signal_scores.items()},
                "error": r.error,
            }
            for r in report.results
        ]
        path.write_text(json.dumps(data, indent=2))
        logger.info("Results saved to %s", path)
        return path
