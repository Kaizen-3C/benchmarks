"""Specificity gate: ADRs must be concrete enough to rebuild from.

Phase 3: per-ADR concreteness score (penalize vague modals like "may",
"should", missing parameters/thresholds). Emit amendment suggestions
for ADRs below the concreteness threshold.
"""

from __future__ import annotations

from pathlib import Path


def check(spec_dir: Path, original_dir: Path) -> dict:
    return {
        "gate": "specificity",
        "pass": None,
        "failures": [],
    }
