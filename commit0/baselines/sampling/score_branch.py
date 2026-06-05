"""Shared, noise-safe, full-suite branch scoring for the sampling re-test.

This is the consolidation the benchmarks-delta harness review recommended (testing
fixes T1-T4, T7), applied here so every rep is scored identically and robustly:

  T1  strip agent noise (.aider*, spec.md, __pycache__) BEFORE `git add -A` so the
      branch patch the container applies is clean code only (binary noise silently
      scores the BASELINE otherwise).
  T2  always score the FULL suite via `commit0 test --branch` (never `pytest -x`).
  T3  retry on a 0/0/0 collection race AND on a sharp collected-count drop vs the
      cell's own high-water mark (the partial-collapse race the single-runner guard
      missed).
  T4  select the result by a pre-run mtime WATERMARK (a strictly-newer log dir),
      not "latest mtime", so a concurrent run can't be scored by mistake.
  T7  one counts parser; separate `errors` (collection) from `failed` (per-test).

Runs on the WSL host (needs the commit0 CLI + Docker). Pure scoring — no LLM.
"""
from __future__ import annotations
import re, shutil, subprocess, time
from pathlib import Path

WORKSPACE = Path.home() / "kaizen-commit0"
# commit0 test-dir per lib (libs not listed default to "tests")
TEST_DIR_OVERRIDES = {"voluptuous": "voluptuous/tests", "chardet": ".",
                      "portalocker": "portalocker_tests/"}
_SUMMARY_RE = re.compile(
    r"(\d+)\s+(passed|failed|skipped|error[s]?|xfailed|xpassed|deselected)", re.I)

def _git(repo: Path, *a, check: bool = True):
    """Run a git command. Fail fast on error (with stderr) unless check=False.

    Silently swallowing a failed `git add`/`commit` would let `commit0 test
    --branch` score an unintended state (including the BASELINE) with no signal —
    the exact mis-scoring this module exists to prevent.
    """
    r = subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(a)} failed in {repo} (exit {r.returncode}): "
            f"{(r.stderr or r.stdout).strip()}")
    return r.stdout

def _strip_noise(repo: Path):  # T1
    for n in list(repo.glob(".aider*")) + [repo / "spec.md"]:
        if n.is_dir():
            shutil.rmtree(n, ignore_errors=True)
        elif n.exists():
            n.unlink()
    for pyc in repo.rglob("__pycache__"):
        shutil.rmtree(pyc, ignore_errors=True)

def _parse(summary: str) -> dict:  # T7: one parser; errors (collection) kept separate
    c = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for n, kind in _SUMMARY_RE.findall(summary or ""):
        k = kind.lower()
        if k.startswith("error"):
            c["errors"] = int(n)
        elif k in c:               # passed/failed/skipped (xfailed/xpassed/deselected ignored)
            c[k] = int(n)
    return c

def _collected(c: dict) -> int:
    return c["passed"] + c["failed"] + c["errors"]

def _newest_after(log_root: Path, watermark: set) -> Path | None:  # T4
    if not log_root.is_dir():
        return None
    dirs = [d for d in log_root.iterdir() if d.is_dir() and str(d) not in watermark]
    if not dirs:
        return None
    return max(dirs, key=lambda d: d.stat().st_mtime)

def score_branch(lib: str, branch: str, repo_dir: Path | None = None,
                 test_dir: str | None = None, retries: int = 3, backoff_s: float = 3.0,
                 strip_noise: bool = True, commit: bool = True) -> dict:
    """Score `branch` for `lib` on the FULL suite, robustly. Returns a dict with
    counts, collected, rate, scoring tag, summary, attempts, and `baseline_suspect`."""
    repo_dir = repo_dir or (WORKSPACE / "repos" / lib)
    test_dir = test_dir or TEST_DIR_OVERRIDES.get(lib, "tests")
    log_root = WORKSPACE / "logs" / "pytest" / lib / branch

    if commit:
        if strip_noise:
            _strip_noise(repo_dir)            # T1
        _git(repo_dir, "add", "-A")
        _git(repo_dir, "commit", "--allow-empty", "-m", f"sampling score: {branch}")

    high_water = 0
    best = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    summary = ""
    attempts = 0
    for attempt in range(retries + 1):
        attempts = attempt + 1
        watermark = {str(d) for d in log_root.iterdir()} if log_root.is_dir() else set()  # T4
        subprocess.run(["commit0", "test", lib, test_dir, "--branch", branch,
                        "--backend", "local", "--timeout", "600"],
                       cwd=WORKSPACE, capture_output=True, text=True)            # T2 (no -x)
        run_dir = _newest_after(log_root, watermark)
        if run_dir is None:
            time.sleep(backoff_s); continue
        out = (run_dir / "test_output.txt")
        text = out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""
        line = next((l for l in reversed(text.splitlines()) if _SUMMARY_RE.search(l)), "")
        counts = _parse(line)
        coll = _collected(counts)
        if coll > high_water:
            high_water, best, summary = coll, counts, line
        # T3: accept if we collected something AND not a sharp drop vs high-water
        if coll > 0 and coll >= 0.5 * high_water:
            best, summary = counts, line
            break
        if attempt < retries:
            time.sleep(backoff_s)   # 0/0/0 or partial-collapse race -> retry

    coll = _collected(best)
    return {
        "counts": best, "collected": coll,
        "rate": (best["passed"] / coll) if coll else 0.0,
        "scoring": "commit0-test-full-suite" if coll > 0 else "no-summary",
        "summary": summary, "attempts": attempts,
        "collection_gated": best["errors"] > 0 and (best["passed"] + best["failed"]) == 0,
        # heuristic: a clean run that collected nothing is a suspected race/baseline-fallback
        "baseline_suspect": coll == 0,
    }
