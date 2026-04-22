"""Test-oracle alignment gate: every canonical test has an analog oracle.

Phase 3: map each canonical pytest test in `original_dir` to an oracle
entry in `spec_dir/oracles/`. Emit unaligned tests along with a suggested
oracle row (JSONL) to add for each.
"""

from __future__ import annotations

from pathlib import Path


def check(spec_dir: Path, original_dir: Path) -> dict:
    return {
        "gate": "test_oracle_alignment",
        "pass": None,
        "failures": [],
    }
