"""Q3 Structural Parity: AST-level similarity between original and recomposed.

Walk both trees with `ast.parse`, collect public-symbol signatures (classes,
top-level functions, methods), and report a Jaccard-style overlap score on
the union of fully-qualified signatures. Pure Python; no LLM calls.

Returns value in [0, 1]:
  1.0  → recomposed has the same public signatures as original
  0.0  → no overlap (catastrophic structural divergence)

What "signature" means here:
  - For functions: f"{module}.{name}({param_names})"
  - For classes:   f"{module}.{ClassName}" plus per-method signatures
  - We deliberately ignore type annotations and default values — they're
    cosmetic and the LLM may use slightly different wording. Names + arity
    are what matters for callers.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Files whose AST shape we don't expect the recomposer to match.
_SKIP_FILE_NAMES = {"setup.py", "conftest.py"}
_SKIP_DIR_PARTS = {".git", ".tox", "__pycache__", "build", "dist", ".pytest_cache",
                   ".mypy_cache", "tests", "test", "testing"}


def _module_name_for(repo_dir: Path, py_file: Path) -> str:
    """Return a dotted module path relative to repo_dir."""
    rel = py_file.relative_to(repo_dir).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else py_file.stem


def _is_public(name: str) -> bool:
    return not name.startswith("_") or name in {"__init__", "__call__", "__iter__",
                                                "__next__", "__len__", "__getitem__",
                                                "__setitem__", "__contains__",
                                                "__enter__", "__exit__"}


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = node.args
    parts = [a.arg for a in args.args]
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    parts.extend(a.arg for a in args.kwonlyargs)
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    return f"{node.name}({','.join(parts)})"


def _collect_signatures(repo_dir: Path) -> set[str]:
    """Walk repo_dir, collect a set of qualified public symbol signatures."""
    sigs: set[str] = set()
    if not repo_dir.is_dir():
        return sigs
    for py in repo_dir.rglob("*.py"):
        if any(p in _SKIP_DIR_PARTS for p in py.parts):
            continue
        if py.name in _SKIP_FILE_NAMES or py.name.startswith("test_"):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = py.read_text(encoding="latin-1")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            # Recomposer emitted a file that doesn't parse. Skip; the q1
            # metric will catch the resulting test failures anyway.
            continue
        module = _module_name_for(repo_dir, py)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _is_public(node.name):
                    sigs.add(f"{module}.{_signature(node)}")
            elif isinstance(node, ast.ClassDef):
                if _is_public(node.name):
                    sigs.add(f"{module}.class:{node.name}")
                    for child in node.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if _is_public(child.name):
                                sigs.add(
                                    f"{module}.{node.name}.{_signature(child)}"
                                )
    return sigs


def compute(original_dir: Path, recomposed_dir: Path, **kwargs) -> dict:
    """Compute Q3 structural parity via Jaccard overlap on public signatures."""
    if not original_dir.is_dir():
        return {
            "metric": "q3_structural_parity", "value": None,
            "detail": {"error": f"original_dir missing: {original_dir}"},
        }
    if not recomposed_dir.is_dir():
        return {
            "metric": "q3_structural_parity", "value": None,
            "detail": {"error": f"recomposed_dir missing: {recomposed_dir}"},
        }

    # The original lib's source is at original_dir/<lib_name>/, but it may
    # ALSO have utility scripts (setup.py, bin/*) at the top level we don't
    # want to compare. Prefer the package subdir if it exists; fall back to
    # repo root otherwise.
    lib_name = recomposed_dir.name
    pkg_in_original = original_dir / lib_name
    orig_root = pkg_in_original if pkg_in_original.is_dir() else original_dir

    orig_sigs = _collect_signatures(orig_root)
    new_sigs = _collect_signatures(recomposed_dir)

    union = orig_sigs | new_sigs
    intersection = orig_sigs & new_sigs
    only_in_original = orig_sigs - new_sigs
    only_in_recomposed = new_sigs - orig_sigs

    if not union:
        value = 0.0
    else:
        value = len(intersection) / len(union)

    return {
        "metric": "q3_structural_parity",
        "value": round(value, 4),
        "detail": {
            "signatures_in_original": len(orig_sigs),
            "signatures_in_recomposed": len(new_sigs),
            "intersection": len(intersection),
            "missing_from_recomposed": sorted(only_in_original)[:25],
            "extra_in_recomposed": sorted(only_in_recomposed)[:25],
            "missing_count": len(only_in_original),
            "extra_count": len(only_in_recomposed),
        },
    }
