"""Acceptance tests for the five round-trip gates.

Each test builds a fixture in a tmp dir with a deliberate failure and
asserts the relevant gate catches it. This is the "at least one canonical
'this fails' example per gate" requirement from ADR-0063 §Validation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from gates import (  # noqa: E402
    consistency,
    coverage,
    implementation_leak,
    specificity,
    test_oracle_alignment,
)


def _make_lib(root: Path, files: dict[str, str]) -> Path:
    lib = root / "lib"
    for rel, content in files.items():
        f = lib / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    return lib


def _make_spec(root: Path, files: dict[str, str]) -> Path:
    spec = root / "spec"
    for rel, content in files.items():
        f = spec / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    return spec


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------


def test_coverage_passes_when_all_public_symbols_mentioned(tmp_path: Path) -> None:
    lib = _make_lib(
        tmp_path,
        {
            "mylib/__init__.py": "def public_function():\n    return 1\n\nclass PublicClass:\n    pass\n",
        },
    )
    spec = _make_spec(
        tmp_path,
        {
            "adrs/ADR-0001-decisions.md": (
                "# ADR-0001\n\nThe library exposes `public_function` and `PublicClass`.\n"
            ),
        },
    )
    result = coverage.check(spec, lib)
    assert result["pass"] is True, result
    assert result["stats"]["coverage_pct"] == 100.0


def test_coverage_fails_when_symbol_orphaned(tmp_path: Path) -> None:
    lib = _make_lib(
        tmp_path,
        {
            "mylib/__init__.py": (
                "def documented_func():\n    return 1\n\n"
                "def orphan_func():\n    return 2\n"
            ),
        },
    )
    spec = _make_spec(
        tmp_path,
        {"adrs/ADR-0001.md": "# ADR-0001\n\nWe expose `documented_func`.\n"},
    )
    result = coverage.check(spec, lib)
    assert result["pass"] is False
    names = {f["symbol"] for f in result["failures"]}
    assert "orphan_func" in names
    assert "documented_func" not in names


# ---------------------------------------------------------------------------
# specificity
# ---------------------------------------------------------------------------


def test_specificity_passes_for_concrete_adr(tmp_path: Path) -> None:
    spec = _make_spec(
        tmp_path,
        {
            "adrs/ADR-0001-cache.md": (
                "# ADR-0001 Cache\n\n"
                "We use an LRU cache with max size 128 entries and no TTL.\n"
                "Eviction policy: LRU. Hash function: SHA-256.\n"
            ),
        },
    )
    result = specificity.check(spec, tmp_path)
    assert result["pass"] is True, result["stats"]


def test_specificity_fails_for_vague_adr(tmp_path: Path) -> None:
    spec = _make_spec(
        tmp_path,
        {
            "adrs/ADR-0002-vague.md": (
                "# ADR-0002 Caching policy\n\n"
                "We may cache results. The cache should typically evict old entries.\n"
                "Roughly some entries are kept. Usually this works well.\n"
            ),
        },
    )
    result = specificity.check(spec, tmp_path)
    assert result["pass"] is False
    assert any("vague" in f["remediation"].lower() for f in result["failures"])


# ---------------------------------------------------------------------------
# consistency
# ---------------------------------------------------------------------------


def test_consistency_passes_when_refs_resolve(tmp_path: Path) -> None:
    spec = _make_spec(
        tmp_path,
        {
            "adrs/ADR-0001.md": "# ADR-0001\n\nSee ADR-0002 for cache policy.\n",
            "adrs/ADR-0002.md": "# ADR-0002\n\nLRU, max 128.\n",
        },
    )
    result = consistency.check(spec, tmp_path)
    assert result["pass"] is True, result["failures"]


def test_consistency_fails_on_dangling_adr_ref(tmp_path: Path) -> None:
    spec = _make_spec(
        tmp_path,
        {"adrs/ADR-0001.md": "# ADR-0001\n\nSee ADR-0099 for caching.\n"},
    )
    result = consistency.check(spec, tmp_path)
    assert result["pass"] is False
    refs = {f["ref"] for f in result["failures"]}
    assert "ADR-0099" in refs


# ---------------------------------------------------------------------------
# test_oracle_alignment
# ---------------------------------------------------------------------------


def test_oracle_alignment_passes_when_every_test_has_oracle(tmp_path: Path) -> None:
    lib = _make_lib(
        tmp_path,
        {
            "mylib/__init__.py": "def add(a, b):\n    return a + b\n",
            "tests/test_add.py": "def test_add_basic():\n    assert 1\n",
        },
    )
    spec = _make_spec(
        tmp_path,
        {"oracles/add.jsonl": '{"name": "test_add_basic", "input": [1, 2], "expected": 3}\n'},
    )
    result = test_oracle_alignment.check(spec, lib)
    assert result["pass"] is True, result["failures"]
    assert result["stats"]["alignment_pct"] == 100.0


def test_oracle_alignment_fails_when_test_has_no_oracle(tmp_path: Path) -> None:
    lib = _make_lib(
        tmp_path,
        {
            "mylib/__init__.py": "def add(a, b):\n    return a + b\n",
            "tests/test_add.py": (
                "def test_add_basic():\n    assert 1\n\n"
                "def test_add_negative():\n    assert 1\n"
            ),
        },
    )
    spec = _make_spec(
        tmp_path,
        {"oracles/add.jsonl": '{"name": "test_add_basic", "input": [1, 2], "expected": 3}\n'},
    )
    result = test_oracle_alignment.check(spec, lib)
    assert result["pass"] is False
    unaligned = {f["test"] for f in result["failures"]}
    assert "test_add_negative" in unaligned
    assert "test_add_basic" not in unaligned


# ---------------------------------------------------------------------------
# implementation_leak
# ---------------------------------------------------------------------------


def test_leak_passes_for_decision_only_adr(tmp_path: Path) -> None:
    lib = _make_lib(
        tmp_path,
        {"mylib/__init__.py": "def foo():\n    return _helper()\n\ndef _helper():\n    return 1\n"},
    )
    spec = _make_spec(
        tmp_path,
        {
            "adrs/ADR-0001-decisions.md": (
                "# ADR-0001\n\nThe `foo` function returns a constant. "
                "Time complexity: O(1).\n"
            ),
        },
    )
    result = implementation_leak.check(spec, lib)
    assert result["pass"] is True, result["failures"]


def test_leak_fails_on_long_code_block(tmp_path: Path) -> None:
    spec = _make_spec(
        tmp_path,
        {
            "adrs/ADR-0001-leaky.md": (
                "# ADR-0001\n\n"
                "```python\n"
                "def foo():\n"
                "    x = 1\n"
                "    y = 2\n"
                "    z = 3\n"
                "    a = 4\n"
                "    b = 5\n"
                "    c = 6\n"
                "    d = 7\n"
                "    return x + y + z + a + b + c + d\n"
                "```\n"
            ),
        },
    )
    result = implementation_leak.check(spec, tmp_path)
    assert result["pass"] is False
    kinds = {f["leak_kind"] for f in result["failures"]}
    assert "long_code_block" in kinds


def test_leak_fails_on_private_symbol_reference(tmp_path: Path) -> None:
    lib = _make_lib(
        tmp_path,
        {
            "mylib/__init__.py": (
                "def public_api():\n    return _internal_helper()\n\n"
                "def _internal_helper():\n    return 42\n"
            ),
        },
    )
    spec = _make_spec(
        tmp_path,
        {
            "adrs/ADR-0001.md": (
                "# ADR-0001\n\nThe public API delegates to `_internal_helper` "
                "which returns the answer.\n"
            ),
        },
    )
    result = implementation_leak.check(spec, lib)
    assert result["pass"] is False
    assert any(f["leak_kind"] == "private_symbol_reference" for f in result["failures"])


# ---------------------------------------------------------------------------
# integration: all gates run on a deliberately-broken spec
# ---------------------------------------------------------------------------


def test_all_gates_catch_distinct_failures_on_broken_spec(tmp_path: Path) -> None:
    """Every gate should fire at least once on a maximally-broken fixture."""
    lib = _make_lib(
        tmp_path,
        {
            "mylib/__init__.py": (
                "def public_func():\n    return _hidden()\n\n"
                "def orphan_func():\n    return 2\n\n"
                "def _hidden():\n    return 0\n"
            ),
            "tests/test_basic.py": (
                "def test_public_func():\n    assert 1\n\n"
                "def test_unaligned():\n    assert 1\n"
            ),
        },
    )
    spec = _make_spec(
        tmp_path,
        {
            "adrs/ADR-0001-vague.md": (
                "# ADR-0001\n\n"
                "We may cache results and `_hidden` should typically work.\n"
                "See ADR-0099 for details.\n"
                "```python\n"
                "def cache_impl():\n"
                "    x = 1\n"
                "    y = 2\n"
                "    z = 3\n"
                "    a = 4\n"
                "    b = 5\n"
                "    c = 6\n"
                "    d = 7\n"
                "    e = 8\n"
                "    f = 9\n"
                "    return x + y + z + a + b + c + d + e + f\n"
                "```\n"
                "References public_func only.\n"
            ),
            "oracles/o.jsonl": '{"name": "test_public_func", "expected": 1}\n',
        },
    )

    results = {
        "coverage": coverage.check(spec, lib),
        "specificity": specificity.check(spec, lib),
        "consistency": consistency.check(spec, lib),
        "test_oracle_alignment": test_oracle_alignment.check(spec, lib),
        "implementation_leak": implementation_leak.check(spec, lib),
    }

    for name, r in results.items():
        assert r["pass"] is False, f"{name} should have failed; got {r}"
        assert len(r["failures"]) > 0, f"{name} reported pass=False but no failures"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
