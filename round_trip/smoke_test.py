"""Post-recompose smoke test: does the package import? Does pytest collect?

Zero LLM cost. Catches the failure modes static gates can't see:
  - Inconsistent internal imports (manifest says X exists, code doesn't define X)
  - Missing relative-import targets
  - Syntax errors in generated code
  - Missing __init__.py re-exports

Returns the FIRST traceback hit (import error preferred; collection error if
import succeeds). The traceback is the input to remediation v2.

Why first-traceback-only: Python halts at the first ImportError anyway, so
later failures aren't observable until the first is fixed. One concrete
failure beats a list of speculative failures.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Reuse Q1's package-detection logic so smoke and Q1 stage identically.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from metrics.q1_test_parity import (  # noqa: E402
    _detect_package_dir,
    _strip_problematic_pytest_flags,
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def _import_check(dst: Path, pkg_name: str, env: dict) -> dict:
    """Run `python -c "import <pkg>"` in a subprocess. Capture traceback."""
    proc = subprocess.run(
        [sys.executable, "-c", f"import {pkg_name}"],
        cwd=dst, env=env, capture_output=True, timeout=30,
    )
    out = (proc.stdout + proc.stderr).decode(errors="replace")
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "traceback": _strip_ansi(out)[-2000:] if proc.returncode != 0 else "",
    }


def _collect_check(dst: Path, env: dict) -> dict:
    """Run `pytest --collect-only` once import is known-good.

    Locates pytest targets by checking standard dirs first; if those don't
    contain Python test modules, falls back to root-level `test.py` /
    `tests.py` (chardet, etc.) or auto-discovery from cwd.
    """
    target: str | None = None
    for d in ("tests", "test", "testing"):
        p = dst / d
        if p.is_dir():
            has_py_tests = any(
                f.name.startswith("test_") or f.name.endswith("_test.py")
                or f.name in ("tests.py", "test.py")
                for f in p.rglob("*.py")
            )
            if has_py_tests:
                target = d
                break
    if target is None:
        # Look for root-level test.py or tests.py.
        for f in ("test.py", "tests.py"):
            if (dst / f).is_file():
                target = f
                break
    if target is None:
        return {"ok": True, "skipped": True, "reason": "no test files found"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header",
         "-p", "no:cacheprovider", target],
        cwd=dst, env=env, capture_output=True, timeout=120,
    )
    out = (proc.stdout + proc.stderr).decode(errors="replace")
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "traceback": _strip_ansi(out)[-2000:] if proc.returncode != 0 else "",
    }


def smoke_test(
    original_dir: Path, recomposed_dir: Path
) -> dict:
    """Stage recomposed code + tests, then check import + collection.

    Returns:
        {
          "ok": bool,                # both import and collect succeeded
          "import": {ok, traceback},
          "collect": {ok, traceback},
          "package_name": str,       # detected importable package name
          "first_traceback": str,    # the actionable error to feed remediation
        }
    """
    if not recomposed_dir.is_dir():
        return {
            "ok": False,
            "error": f"recomposed_dir missing: {recomposed_dir}",
            "first_traceback": "",
        }

    pkg_src, pkg_name = _detect_package_dir(recomposed_dir)

    with tempfile.TemporaryDirectory(prefix=f"smoke_{recomposed_dir.name}_") as td:
        dst = Path(td)
        # Stage the package.
        pkg_dst = dst / pkg_name
        if pkg_src == recomposed_dir:
            shutil.copytree(recomposed_dir, pkg_dst)
        else:
            shutil.copytree(pkg_src, pkg_dst)
        # Stage the test suite (for collect-only check).
        for tname in ("tests", "test", "testing"):
            src = original_dir / tname
            if src.is_dir():
                shutil.copytree(src, dst / src.name)
                break
        # Some libs (e.g., chardet) keep tests at the project root.
        for fname in ("test.py", "tests.py"):
            p = original_dir / fname
            if p.is_file():
                shutil.copy2(p, dst / fname)
        # Stage minimal toplevel config that test collection might need.
        for name in ("conftest.py", "pytest.ini", "setup.cfg", "pyproject.toml"):
            p = original_dir / name
            if p.is_file():
                shutil.copy2(p, dst / name)

        # Strip --cov-* flags from staged config so collect doesn't fail
        # on environments without pytest-cov. Same surgical strip Q1 uses.
        _strip_problematic_pytest_flags(dst)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(dst) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

        imp = _import_check(dst, pkg_name, env)
        col = _collect_check(dst, env) if imp["ok"] else {
            "ok": False, "skipped": True, "reason": "import failed"
        }

    first_traceback = ""
    if not imp["ok"]:
        first_traceback = imp["traceback"]
    elif not col.get("ok") and not col.get("skipped"):
        first_traceback = col.get("traceback", "")

    return {
        "ok": imp["ok"] and col.get("ok", False),
        "import": imp,
        "collect": col,
        "package_name": pkg_name,
        "first_traceback": first_traceback,
    }


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--original", type=Path, required=True)
    ap.add_argument("--recomposed", type=Path, required=True)
    args = ap.parse_args()

    result = smoke_test(args.original, args.recomposed)
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["ok"] else 1)
