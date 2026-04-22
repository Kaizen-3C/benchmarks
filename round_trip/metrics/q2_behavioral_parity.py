"""Q2 Behavioral Parity: (input, output) equivalence on a curated set.

Phase 2: for each curated call in the oracles/ directory, execute against
both `original_dir` and `recomposed_dir` and compare return values /
raised exception types. Report fraction of matching outcomes.
"""

from __future__ import annotations

from pathlib import Path


def compute(original_dir: Path, recomposed_dir: Path, **kwargs) -> dict:
    return {
        "metric": "q2_behavioral_parity",
        "value": None,
        "detail": {"todo": "phase 2: execute curated (input,output) pairs on both impls"},
    }
