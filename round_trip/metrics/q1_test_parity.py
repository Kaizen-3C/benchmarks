"""Q1 Test Parity: % of canonical tests passing on the recomposed code.

Phase 2: copy the recomposed package and the original test suite into a
clean tempdir, set PYTHONPATH so `import <lib>` resolves to the recomposed
files, then run pytest. Parse the summary line. Report passed/failed/errors
and the resulting fraction.

Why a tempdir: the original repo is `~/kaizen-commit0/repos/<lib>/`, and
its `<lib>/` package directory shadows the recomposed one if we run pytest
in-place. Stamping the recomposed package into a fresh tree guarantees
the test imports resolve to the recomposed code, not the original.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Files we copy from the original repo when they exist (test config /
# fixture sources the test suite implicitly depends on).
_OPTIONAL_TOPLEVEL = (
    "conftest.py",
    "pytest.ini",
    "pyproject.toml",
    "setup.cfg",
    "tox.ini",
    "MANIFEST.in",
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_PYTEST_FINAL_RE = re.compile(
    r"(\d+)\s+(passed|failed|skipped|error[s]?)", re.IGNORECASE
)


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def _parse_pytest_summary(output: str) -> dict[str, int]:
    """Parse pytest's final summary line. Robust to colour codes and warnings."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    clean = _strip_ansi(output)
    # Look for the final summary line (the one after the `===` underline).
    # Easier: scan all matches; the LAST set wins (pytest re-prints summary).
    for n_str, kind in _PYTEST_FINAL_RE.findall(clean):
        n = int(n_str)
        kind_lower = kind.lower()
        if kind_lower.startswith("error"):
            counts["errors"] = n
        else:
            counts[kind_lower] = n
    return counts


def _find_tests_dir(original_dir: Path) -> Path | None:
    """Locate the canonical tests/ directory in the original repo.

    commit0 conventions: most libs use `tests/`; a few use `test/`. We prefer
    `tests/` if both exist.
    """
    for name in ("tests", "test", "testing"):
        d = original_dir / name
        if d.is_dir():
            return d
    return None


def _detect_package_dir(recomposed_dir: Path) -> tuple[Path, str]:
    """Find the actual importable package inside the recomposed output.

    The recomposed output lives under `recomposed/<lib>/`. When lib name ==
    package name (e.g., wcwidth), `__init__.py` is directly inside. When they
    differ (e.g., pyjwt → jwt), the package is a subdirectory. We detect this
    by looking for `__init__.py`.

    Returns (package_source_dir, package_name).
    """
    if (recomposed_dir / "__init__.py").is_file():
        return recomposed_dir, recomposed_dir.name

    # Look for a subdirectory containing __init__.py.
    candidates = [
        d for d in recomposed_dir.iterdir()
        if d.is_dir() and (d / "__init__.py").is_file()
    ]
    if len(candidates) == 1:
        return candidates[0], candidates[0].name

    # Multiple packages or none — fall back to the directory name.
    return recomposed_dir, recomposed_dir.name


def _stage_runspace(
    original_dir: Path, recomposed_dir: Path, lib_name: str, dst: Path
) -> dict[str, int]:
    """Lay out a clean tempdir that pytest can run against.

    Layout:
        dst/<pkg_name>/        ← the importable package from recomposed_dir
        dst/tests/             ← copied from original_dir/tests/
        dst/{conftest.py, ...} ← optional toplevel files copied if present
    """
    inv = {"recomposed_files": 0, "test_files": 0, "toplevel_files": 0,
           "package_name": lib_name}

    pkg_src, pkg_name = _detect_package_dir(recomposed_dir)
    inv["package_name"] = pkg_name

    pkg_dst = dst / pkg_name
    if pkg_src.is_dir():
        if pkg_src == recomposed_dir:
            shutil.copytree(recomposed_dir, pkg_dst)
        else:
            shutil.copytree(pkg_src, pkg_dst)
        inv["recomposed_files"] = sum(1 for _ in pkg_dst.rglob("*") if _.is_file())

    # Copy the test suite.
    tests_src = _find_tests_dir(original_dir)
    if tests_src is not None:
        tests_dst = dst / tests_src.name
        shutil.copytree(tests_src, tests_dst)
        inv["test_files"] = sum(1 for _ in tests_dst.rglob("*") if _.is_file())
    # Some libs (e.g., chardet) keep tests at the project root.
    for fname in ("test.py", "tests.py"):
        p = original_dir / fname
        if p.is_file():
            shutil.copy2(p, dst / fname)
            inv["test_files"] += 1

    # Copy any toplevel config the test suite might rely on.
    for name in _OPTIONAL_TOPLEVEL:
        src = original_dir / name
        if src.is_file():
            shutil.copy2(src, dst / name)
            inv["toplevel_files"] += 1

    return inv


def _strip_problematic_pytest_flags(dst: Path) -> dict[str, str]:
    """Some libs ship --cov-* flags in pytest config that require pytest-cov.

    In the round-trip context we don't want coverage; just pass/fail. Strip
    `--cov*` flags surgically from `addopts` in pytest.ini / setup.cfg /
    pyproject.toml / tox.ini. Returns a diagnostic record.

    We strip surgically (rather than clearing the whole addopts) so other
    useful flags like `-ra`, `--strict-markers`, `--tb=short` survive.
    """
    changes: dict[str, str] = {}

    # ini-style files: addopts may live under [pytest], [tool:pytest], or
    # tox.ini's [pytest] section.
    for fname in ("pytest.ini", "setup.cfg", "tox.ini"):
        p = dst / fname
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")

        # Match addopts lines + INI-style continuation lines (leading
        # whitespace), strip --cov-* tokens. wcwidth and several other
        # commit0-lite libs use the multi-line form:
        #     addopts = --x
        #               --cov=foo
        #               --y
        # Cov flags that take a positional value (space-separated form is
        # widely used in the wild — e.g., `addopts=--cov-report term --cov foo`).
        # Whitelist matches what pytest-cov accepts.
        _COV_FLAGS_WITH_VALUE = (
            "cov", "cov-report", "cov-config", "cov-fail-under",
            "cov-context", "cov-branch",
        )

        def _strip_cov_in_addopts(match: re.Match) -> str:
            block = match.group(0)
            # First: nuke --cov[-flag][=value] forms (no space-separated value).
            block = re.sub(
                r"\s*--(?:no-)?cov(?:-[\w-]+)?=\S+", "", block
            )
            # Then: nuke `--cov-flag value` (space-separated; value is the next
            # non-flag token). Done per-token to avoid over-greedy matching.
            tokens = re.split(r"(\s+)", block)  # keep separators
            out_tokens: list[str] = []
            skip_next_value = False
            for tok in tokens:
                if skip_next_value and tok.strip() and not tok.startswith("--"):
                    skip_next_value = False
                    continue  # drop the positional value
                if skip_next_value and tok.startswith("--"):
                    skip_next_value = False  # next is a flag; don't consume
                stripped = tok.strip()
                if stripped.startswith("--"):
                    name = stripped.lstrip("-").split("=", 1)[0]
                    if name in _COV_FLAGS_WITH_VALUE or name.startswith("cov"):
                        # Drop the flag itself and arm to drop the next value.
                        skip_next_value = True
                        continue
                out_tokens.append(tok)
            return "".join(out_tokens)

        # The block: an `addopts = ...` line followed by zero or more
        # continuation lines (start with whitespace; not blank).
        new = re.sub(
            r"^\s*addopts\s*=[^\n]*(?:\n[ \t]+[^\n]*)*",
            _strip_cov_in_addopts,
            text,
            flags=re.MULTILINE,
        )
        if new != text:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
            changes[fname] = "stripped --cov-* flags from addopts"

    # pyproject.toml: addopts under [tool.pytest.ini_options]. Same surgical
    # strip on the value (which is a string OR a list-of-strings).
    p = dst / "pyproject.toml"
    if p.is_file():
        text = p.read_text(encoding="utf-8", errors="replace")
        # Strip --cov tokens from quoted-string addopts values.
        new = re.sub(
            r"(addopts\s*=\s*\")([^\"]*)\"",
            lambda m: m.group(1)
            + re.sub(r"\s*--(?:no-)?cov(?:-[\w-]+)?(?:=\S+)?", "", m.group(2))
            + '"',
            text,
        )
        # Strip --cov tokens from list-of-strings addopts values.
        new = re.sub(
            r"(addopts\s*=\s*\[[^\]]*\])",
            lambda m: re.sub(
                r'"[^"]*--(?:no-)?cov(?:-[\w-]+)?[^"]*"\s*,?\s*',
                "",
                m.group(0),
            ),
            new,
        )
        if new != text:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
            changes["pyproject.toml"] = "stripped --cov-* flags from addopts"

    return changes


def compute(original_dir: Path, recomposed_dir: Path, **kwargs) -> dict:
    """Compute Q1 test parity.

    Args:
        original_dir: path to the original library checkout (has tests/).
        recomposed_dir: path to the recomposed package (e.g.,
            benchmarks/round_trip/recomposed/<lib>/). The DIRECTORY NAME is
            the package name imported by the tests.
    """
    if not original_dir.is_dir():
        return {
            "metric": "q1_test_parity", "value": None,
            "detail": {"error": f"original_dir missing: {original_dir}"},
        }
    if not recomposed_dir.is_dir():
        return {
            "metric": "q1_test_parity", "value": None,
            "detail": {"error": f"recomposed_dir missing: {recomposed_dir}"},
        }

    lib_name = recomposed_dir.name

    with tempfile.TemporaryDirectory(prefix=f"q1_{lib_name}_") as td:
        dst = Path(td)
        inv = _stage_runspace(original_dir, recomposed_dir, lib_name, dst)
        if inv["test_files"] == 0:
            return {
                "metric": "q1_test_parity", "value": None,
                "detail": {"error": "no tests/ directory in original_dir",
                           "inventory": inv},
            }

        cov_changes = _strip_problematic_pytest_flags(dst)

        env = os.environ.copy()
        # Force the recomposed package to win on import resolution. The
        # tempdir comes first; nothing else should shadow.
        env["PYTHONPATH"] = str(dst) + os.pathsep + env.get("PYTHONPATH", "")
        # Disable any user pytest plugins that may be installed system-wide.
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

        # Choose pytest target: prefer a tests dir with .py modules; else
        # fall back to root-level test.py/tests.py (chardet-style).
        pytest_target: str | None = None
        for d in ("tests", "test", "testing"):
            p = dst / d
            if p.is_dir() and any(
                f.name.startswith("test_") or f.name.endswith("_test.py")
                or f.name in ("test.py", "tests.py")
                for f in p.rglob("*.py")
            ):
                pytest_target = d
                break
        if pytest_target is None:
            for fname in ("test.py", "tests.py"):
                if (dst / fname).is_file():
                    pytest_target = fname
                    break
        if pytest_target is None:
            pytest_target = "."  # last resort: auto-discover from cwd

        proc = subprocess.run(
            [sys.executable, "-m", "pytest",
             "--tb=no", "-q", "--no-header",
             "-p", "no:cacheprovider",
             pytest_target],
            cwd=dst, env=env,
            capture_output=True, timeout=300,
        )
        stdout = proc.stdout.decode(errors="replace")
        stderr = proc.stderr.decode(errors="replace")
        output = stdout + "\n" + stderr

        counts = _parse_pytest_summary(output)
        collected = counts["passed"] + counts["failed"] + counts["skipped"]
        attempted = counts["passed"] + counts["failed"] + counts["errors"]
        value = (counts["passed"] / attempted) if attempted else 0.0

        # Did pytest even manage to collect and run tests, or did it fail
        # at import time?  returncode=2 with 0 collected = collection failure.
        test_suite_executed = collected > 0 or counts["errors"] > 0

        tail = _strip_ansi(output)[-1500:]

        return {
            "metric": "q1_test_parity",
            "value": round(value, 4),
            "detail": {
                "passed": counts["passed"],
                "failed": counts["failed"],
                "errors": counts["errors"],
                "skipped": counts["skipped"],
                "attempted": attempted,
                "collected": collected,
                "test_suite_executed": test_suite_executed,
                "pytest_returncode": proc.returncode,
                "inventory": inv,
                "cov_changes": cov_changes,
                "output_tail": tail,
            },
        }
