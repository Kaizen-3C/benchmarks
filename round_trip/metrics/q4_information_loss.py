"""Q4 Information Loss: % of public symbols mentioned in spec text.

Phase 2 v1 (this file): pure-Python "are public symbols named in the spec?"
test. Walks `original_dir/<lib_name>/` for public defs, then greps the
combined spec text under `spec_dir` for each name. Returns the fraction
mentioned + the list of orphans.

This is the cheap-and-honest variant. v2 (line-derivability — "could a
reader of the ADRs alone reconstruct this code line?") is the right place
for an LLM, and per the kaizen-delta tool-routing convention that's a
**Haiku** call: a simple yes/no per spec section. Deferred to a follow-up.

No LLM call in v1.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_SKIP_DIR_PARTS = {".git", ".tox", "__pycache__", "build", "dist", ".pytest_cache",
                   ".mypy_cache", "tests", "test", "testing"}


def _is_public(name: str) -> bool:
    return not name.startswith("_") or name in {"__init__", "__call__"}


def _public_symbols(repo_dir: Path) -> list[str]:
    """List public class / function names defined in repo_dir's package source."""
    out: list[str] = []
    if not repo_dir.is_dir():
        return out
    for py in repo_dir.rglob("*.py"):
        if any(p in _SKIP_DIR_PARTS for p in py.parts):
            continue
        if py.name in {"setup.py", "conftest.py"} or py.name.startswith("test_"):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = py.read_text(encoding="latin-1")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if _is_public(node.name):
                    out.append(node.name)
    return sorted(set(out))


def _spec_corpus(spec_dir: Path) -> str:
    """Concatenate all text under spec_dir/{adrs,contracts,oracles}/."""
    if not spec_dir or not spec_dir.is_dir():
        return ""
    parts: list[str] = []
    for sub in ("adrs", "contracts", "oracles"):
        sub_dir = spec_dir / sub
        if not sub_dir.is_dir():
            continue
        for f in sub_dir.rglob("*"):
            if f.is_dir() or f.name.startswith("."):
                continue
            try:
                parts.append(f.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                parts.append(f.read_text(encoding="latin-1"))
    return "\n".join(parts)


def compute(original_dir: Path, recomposed_dir: Path, **kwargs) -> dict:
    """Symbol coverage: of every public symbol in the original, what
    fraction appears in the spec text?
    """
    spec_dir: Path | None = kwargs.get("spec_dir")
    if not original_dir.is_dir():
        return {
            "metric": "q4_information_loss", "value": None,
            "detail": {"error": f"original_dir missing: {original_dir}"},
        }
    if not spec_dir or not Path(spec_dir).is_dir():
        return {
            "metric": "q4_information_loss", "value": None,
            "detail": {"error": f"spec_dir missing: {spec_dir}"},
        }

    # Prefer the package subdir if it exists.
    lib_name = recomposed_dir.name if recomposed_dir else None
    pkg_in_original = (original_dir / lib_name) if lib_name else None
    orig_root = (
        pkg_in_original if pkg_in_original and pkg_in_original.is_dir()
        else original_dir
    )

    symbols = _public_symbols(orig_root)
    if not symbols:
        return {
            "metric": "q4_information_loss", "value": None,
            "detail": {"error": "no public symbols found in original"},
        }

    text = _spec_corpus(Path(spec_dir))
    if not text:
        return {
            "metric": "q4_information_loss", "value": 0.0,
            "detail": {"error": "spec text is empty",
                       "symbols_in_original": len(symbols)},
        }

    # Word-boundary match so e.g. "wcwidth" doesn't accidentally hit "wcswidth".
    mentioned: list[str] = []
    orphans: list[str] = []
    for sym in symbols:
        if re.search(rf"\b{re.escape(sym)}\b", text):
            mentioned.append(sym)
        else:
            orphans.append(sym)

    value = len(mentioned) / len(symbols)
    return {
        "metric": "q4_information_loss",
        "value": round(value, 4),
        "detail": {
            "symbols_in_original": len(symbols),
            "symbols_mentioned_in_spec": len(mentioned),
            "orphans": orphans[:25],
            "orphan_count": len(orphans),
        },
    }
