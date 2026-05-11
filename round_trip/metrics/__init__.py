"""Round-trip fidelity metrics (Q1-Q4).

Each submodule exports:
    compute(original_dir: Path, recomposed_dir: Path, **kwargs) -> dict

with return shape:
    {"metric": "<name>", "value": float | None, "detail": dict}

Phase 1: all metrics return placeholder values. Real computation lands in
phase 2 (per benchmarks/round_trip/PLAN.md).
"""

from __future__ import annotations

from . import (
    q1_test_parity,
    q2_behavioral_parity,
    q3_structural_parity,
    q4_information_loss,
    q4_line_derivability,
)

# Default tuple includes only the no-LLM metrics so `run_one` doesn't
# automatically spend money on Q4 v2. Callers that want v2 register it
# explicitly via `--with-q4-v2` (added to run_lite + run_one).
ALL_METRICS = (
    q1_test_parity,
    q2_behavioral_parity,
    q3_structural_parity,
    q4_information_loss,
)

ALL_METRICS_WITH_Q4_V2 = ALL_METRICS + (q4_line_derivability,)

__all__ = [
    "ALL_METRICS",
    "ALL_METRICS_WITH_Q4_V2",
    "q1_test_parity",
    "q2_behavioral_parity",
    "q3_structural_parity",
    "q4_information_loss",
    "q4_line_derivability",
]
