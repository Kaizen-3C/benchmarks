"""Language adapter protocol — separates Python-specific logic from the
round-trip pipeline so the benchmark can run on Rust, TypeScript, Go, etc.

Design intent (per session 2026-05-07): the round-trip thesis is
language-independent (can a spec capture enough intent to rebuild the
code?), but every concrete operation in the pipeline currently assumes
Python: `*.py` glob, `ast.parse`, `pytest --collect-only`, `python -c`,
relative-import resolution. Pulling those behind a `LangAdapter`
protocol lets us:

  1. Run the same architecture against Rust (`cargo check` / `cargo test`)
     and TypeScript (`tsc --noEmit` / `vitest`) in addition to Python.
  2. Cleanly measure the static-spec ceiling per language family — the
     measurement contribution flagged by the 2026-05-07 research brief
     (no existing benchmark separates static-spec ceiling from
     runtime-feedback floor).
  3. Decouple "Python pytest hacks" (cov flag stripping, root test.py
     detection) from the pipeline shape.

Phased plan:
  - Phase A: extract the protocol + ship a PythonAdapter that wraps the
    existing helpers verbatim (no behavior change).
  - Phase B: port smoke_test, q1, code_edit_loop call sites to use the
    adapter.
  - Phase C: stub RustAdapter + TypeScriptAdapter, validate on one tiny
    crate / package each.
  - Phase D: full cross-language sweep, paper-grade comparison.

This file is Phase A: the protocol. Concrete adapters live in
`lang_adapters/<name>.py`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol


class SmokeResult(dict):
    """Shape returned by LangAdapter.smoke_check.

    Required keys:
      ok: bool                      — overall pass
      build: {ok, traceback}        — language's "does it parse / typecheck / import"
      collect: {ok, traceback}      — language's "are there runnable tests"
      first_traceback: str          — actionable error to feed remediation/loop
      package_name: str             — what the language calls the unit
    """


class LangAdapter(Protocol):
    """Interface every language plugin must implement.

    Naming convention: methods are abstract over language but their
    implementations are dialect-specific (`cargo check` vs `python -c`).

    The pipeline calls these methods; it never grep/AST-walks language
    files directly.
    """

    # --- identity -----------------------------------------------------------

    name: str  # "python", "rust", "typescript"
    file_extensions: tuple[str, ...]  # (".py",), (".rs",), (".ts", ".tsx")
    package_marker: tuple[str, ...]  # ("__init__.py",), ("Cargo.toml",), ("package.json",)

    # --- package shape ------------------------------------------------------

    def detect_package_dir(self, recomposed_dir: Path) -> tuple[Path, str]:
        """Return (package_root_dir, importable_package_name).

        Examples:
          Python: recomposed/pyjwt/jwt/__init__.py -> (recomposed/pyjwt/jwt, "jwt")
          Rust:   recomposed/serde/Cargo.toml -> (recomposed/serde, "serde")
          TS:     recomposed/chalk/package.json -> (recomposed/chalk, "chalk")
        """
        ...

    def public_symbols(self, package_dir: Path, test_scoped: bool = True
                        ) -> list[dict]:
        """Enumerate public symbols for the static gates.

        Implementations decide what "public" means in their language
        (Python: top-level non-underscore; Rust: `pub` in lib.rs; TS:
        exports from index.ts). Each symbol dict has at minimum:
          name, kind, module, source ("path.ext:line").
        """
        ...

    # --- runtime checks -----------------------------------------------------

    def smoke_check(self, original_dir: Path, recomposed_dir: Path
                     ) -> SmokeResult:
        """Stage code + run language's import + test-collection check.

        Python: python -c "import X" + pytest --collect-only
        Rust:   cargo check (build) + cargo test --no-run (collection)
        TS:     tsc --noEmit (build) + vitest --listTests (collection)
        """
        ...

    def run_tests(self, original_dir: Path, recomposed_dir: Path,
                   timeout: float = 300.0) -> dict:
        """Actually run the test suite. Returns p/f/e/skipped/collected.

        This is what Q1 calls.
        """
        ...

    # --- test discovery -----------------------------------------------------

    def stage_test_environment(self, original_dir: Path, dst: Path
                                ) -> dict:
        """Lay out the language's test runner expectations into dst.

        Python: copy tests/, conftest.py, pytest.ini, strip cov flags.
        Rust:   copy tests/, Cargo.toml, lockfile.
        TS:     copy __tests__/, vitest.config, tsconfig.

        Returns inventory dict.
        """
        ...

    def attribute_chains_in_tests(self, original_dir: Path,
                                    pkg_root: str) -> set[tuple[str, str]]:
        """For dynamic_intent — tests that reach `pkg.submod.attr`.

        Python: AST walk for Attribute nodes rooted in package imports.
        Rust:   typically NOT needed (use sites are typed; less hidden).
        TS:     similar to Python.

        Returns set of (module, attribute_chain) pairs.
        """
        ...


# ---------------------------------------------------------------------------
# Helpers shared across adapters (subprocess execution, ANSI stripping).
# ---------------------------------------------------------------------------

import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def run_subprocess(cmd: list[str], cwd: Path, env: dict | None = None,
                    timeout: float = 120.0) -> tuple[int, str]:
    """Run cmd, return (returncode, combined_output)."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=env or os.environ.copy(),
            capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return 124, f"TIMEOUT after {timeout}s: {e}"
    out = (proc.stdout + proc.stderr).decode(errors="replace")
    return proc.returncode, strip_ansi(out)


# ---------------------------------------------------------------------------
# Adapter registry — populated by lang_adapters/<name>.py modules.
# ---------------------------------------------------------------------------

_ADAPTERS: dict[str, LangAdapter] = {}


def register(adapter: LangAdapter) -> None:
    _ADAPTERS[adapter.name] = adapter


def get(name: str) -> LangAdapter:
    if name not in _ADAPTERS:
        raise KeyError(
            f"no adapter for language {name!r}; "
            f"known: {sorted(_ADAPTERS)}"
        )
    return _ADAPTERS[name]


def detect_from_repo(original_dir: Path) -> str:
    """Heuristic: pick a language adapter from the repo's marker files.

    Order: cargo > package.json > python (default).
    """
    if (original_dir / "Cargo.toml").is_file():
        return "rust"
    if (original_dir / "package.json").is_file():
        return "typescript"
    return "python"
