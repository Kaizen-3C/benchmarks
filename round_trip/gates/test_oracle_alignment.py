"""Test-oracle alignment gate: every canonical test has an analog oracle.

Per ADR-0063: an oracle is a (input, expected output) pair extracted from
the spec that the recomposed code can be checked against without running
the canonical test suite. If a canonical test has no oracle analog, the
spec is silently shifting the success criterion: Recompose can pass every
oracle and still fail the canonical tests.

Detection:
    - Walk pytest tests under `original_dir/tests/` (and `original_dir/test/`).
    - Collect each test function name (`test_<thing>`).
    - Walk `spec_dir/oracles/*.jsonl`. Each line is a JSON object; we expect
      either a `name` or `test` field naming the canonical test it covers.
    - Unaligned = canonical test with no matching oracle entry.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path


def _canonical_test_names(original_dir: Path) -> list[dict]:
    tests: list[dict] = []
    for tests_root in (original_dir / "tests", original_dir / "test"):
        if not tests_root.is_dir():
            continue
        for py in tests_root.rglob("test_*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("test_"):
                        tests.append(
                            {
                                "name": node.name,
                                "source": (
                                    f"{py.relative_to(original_dir).as_posix()}:{node.lineno}"
                                ),
                            }
                        )
    return tests


def _oracle_entries(spec_dir: Path) -> set[str]:
    oracles_dir = spec_dir / "oracles"
    names: set[str] = set()
    if not oracles_dir.is_dir():
        return names
    for f in oracles_dir.rglob("*.jsonl"):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for key in ("name", "test", "test_name", "canonical_test"):
                    val = obj.get(key)
                    if isinstance(val, str) and val:
                        names.add(val)
                        break
        except (OSError, UnicodeDecodeError):
            continue
    return names


def check(spec_dir: Path, original_dir: Path) -> dict:
    if not original_dir.is_dir():
        return {
            "gate": "test_oracle_alignment",
            "pass": False,
            "failures": [{"reason": "original_dir_missing", "path": str(original_dir)}],
        }
    if not spec_dir.is_dir():
        return {
            "gate": "test_oracle_alignment",
            "pass": False,
            "failures": [{"reason": "spec_dir_missing", "path": str(spec_dir)}],
        }

    tests = _canonical_test_names(original_dir)
    oracles = _oracle_entries(spec_dir)
    failures: list[dict] = []

    for t in tests:
        if t["name"] not in oracles:
            failures.append(
                {
                    "test": t["name"],
                    "source": t["source"],
                    "remediation": (
                        f"No oracle covers `{t['name']}` ({t['source']}). "
                        f"Append a JSONL row to {spec_dir.name}/oracles/ with "
                        f"`{{\"name\": \"{t['name']}\", \"input\": ..., "
                        f"\"expected\": ...}}` so Recompose is checked against "
                        f"the same contract the canonical test enforces."
                    ),
                }
            )

    return {
        "gate": "test_oracle_alignment",
        "pass": len(failures) == 0,
        "failures": failures,
        "stats": {
            "tests_total": len(tests),
            "oracles_total": len(oracles),
            "tests_aligned": len(tests) - len(failures),
            "alignment_pct": (
                round(100.0 * (len(tests) - len(failures)) / len(tests), 1)
                if tests
                else 100.0
            ),
        },
    }
