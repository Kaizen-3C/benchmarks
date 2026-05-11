"""Coverage gate: every public symbol in the original appears in >=1 ADR/contract.

Per ADR-0063: missing symbols mean Recompose will likely omit or hallucinate
them. Failed payload lists each orphan symbol along with the source location
and a suggested ADR section to add.

v2 (2026-05-07): scopes to "test-relevant" symbols — only symbols that appear
in the test suite's import statements or direct references. This eliminates
noise from setup.py utilities, CLI entry-points, and helper functions the
tests never touch (the original gate had r≈0 against Q1 because it measured
the wrong thing).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


def _test_imported_names(original_dir: Path) -> set[str]:
    """Extract names the test suite imports or references from the library.

    Scans test files for `import <pkg>`, `from <pkg> import X`, and
    `from <pkg>.mod import Y` patterns. Returns a set of symbol names
    that the tests actually use.
    """
    names: set[str] = set()
    test_dirs = {"tests", "test", "testing"}

    for td_name in test_dirs:
        td = original_dir / td_name
        if not td.is_dir():
            continue
        for py in td.rglob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    pkg_root = original_dir.name
                    if node.module == pkg_root or node.module.startswith(pkg_root + "."):
                        for alias in (node.names or []):
                            if alias.name != "*":
                                names.add(alias.name)
                elif isinstance(node, ast.Import):
                    for alias in (node.names or []):
                        names.add(alias.name.split(".")[-1])
    return names


def _public_symbols(original_dir: Path, test_scoped: bool = True) -> list[dict]:
    """Walk Python files under original_dir, collect public top-level symbols.

    If test_scoped=True (default), only returns symbols that the test suite
    imports or references. This filters out setup.py utilities, CLI helpers,
    and other symbols the tests never touch.
    """
    test_names = _test_imported_names(original_dir) if test_scoped else None
    symbols: list[dict] = []
    skip_dirs = {"tests", "test", ".git", ".tox", "__pycache__", "build", "dist"}

    for py in original_dir.rglob("*.py"):
        if any(part in skip_dirs for part in py.parts):
            continue
        if py.name.startswith("test_") or py.name.endswith("_test.py"):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel_module = py.relative_to(original_dir).with_suffix("").as_posix().replace("/", ".")
        for node in tree.body:
            name = getattr(node, "name", None)
            if not name or name.startswith("_"):
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "function"
            elif isinstance(node, ast.ClassDef):
                kind = "class"
            else:
                continue
            if test_names is not None and name not in test_names:
                continue
            symbols.append(
                {
                    "name": name,
                    "kind": kind,
                    "module": rel_module,
                    "lineno": node.lineno,
                    "source": f"{py.relative_to(original_dir).as_posix()}:{node.lineno}",
                }
            )
    return symbols


def _spec_corpus(spec_dir: Path) -> str:
    """Concatenate ADR + contract text into a single searchable corpus."""
    parts: list[str] = []
    for sub in ("adrs", "contracts"):
        d = spec_dir / sub
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if f.is_file() and f.suffix in {".md", ".markdown", ".txt"}:
                try:
                    parts.append(f.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError):
                    continue
    return "\n".join(parts)


def check(spec_dir: Path, original_dir: Path) -> dict:
    if not original_dir.is_dir():
        return {
            "gate": "coverage",
            "pass": False,
            "failures": [{"reason": "original_dir_missing", "path": str(original_dir)}],
        }
    if not spec_dir.is_dir():
        return {
            "gate": "coverage",
            "pass": False,
            "failures": [{"reason": "spec_dir_missing", "path": str(spec_dir)}],
        }

    test_names = _test_imported_names(original_dir)
    use_scoped = len(test_names) > 0
    symbols = _public_symbols(original_dir, test_scoped=use_scoped)
    all_symbols = _public_symbols(original_dir, test_scoped=False)
    corpus = _spec_corpus(spec_dir)
    failures: list[dict] = []

    for sym in symbols:
        pattern = re.compile(rf"\b{re.escape(sym['name'])}\b")
        if not pattern.search(corpus):
            failures.append(
                {
                    "symbol": sym["name"],
                    "kind": sym["kind"],
                    "module": sym["module"],
                    "source": sym["source"],
                    "remediation": (
                        f"Add an ADR section covering `{sym['name']}` "
                        f"({sym['kind']} in {sym['module']}). "
                        f"Reference: {sym['source']}."
                    ),
                }
            )

    return {
        "gate": "coverage",
        "pass": len(failures) == 0,
        "failures": failures,
        "stats": {
            "symbols_total": len(symbols),
            "symbols_covered": len(symbols) - len(failures),
            "symbols_total_unscoped": len(all_symbols),
            "coverage_pct": (
                round(100.0 * (len(symbols) - len(failures)) / len(symbols), 1)
                if symbols
                else 100.0
            ),
        },
    }
