"""TypeScriptAdapter — Phase C implementation.

Uses npm + tsc + vitest. Test environment requires `node_modules/` to be
populated (the adapter does NOT run `npm install` on every smoke — too
slow). The original repo MUST already have `node_modules/` installed; the
adapter copies that across into the smoke tempdir.

Smoke build = `tsc --noEmit` (typecheck without writing JS).
Smoke collect = `vitest --run --reporter=verbose --listTests` (or the
fallback path: parse `vitest run` output for test counts).
Test run = `vitest run --reporter=json`.
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


_NPX = "npx.cmd" if os.name == "nt" else "npx"


def _read_pkg(pkg_dir: Path) -> dict:
    p = pkg_dir / "package.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_pkg_name(pkg_dir: Path) -> str | None:
    n = _read_pkg(pkg_dir).get("name")
    return n if isinstance(n, str) else None


def _detect_test_runner(pkg_dir: Path) -> str:
    """Pick test runner from package.json devDependencies.

    Order of preference (matches what's most common in modern TS packages):
        vitest > ava > jest > mocha > 'unknown'
    """
    pkg = _read_pkg(pkg_dir)
    devdeps = pkg.get("devDependencies", {})
    deps = pkg.get("dependencies", {})
    all_deps = {**deps, **devdeps}
    for runner in ("vitest", "ava", "jest", "mocha"):
        if runner in all_deps:
            return runner
    return "unknown"


_EXPORT_RE = re.compile(
    r"^export\s+(?:async\s+)?(?P<kind>function|class|interface|type|enum|const|let)\s+"
    r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)",
    re.MULTILINE,
)
_REEXPORT_RE = re.compile(
    r"^export\s*\{\s*(?P<names>[^}]*?)\s*\}",
    re.MULTILINE,
)


class TypeScriptAdapter:
    name = "typescript"
    # Many "TS" packages ship as .js + .d.ts (CommonJS / ESM with type
    # declarations on the side). The adapter handles both.
    file_extensions = (".ts", ".tsx", ".js", ".mjs", ".cjs", ".d.ts")
    package_marker = ("package.json",)

    def detect_package_dir(self, recomposed_dir: Path) -> tuple[Path, str]:
        if (recomposed_dir / "package.json").is_file():
            return recomposed_dir, _read_pkg_name(recomposed_dir) or recomposed_dir.name
        candidates = [
            d for d in recomposed_dir.iterdir()
            if d.is_dir() and (d / "package.json").is_file()
        ]
        if len(candidates) == 1:
            return candidates[0], _read_pkg_name(candidates[0]) or candidates[0].name
        return recomposed_dir, recomposed_dir.name

    def public_symbols(self, package_dir: Path, test_scoped: bool = True
                        ) -> list[dict]:
        out: list[dict] = []
        src = package_dir / "src"
        scan_root = src if src.is_dir() else package_dir
        for ts in sorted(scan_root.rglob("*.ts")):
            if "node_modules" in ts.parts or "tests" in ts.parts:
                continue
            try:
                text = ts.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = ts.read_bytes().decode("latin-1", errors="replace")
            for m in _EXPORT_RE.finditer(text):
                line = text[: m.start()].count("\n") + 1
                out.append({
                    "name": m.group("name"),
                    "kind": m.group("kind"),
                    "module": ts.relative_to(scan_root).with_suffix("").as_posix(),
                    "source": f"{ts.relative_to(package_dir).as_posix()}:{line}",
                })
            for m in _REEXPORT_RE.finditer(text):
                names_block = m.group("names")
                line = text[: m.start()].count("\n") + 1
                for name in re.split(r"[,\s]+", names_block):
                    name = name.strip()
                    if not name or name == "default":
                        continue
                    # `Foo as Bar` -> use Bar
                    if " as " in name:
                        name = name.split(" as ")[-1].strip()
                    out.append({
                        "name": name,
                        "kind": "reexport",
                        "module": ts.relative_to(scan_root).with_suffix("").as_posix(),
                        "source": f"{ts.relative_to(package_dir).as_posix()}:{line}",
                    })
        return out

    def _stage(self, original_dir: Path, recomposed_dir: Path,
                td: Path) -> tuple[Path, str]:
        """Stage the recomposed package + the original tests + node_modules.

        node_modules is referenced from the original via a symlink-like
        directory junction on Windows (or copytree as a fallback). Vitest
        and tsc both work fine with that.
        """
        pkg_src, pkg_name = self.detect_package_dir(recomposed_dir)
        dst = td / pkg_name
        shutil.copytree(pkg_src, dst, ignore=shutil.ignore_patterns(
            "node_modules", "dist", ".cache", ".vite",
        ))
        # Tests come from the canonical original (round-trip rule).
        for tname in ("tests", "__tests__", "test"):
            ts_src = original_dir / tname
            if ts_src.is_dir():
                td_dst = dst / tname
                if td_dst.is_dir():
                    shutil.rmtree(td_dst)
                shutil.copytree(ts_src, td_dst)
                break
        # Some packages (e.g., string-width) keep tests at the project root:
        # `test.js`, `tests.js`, or `*.test.{js,ts}` / `*.spec.{js,ts}`.
        root_test_patterns = ("test.js", "test.ts", "tests.js", "tests.ts")
        for fname in root_test_patterns:
            p = original_dir / fname
            if p.is_file():
                shutil.copy2(p, dst / fname)
        # Glob for *.test.{js,ts} and *.spec.{js,ts} at root.
        for f in original_dir.iterdir():
            if not f.is_file():
                continue
            n = f.name
            if (n.endswith(".test.js") or n.endswith(".test.ts")
                    or n.endswith(".spec.js") or n.endswith(".spec.ts")):
                shutil.copy2(f, dst / n)
        # Bring node_modules across — required for tsc + vitest.
        nm_src = original_dir / "node_modules"
        if nm_src.is_dir():
            try:
                # On Windows, mklink /J creates a directory junction (cheap).
                if os.name == "nt":
                    os.system(f'mklink /J "{dst / "node_modules"}" "{nm_src}" >NUL 2>&1')
                else:
                    os.symlink(nm_src, dst / "node_modules")
                if not (dst / "node_modules").exists():
                    raise OSError("link failed")
            except OSError:
                shutil.copytree(nm_src, dst / "node_modules")
        return dst, pkg_name

    def smoke_check(self, original_dir: Path, recomposed_dir: Path) -> dict:
        with tempfile.TemporaryDirectory(prefix="smoke_ts_") as td:
            try:
                dst, pkg_name = self._stage(original_dir, recomposed_dir, Path(td))
            except Exception as e:
                return {
                    "ok": False,
                    "build": {"ok": False, "traceback": f"staging failed: {e}"},
                    "collect": {"ok": False, "skipped": True, "reason": "staging failed"},
                    "first_traceback": str(e),
                    "package_name": recomposed_dir.name,
                }

            env = os.environ.copy()
            env.setdefault("CI", "true")
            env.setdefault("NO_COLOR", "1")

            # Build = tsc --noEmit  (skipped for pure-JS packages with no tsconfig)
            if (dst / "tsconfig.json").is_file():
                rc, out = run_subprocess(
                    [_NPX, "--no-install", "tsc", "--noEmit"],
                    cwd=dst, env=env, timeout=120.0,
                )
                build = {
                    "ok": rc == 0, "returncode": rc,
                    "traceback": out[-2000:] if rc != 0 else "",
                }
            else:
                build = {"ok": True, "skipped": True,
                          "reason": "no tsconfig.json (pure JS package)",
                          "returncode": 0, "traceback": ""}
            if not build["ok"]:
                return {
                    "ok": False, "build": build,
                    "collect": {"ok": False, "skipped": True, "reason": "build failed"},
                    "first_traceback": build["traceback"],
                    "package_name": pkg_name,
                }

            # Collect — runner-aware. Detect from package.json then dispatch.
            runner = _detect_test_runner(dst)
            rc, out, counts = _run_tests_with(runner, dst, env, timeout=180.0)
            collected_ok = (counts["passed"] + counts["failed"]) > 0
            collect = {
                "ok": collected_ok,
                "returncode": rc,
                "traceback": out[-2000:] if not collected_ok else "",
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
        with tempfile.TemporaryDirectory(prefix="q1_ts_") as td:
            dst, pkg_name = self._stage(original_dir, recomposed_dir, Path(td))
            env = os.environ.copy()
            env.setdefault("CI", "true")
            env.setdefault("NO_COLOR", "1")
            runner = _detect_test_runner(dst)
            rc, out, counts = _run_tests_with(runner, dst, env, timeout=timeout)
            attempted = counts["passed"] + counts["failed"]
            value = counts["passed"] / attempted if attempted else 0.0
            return {
                "metric": "q1_test_parity",
                "value": round(value, 4),
                "detail": {
                    "passed": counts["passed"],
                    "failed": counts["failed"],
                    "skipped": counts["skipped"],
                    "errors": 0,
                    "collected": attempted,
                    "test_suite_executed": attempted > 0,
                    "test_runner": runner,
                    "returncode": rc,
                    "output_tail": out[-1500:],
                    "package_name": pkg_name,
                },
            }

    def stage_test_environment(self, original_dir: Path, dst: Path) -> dict:
        return {"note": "TypeScriptAdapter stages inside smoke_check / run_tests"}

    def attribute_chains_in_tests(self, original_dir: Path, pkg_root: str
                                    ) -> set[tuple[str, str]]:
        return set()  # phase C deferral


# Vitest summary lines like:
#   "Tests  10 passed (10)"  /  "Tests  3 failed | 7 passed (10)"
_VT_TESTS_LINE = re.compile(
    r"Tests\s+(?:(?P<failed>\d+)\s+failed\s*\|\s*)?"
    r"(?:(?P<passed>\d+)\s+passed\s*)?"
    r"(?:\|\s*(?P<skipped>\d+)\s+skipped\s*)?"
    r"\((?P<total>\d+)\)",
    re.IGNORECASE,
)


def _parse_vitest_summary(output: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    text = strip_ansi(output)
    for m in _VT_TESTS_LINE.finditer(text):
        if m.group("passed"):
            counts["passed"] = max(counts["passed"], int(m.group("passed")))
        if m.group("failed"):
            counts["failed"] = max(counts["failed"], int(m.group("failed")))
        if m.group("skipped"):
            counts["skipped"] = max(counts["skipped"], int(m.group("skipped")))
    return counts


# ava with --tap output:
#   ok 1 - test name
#   not ok 2 - other test
#   1..N
#   # tests N
#   # pass M
#   # fail K
_AVA_OK_RE = re.compile(r"^ok\s+\d+", re.MULTILINE)
_AVA_NOT_OK_RE = re.compile(r"^not ok\s+\d+", re.MULTILINE)
_AVA_PASS_LINE = re.compile(r"^#\s*pass\s+(\d+)\s*$", re.MULTILINE)
_AVA_FAIL_LINE = re.compile(r"^#\s*fail\s+(\d+)\s*$", re.MULTILINE)
_AVA_SKIP_LINE = re.compile(r"^#\s*skip\s+(\d+)\s*$", re.MULTILINE)


def _parse_ava_summary(output: str) -> dict[str, int]:
    text = strip_ansi(output)
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    pm = _AVA_PASS_LINE.search(text)
    fm = _AVA_FAIL_LINE.search(text)
    sm = _AVA_SKIP_LINE.search(text)
    if pm or fm or sm:
        if pm:
            counts["passed"] = int(pm.group(1))
        if fm:
            counts["failed"] = int(fm.group(1))
        if sm:
            counts["skipped"] = int(sm.group(1))
        return counts
    # Fall back to counting `ok` / `not ok` lines (handles tap-without-summary).
    counts["passed"] = len(_AVA_OK_RE.findall(text))
    counts["failed"] = len(_AVA_NOT_OK_RE.findall(text))
    return counts


def _run_tests_with(runner: str, dst: Path, env: dict, timeout: float
                     ) -> tuple[int, str, dict[str, int]]:
    """Dispatch to the right runner. Returns (rc, output, counts)."""
    if runner == "vitest":
        rc, out = run_subprocess(
            [_NPX, "--no-install", "vitest", "run",
             "--reporter=default", "--no-color"],
            cwd=dst, env=env, timeout=timeout,
        )
        return rc, out, _parse_vitest_summary(out)
    if runner == "ava":
        rc, out = run_subprocess(
            [_NPX, "--no-install", "ava", "--tap"],
            cwd=dst, env=env, timeout=timeout,
        )
        return rc, out, _parse_ava_summary(out)
    if runner == "jest":
        rc, out = run_subprocess(
            [_NPX, "--no-install", "jest", "--ci", "--colors=false"],
            cwd=dst, env=env, timeout=timeout,
        )
        # Jest emits "Tests:  X passed, Y failed, Z total"
        text = strip_ansi(out)
        m = re.search(
            r"Tests:\s*(?:(\d+)\s+failed,\s*)?(?:(\d+)\s+passed,?\s*)?"
            r"(?:(\d+)\s+skipped,?\s*)?(\d+)\s+total",
            text,
        )
        counts = {"passed": 0, "failed": 0, "skipped": 0}
        if m:
            counts["failed"] = int(m.group(1) or 0)
            counts["passed"] = int(m.group(2) or 0)
            counts["skipped"] = int(m.group(3) or 0)
        return rc, out, counts
    # unknown runner — try `npm test` and parse defensively.
    rc, out = run_subprocess(
        ["npm", "test", "--", "--no-color"],
        cwd=dst, env=env, timeout=timeout,
    )
    counts = _parse_vitest_summary(out)
    if counts["passed"] + counts["failed"] == 0:
        counts = _parse_ava_summary(out)
    return rc, out, counts


register(TypeScriptAdapter())
