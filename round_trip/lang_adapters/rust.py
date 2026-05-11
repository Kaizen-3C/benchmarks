"""RustAdapter — Phase C implementation.

Uses cargo's machine-readable output for build/test signals:
  - `cargo check --message-format=json` for build/typecheck
  - `cargo test --no-run --message-format=json` for test compilation
  - `cargo test --no-fail-fast --format json -Z unstable-options` for runs
    (or scrape stable text output as fallback).

Public-symbol enumeration uses regex on lib.rs (good enough for Phase C;
upgrade to `cargo public-api` later).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from lang_adapter import LangAdapter, register, run_subprocess, strip_ansi  # noqa: E402


_PUB_RE = re.compile(
    r"^pub\s+(?:async\s+)?(?P<kind>fn|struct|enum|trait|mod|const|static|type|union)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)


def _read_crate_name(crate_dir: Path) -> str | None:
    """Pull `name = "..."` from Cargo.toml [package] section."""
    cargo = crate_dir / "Cargo.toml"
    if not cargo.is_file():
        return None
    try:
        text = cargo.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = re.search(
        r"\[package\][^\[]*?\bname\s*=\s*\"(?P<n>[^\"]+)\"",
        text, re.DOTALL,
    )
    return m.group("n") if m else None


class RustAdapter:
    name = "rust"
    file_extensions = (".rs",)
    package_marker = ("Cargo.toml",)

    def detect_package_dir(self, recomposed_dir: Path) -> tuple[Path, str]:
        # Single-crate case: recomposed_dir IS the crate root.
        if (recomposed_dir / "Cargo.toml").is_file():
            name = _read_crate_name(recomposed_dir) or recomposed_dir.name
            return recomposed_dir, name
        # Workspace / nested case: pick the unique subdir with Cargo.toml.
        candidates = [
            d for d in recomposed_dir.iterdir()
            if d.is_dir() and (d / "Cargo.toml").is_file()
        ]
        if len(candidates) == 1:
            d = candidates[0]
            return d, _read_crate_name(d) or d.name
        return recomposed_dir, recomposed_dir.name

    def public_symbols(self, package_dir: Path, test_scoped: bool = True
                        ) -> list[dict]:
        """Regex-scan src/**/*.rs for `pub <kind> <name>`. test_scoped is a
        no-op for Rust right now — we surface all public items.
        """
        out: list[dict] = []
        src = package_dir / "src"
        if not src.is_dir():
            return out
        for rs in sorted(src.rglob("*.rs")):
            try:
                text = rs.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = rs.read_bytes().decode("latin-1", errors="replace")
            for m in _PUB_RE.finditer(text):
                line = text[: m.start()].count("\n") + 1
                out.append({
                    "name": m.group("name"),
                    "kind": m.group("kind"),
                    "module": rs.relative_to(src).with_suffix("").as_posix().replace("/", "::"),
                    "source": f"{rs.relative_to(package_dir).as_posix()}:{line}",
                })
        return out

    def smoke_check(self, original_dir: Path, recomposed_dir: Path) -> dict:
        """Stage recomposed crate alongside original tests, run cargo check
        + cargo test --no-run.
        """
        pkg_src, pkg_name = self.detect_package_dir(recomposed_dir)
        if not (pkg_src / "Cargo.toml").is_file():
            return {
                "ok": False,
                "build": {"ok": False, "traceback": "no Cargo.toml in recomposed_dir"},
                "collect": {"ok": False, "skipped": True, "reason": "no build"},
                "first_traceback": "no Cargo.toml in recomposed_dir",
                "package_name": pkg_name,
            }

        with tempfile.TemporaryDirectory(prefix=f"smoke_rs_{pkg_name}_") as td:
            dst = Path(td) / pkg_name
            shutil.copytree(pkg_src, dst)
            # Overwrite the recomposed `tests/` (if any) with the canonical
            # original tests — round-trip rule: tests come from upstream.
            tests_src = original_dir / "tests"
            tests_dst = dst / "tests"
            if tests_src.is_dir():
                if tests_dst.is_dir():
                    shutil.rmtree(tests_dst)
                shutil.copytree(tests_src, tests_dst)

            env = os.environ.copy()
            env.setdefault("CARGO_TERM_COLOR", "never")
            env.setdefault("RUST_BACKTRACE", "0")

            # Build phase: cargo check (faster than full build, fails fast).
            rc, out = run_subprocess(
                ["cargo", "check", "--all-targets", "--message-format=short"],
                cwd=dst, env=env, timeout=180.0,
            )
            build = {
                "ok": rc == 0,
                "returncode": rc,
                "traceback": out[-2000:] if rc != 0 else "",
            }
            if not build["ok"]:
                return {
                    "ok": False,
                    "build": build,
                    "collect": {"ok": False, "skipped": True,
                                "reason": "build failed"},
                    "first_traceback": build["traceback"],
                    "package_name": pkg_name,
                }

            # Test compilation — ensures tests link, doesn't run them.
            rc, out = run_subprocess(
                ["cargo", "test", "--no-run", "--message-format=short"],
                cwd=dst, env=env, timeout=180.0,
            )
            collect = {
                "ok": rc == 0,
                "returncode": rc,
                "traceback": out[-2000:] if rc != 0 else "",
            }

        return {
            "ok": build["ok"] and collect["ok"],
            "build": build,
            "collect": collect,
            "first_traceback": build["traceback"] or collect["traceback"],
            "package_name": pkg_name,
        }

    def run_tests(self, original_dir: Path, recomposed_dir: Path,
                   timeout: float = 300.0) -> dict:
        """Run the canonical tests against the recomposed crate. Returns
        Q1-shaped dict.
        """
        pkg_src, pkg_name = self.detect_package_dir(recomposed_dir)
        with tempfile.TemporaryDirectory(prefix=f"q1_rs_{pkg_name}_") as td:
            dst = Path(td) / pkg_name
            shutil.copytree(pkg_src, dst)
            tests_src = original_dir / "tests"
            tests_dst = dst / "tests"
            if tests_src.is_dir():
                if tests_dst.is_dir():
                    shutil.rmtree(tests_dst)
                shutil.copytree(tests_src, tests_dst)

            env = os.environ.copy()
            env.setdefault("CARGO_TERM_COLOR", "never")

            rc, out = run_subprocess(
                ["cargo", "test", "--no-fail-fast", "--quiet"],
                cwd=dst, env=env, timeout=timeout,
            )
            counts = _parse_cargo_test_summary(out)
            attempted = counts["passed"] + counts["failed"]
            value = counts["passed"] / attempted if attempted else 0.0

            return {
                "metric": "q1_test_parity",
                "value": round(value, 4),
                "detail": {
                    "passed": counts["passed"],
                    "failed": counts["failed"],
                    "ignored": counts["ignored"],
                    "errors": 0,
                    "collected": attempted,
                    "test_suite_executed": attempted > 0,
                    "cargo_returncode": rc,
                    "output_tail": out[-1500:],
                    "package_name": pkg_name,
                },
            }

    def stage_test_environment(self, original_dir: Path, dst: Path) -> dict:
        # Used internally above; for the protocol contract.
        return {"note": "RustAdapter stages inside smoke_check / run_tests"}

    def attribute_chains_in_tests(self, original_dir: Path, pkg_root: str
                                    ) -> set[tuple[str, str]]:
        """Rust trait/method use surfaces — return empty for now. Strict
        typing makes hidden surface less of a problem here.
        """
        return set()


# `<crate> test result: ok. N passed; M failed; K ignored; ...`
_RS_TEST_SUMMARY = re.compile(
    r"test result:\s*\w+\.\s*(\d+)\s+passed;\s*(\d+)\s+failed;\s*(\d+)\s+ignored",
    re.IGNORECASE,
)


def _parse_cargo_test_summary(output: str) -> dict[str, int]:
    """Sum across multiple test binaries (lib + integration tests)."""
    counts = {"passed": 0, "failed": 0, "ignored": 0}
    for m in _RS_TEST_SUMMARY.finditer(strip_ansi(output)):
        counts["passed"] += int(m.group(1))
        counts["failed"] += int(m.group(2))
        counts["ignored"] += int(m.group(3))
    return counts


register(RustAdapter())
