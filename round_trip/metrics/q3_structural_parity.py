"""Q3 Structural Parity: AST / module-level diff size.

Phase 2: parse both trees with `ast.parse`, walk in parallel, count
node-level differences (classes, functions, signatures). Report a
normalized similarity score in [0, 1].
"""

from __future__ import annotations

from pathlib import Path


def compute(original_dir: Path, recomposed_dir: Path, **kwargs) -> dict:
    return {
        "metric": "q3_structural_parity",
        "value": None,
        "detail": {"todo": "phase 2: AST walk + node-level diff count"},
    }
