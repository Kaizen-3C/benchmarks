"""Implementation-leak gate: ADRs must describe behavior, not code.

Phase 3: scan ADR text for code-shaped content (fenced blocks, concrete
identifiers that match `original_dir`'s private symbols, inlined algorithm
steps). Leakage rigs the round-trip by letting Recompose cheat. Emit the
list of leaked snippets + refactor suggestions.
"""

from __future__ import annotations

from pathlib import Path


def check(spec_dir: Path, original_dir: Path) -> dict:
    return {
        "gate": "implementation_leak",
        "pass": None,
        "failures": [],
    }
