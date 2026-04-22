"""Round-trip spec-quality gates (run between Decompose and Recompose).

Each submodule exports:
    check(spec_dir: Path, original_dir: Path) -> dict

with return shape:
    {"gate": "<name>", "pass": bool | None, "failures": list[dict]}

A failed gate emits a structured "this WILL diverge" report; the
remediation engine consumes it (see remediation.py).

Phase 1: all gates return placeholder (pass=None, failures=[]).
Real logic lands in phase 3 (per benchmarks/round_trip/PLAN.md).
"""

from __future__ import annotations

from . import (
    consistency,
    coverage,
    implementation_leak,
    specificity,
    test_oracle_alignment,
)

ALL_GATES = (
    coverage,
    specificity,
    consistency,
    test_oracle_alignment,
    implementation_leak,
)

__all__ = [
    "ALL_GATES",
    "consistency",
    "coverage",
    "implementation_leak",
    "specificity",
    "test_oracle_alignment",
]
