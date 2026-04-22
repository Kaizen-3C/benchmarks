"""Coverage gate: every public symbol in the original appears in >=1 ADR/contract.

Phase 3: enumerate public symbols via AST of `original_dir`, scan ADR +
contract text under `spec_dir`, emit the list of missing symbols along
with a suggested ADR section to add for each.
"""

from __future__ import annotations

from pathlib import Path


def check(spec_dir: Path, original_dir: Path) -> dict:
    return {
        "gate": "coverage",
        "pass": None,
        "failures": [],
    }
