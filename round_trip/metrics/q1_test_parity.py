"""Q1 Test Parity: % of canonical tests passing on recomposed code.

Phase 2: run the library's own pytest suite (via commit0 or local pytest)
against `recomposed_dir` and report passed/total.
"""

from __future__ import annotations

from pathlib import Path


def compute(original_dir: Path, recomposed_dir: Path, **kwargs) -> dict:
    return {
        "metric": "q1_test_parity",
        "value": None,
        "detail": {"todo": "phase 2: run canonical pytest against recomposed_dir"},
    }
