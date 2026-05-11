"""Oracle-executable gate (cross-check axis).

Runs every oracle row against `original_dir` directly. If an oracle's
expected output doesn't match what the original code actually produces,
the oracle drifted from the source during Decompose and the round-trip
cannot be evaluated against it without rigging the result.

This is the cross-check gate sketched in benchmarks/round_trip/REVIEW_FROM_ARIS.md
under "Cross-check gate candidates", item (1). It runs offline (no LLM,
no recompose) and is the cheapest verifier of spec quality we can add.

Schema coverage (deterministic, no LLM):

  | shape                                            | handled |
  |--------------------------------------------------|---------|
  | {"input": {...}, "expected": <scalar>}            | yes     |
  | {"input": {...}, "expected": "<ExceptionName>"}   | yes     |
  | {"input": {...}, "expected": {"raises": "X"}}     | yes     |
  | {"input": {...}, "expected": {"raises": null}}    | yes (no raise expected) |
  | {"input": {...}, "expected_type": "<typename>"}   | yes     |
  | {"input": {...}, "expected_first": <value>}       | yes     |
  | {"input": {...}, "expected_last": <value>}        | yes     |
  | {"input": {...}, "expected": <list> or <dict>}    | yes (==) |
  | composite/multi-key expected (e.g., pyjwt)        | skip    |
  | sentinel inputs ("__lambda__", "==now")           | skip    |

Symbol resolution: for `oracles/<name>.jsonl`, look for callable `<name>`
or `_<name>` at module scope inside `original_dir`. If exactly one match
exists, call it with `**input`. If zero or multiple matches, the oracle
file is skipped with reason. This is intentional: false-positive failures
from wrong-symbol resolution would be worse than the missed coverage.

Output (matching the other gate modules):
    {
      "gate": "oracle_executable",
      "pass": bool,                    # True iff zero failures
      "failures": [
        {"oracle_file", "oracle_name", "kind",
         "actual", "expected", "remediation"},
        ...
      ],
      "stats": {
        "oracle_files": int,
        "rows_total": int,
        "rows_executed": int,
        "rows_skipped": int,
        "rows_passed": int,
        "rows_failed": int,
        "skip_reasons": {<reason>: <count>},
      },
    }

A "fail" means the oracle's expected output disagrees with the source's
actual output — that's the cross-check failure we care about.
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
from pathlib import Path
from typing import Any


# ---- symbol resolution ------------------------------------------------------


def _toplevel_callable_names(py_file: Path) -> set[str]:
    """Return the set of module-level def names in `py_file` (public + private)."""
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set()
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _resolve_symbol(
    original_dir: Path, oracle_name: str
) -> tuple[Any, str | None, str | None]:
    """Find `oracle_name` (or `_oracle_name`) somewhere under original_dir.

    Returns (callable_or_None, dotted_path, skip_reason).
    """
    skip_dirs = {"tests", "test", ".git", ".tox", "__pycache__", "build", "dist"}

    candidates: list[tuple[str, Path, str]] = []
    for py in original_dir.rglob("*.py"):
        if any(part in skip_dirs for part in py.parts):
            continue
        names = _toplevel_callable_names(py)
        rel_module = (
            py.relative_to(original_dir).with_suffix("").as_posix().replace("/", ".")
        )
        for sym in (oracle_name, f"_{oracle_name}"):
            if sym in names:
                candidates.append((sym, py, rel_module))

    if not candidates:
        return None, None, "no_matching_symbol"
    # Prefer a non-test, non-conftest candidate; if multiple, prefer the
    # shortest module path (typically the package root), tie-break by
    # public-name preference.
    def _key(c: tuple[str, Path, str]) -> tuple:
        sym, _path, mod = c
        return (
            mod.count("."),                # shorter dotted path first
            0 if not sym.startswith("_") else 1,  # public preferred
            mod,
        )
    candidates.sort(key=_key)
    sym, path, dotted = candidates[0]

    # Import the module by injecting original_dir to sys.path. Use a
    # private cache to avoid re-importing identical modules across rows.
    parent_str = str(original_dir.parent)
    if parent_str not in sys.path:
        sys.path.insert(0, parent_str)
    pkg_str = str(original_dir)
    if pkg_str not in sys.path:
        sys.path.insert(0, pkg_str)

    try:
        # Try importing as <pkg_name>.<dotted> first; fall back to dotted.
        pkg_name = original_dir.name
        candidates_paths = [
            f"{pkg_name}.{dotted}" if dotted else pkg_name,
            dotted,
        ]
        last_err = None
        mod_obj = None
        for path in candidates_paths:
            if not path:
                continue
            try:
                mod_obj = importlib.import_module(path)
                break
            except ImportError as e:
                last_err = e
                continue
        if mod_obj is None:
            return None, None, f"import_failed: {last_err}"
        func = getattr(mod_obj, sym, None)
        if func is None:
            return None, None, f"symbol_not_in_module: {sym}"
        return func, f"{mod_obj.__name__}.{sym}", None
    except Exception as e:  # noqa: BLE001 — informative skip beats hard fail
        return None, None, f"import_error: {type(e).__name__}: {str(e)[:120]}"


# ---- oracle row interpretation ---------------------------------------------


# Sentinel-input markers we don't try to substitute deterministically.
_SENTINEL_INPUT_VALUES = {"__lambda__", "==now"}


def _row_has_sentinel_input(row: dict) -> bool:
    inp = row.get("input")
    if not isinstance(inp, dict):
        return False
    for v in inp.values():
        if isinstance(v, str) and v in _SENTINEL_INPUT_VALUES:
            return True
    return False


_KNOWN_EXCEPTION_NAMES = {
    "TypeError", "ValueError", "KeyError", "IndexError", "AttributeError",
    "ImportError", "RuntimeError", "NotImplementedError", "ZeroDivisionError",
    "OverflowError", "AssertionError", "StopIteration", "FileNotFoundError",
    "OSError",
}

# Sentinel string in `expected` that means "should not raise; any return
# value is acceptable." Surfaced from spec/deprecated/oracles/validate_reason.jsonl.
_NO_EXCEPTION_SENTINELS = {"no_exception", "ok", "no_raise"}


def _is_exception_name(s: str) -> bool:
    if not isinstance(s, str):
        return False
    if s in _NO_EXCEPTION_SENTINELS:
        return False
    return s in _KNOWN_EXCEPTION_NAMES or s.endswith("Error")


def _classify_row(row: dict) -> tuple[str, str | None]:
    """Return (kind, skip_reason).

    kind ∈ {"scalar_eq", "exception_name", "raises_dict",
             "expected_type", "expected_first", "expected_last", "skip"}.
    """
    if not isinstance(row.get("input"), dict):
        return ("skip", "input_not_dict")
    if _row_has_sentinel_input(row):
        return ("skip", "sentinel_input")
    if "expected_type" in row:
        return ("expected_type", None)
    if "expected_first" in row:
        return ("expected_first", None)
    if "expected_last" in row:
        return ("expected_last", None)
    if "expected" not in row:
        return ("skip", "no_expected_field")
    expected = row["expected"]
    if isinstance(expected, dict):
        if set(expected.keys()) == {"raises"}:
            return ("raises_dict", None)
        return ("skip", "composite_expected")
    if isinstance(expected, str) and expected in _NO_EXCEPTION_SENTINELS:
        return ("no_exception_sentinel", None)
    if isinstance(expected, str) and _is_exception_name(expected):
        return ("exception_name", None)
    if expected is None or isinstance(expected, (bool, int, float, str, list, tuple)):
        return ("scalar_eq", None)
    return ("skip", "unknown_expected_shape")


def _execute_row(func: Any, row: dict, kind: str) -> tuple[bool, str, Any]:
    """Run the oracle and decide pass/fail.

    Returns (passed, evidence_str, actual).
    """
    inp = row["input"]
    if kind == "no_exception_sentinel":
        try:
            actual = func(**inp)
            return (True, "no raise expected; returned cleanly", actual)
        except Exception as e:  # noqa: BLE001
            return (False, f"expected no raise, got {type(e).__name__}: {e}", None)

    if kind == "exception_name":
        expected_exc = row["expected"]
        try:
            actual = func(**inp)
            return (False, f"expected raise {expected_exc}, got value {actual!r}", actual)
        except Exception as e:  # noqa: BLE001
            cls = type(e).__name__
            if cls == expected_exc:
                return (True, f"raised {cls} as expected", None)
            return (False, f"expected {expected_exc}, raised {cls}: {e}", None)

    if kind == "raises_dict":
        expected_exc = row["expected"]["raises"]
        try:
            actual = func(**inp)
            if expected_exc is None:
                return (True, "no raise expected; returned cleanly", actual)
            return (False, f"expected raise {expected_exc}, got value {actual!r}", actual)
        except Exception as e:  # noqa: BLE001
            cls = type(e).__name__
            if expected_exc is None:
                return (False, f"no raise expected; raised {cls}: {e}", None)
            if cls == expected_exc:
                return (True, f"raised {cls} as expected", None)
            return (False, f"expected {expected_exc}, raised {cls}: {e}", None)

    try:
        actual = func(**inp)
    except Exception as e:  # noqa: BLE001
        return (False, f"unexpected raise {type(e).__name__}: {e}", None)

    if kind == "scalar_eq":
        expected = row["expected"]
        if actual == expected:
            return (True, f"== {expected!r}", actual)
        return (False, f"actual={actual!r} != expected={expected!r}", actual)
    if kind == "expected_type":
        expected = row["expected_type"]
        if type(actual).__name__ == expected:
            return (True, f"type=={expected}", actual)
        return (
            False,
            f"actual_type={type(actual).__name__} != expected_type={expected}",
            actual,
        )
    if kind == "expected_first":
        try:
            first = actual[0]
        except (TypeError, IndexError):
            return (False, f"actual={actual!r} not indexable for [0]", actual)
        expected = row["expected_first"]
        if first == expected:
            return (True, f"[0]=={expected!r}", actual)
        return (False, f"actual[0]={first!r} != expected_first={expected!r}", actual)
    if kind == "expected_last":
        try:
            last = actual[-1]
        except (TypeError, IndexError):
            return (False, f"actual={actual!r} not indexable for [-1]", actual)
        expected = row["expected_last"]
        if last == expected:
            return (True, f"[-1]=={expected!r}", actual)
        return (False, f"actual[-1]={last!r} != expected_last={expected!r}", actual)

    return (False, f"unhandled kind: {kind}", None)


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


# ---- public gate entry point ------------------------------------------------


def check(spec_dir: Path, original_dir: Path) -> dict:
    if not spec_dir.is_dir():
        return {
            "gate": "oracle_executable",
            "pass": False,
            "failures": [{"reason": "spec_dir_missing", "path": str(spec_dir)}],
        }
    if not original_dir.is_dir():
        return {
            "gate": "oracle_executable",
            "pass": False,
            "failures": [{"reason": "original_dir_missing", "path": str(original_dir)}],
        }

    oracles_dir = spec_dir / "oracles"
    if not oracles_dir.is_dir():
        return {
            "gate": "oracle_executable",
            "pass": True,
            "failures": [],
            "stats": {"reason": "no_oracles_dir"},
        }

    failures: list[dict] = []
    skip_reasons: dict[str, int] = {}
    rows_total = 0
    rows_executed = 0
    rows_passed = 0
    rows_failed = 0
    files_seen = 0
    file_records: list[dict] = []

    # Per-file: resolve symbol once, then execute each row.
    for jsonl_file in sorted(oracles_dir.rglob("*.jsonl")):
        files_seen += 1
        oracle_name = jsonl_file.stem
        rel = jsonl_file.relative_to(spec_dir).as_posix()
        rows = _read_jsonl(jsonl_file)
        rows_total += len(rows)

        func, dotted_path, sym_skip = _resolve_symbol(original_dir, oracle_name)
        if func is None:
            skip_reasons[sym_skip or "unknown"] = (
                skip_reasons.get(sym_skip or "unknown", 0) + len(rows)
            )
            file_records.append({
                "file": rel,
                "rows": len(rows),
                "resolved": None,
                "skip_reason": sym_skip,
            })
            continue

        file_passed = 0
        file_failed = 0
        file_skipped = 0
        for row in rows:
            kind, skip_reason = _classify_row(row)
            if kind == "skip":
                rows_executed += 0
                skip_reasons[skip_reason or "unknown"] = (
                    skip_reasons.get(skip_reason or "unknown", 0) + 1
                )
                file_skipped += 1
                continue
            rows_executed += 1
            passed, evidence, actual = _execute_row(func, row, kind)
            if passed:
                rows_passed += 1
                file_passed += 1
            else:
                rows_failed += 1
                file_failed += 1
                failures.append({
                    "oracle_file": rel,
                    "oracle_name": row.get("name", "<unnamed>"),
                    "kind": kind,
                    "input_preview": str(row.get("input"))[:120],
                    "expected": (
                        row.get("expected")
                        if "expected" in row
                        else {
                            k: row.get(k)
                            for k in ("expected_type", "expected_first", "expected_last")
                            if k in row
                        }
                    ),
                    "evidence": evidence,
                    "remediation": (
                        f"oracle row `{row.get('name')}` in {rel} disagrees with "
                        f"`{dotted_path}`. Either the oracle was authored against a "
                        f"different version of the source, or Decompose paraphrased "
                        f"the expected output. Re-derive the expected value from a "
                        f"canonical run of `{dotted_path}` and update the oracle."
                    ),
                })
        file_records.append({
            "file": rel,
            "rows": len(rows),
            "resolved": dotted_path,
            "passed": file_passed,
            "failed": file_failed,
            "skipped": file_skipped,
        })

    return {
        "gate": "oracle_executable",
        "pass": rows_failed == 0,
        "failures": failures,
        "stats": {
            "oracle_files": files_seen,
            "rows_total": rows_total,
            "rows_executed": rows_executed,
            "rows_skipped": rows_total - rows_executed,
            "rows_passed": rows_passed,
            "rows_failed": rows_failed,
            "skip_reasons": skip_reasons,
            "files": file_records,
        },
    }
