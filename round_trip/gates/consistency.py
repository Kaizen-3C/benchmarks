"""Consistency gate: no dangling cross-references in contracts/ADRs.

Phase 3: parse every `ADR-NNNN` / contract name reference and verify its
target exists under `spec_dir`. Emit the list of broken references.
"""

from __future__ import annotations

from pathlib import Path


def check(spec_dir: Path, original_dir: Path) -> dict:
    return {
        "gate": "consistency",
        "pass": None,
        "failures": [],
    }
