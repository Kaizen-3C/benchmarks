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
)

ALL_METRICS = (
    q1_test_parity,
    q2_behavioral_parity,
    q3_structural_parity,
    q4_information_loss,
)

__all__ = [
    "ALL_METRICS",
    "q1_test_parity",
    "q2_behavioral_parity",
    "q3_structural_parity",
    "q4_information_loss",
]
