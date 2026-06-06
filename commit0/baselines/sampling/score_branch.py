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

def _newest_since(log_root: Path, t0: float) -> Path | None:  # T4: mtime watermark
    """Run dir written by THIS run = the one whose test_output.txt mtime >= t0.

    Uses an mtime watermark (a timestamp), NOT a path set. commit0 names each log dir by
    a content HASH and REUSES it for identical code, so a 'strictly-new dir' path-set check
    never sees a re-scored unchanged branch (it returns None -> 0/0/0). That broke the
    verification path and would also zero-out any sampling rep that regenerates identical
    code. mtime-based selection handles both new and reused dirs and matches this module's
    documented intent.
    """
    if not log_root.is_dir():
        return None
    cands = []
    for d in log_root.iterdir():
        if not d.is_dir():
            continue
        out = d / "test_output.txt"
        m = out.stat().st_mtime if out.exists() else d.stat().st_mtime
        if m >= t0 - 1.0:   # 1s slack for clock skew
            cands.append((m, d))
    return max(cands)[1] if cands else None

def score_branch(lib: str, branch: str, repo_dir: Path | None = None,
                 test_dir: str | None = None, retries: int = 3, backoff_s: float = 3.0,
                 strip_noise: bool = True, commit: bool = True, timeout_s: int = 600) -> dict:
    """Score `branch` for `lib` on the FULL suite, robustly. Returns a dict with
    counts, collected, rate, scoring tag, summary, attempts, and `baseline_suspect`."""
    repo_dir = repo_dir or (WORKSPACE / "repos" / lib)
    test_dir = test_dir or TEST_DIR_OVERRIDES.get(lib, "tests")
    log_root = WORKSPACE / "logs" / "pytest" / lib / branch

    if commit:
        # Ensure HEAD is the branch we are about to commit to AND score. Otherwise we
        # would commit the working tree onto the wrong ref (and strip noise from the
        # wrong tree) while `commit0 test --branch <branch>` scores the stale target
        # branch — the silent mis-scoring this module exists to prevent. _git fails
        # fast (check=True), so a dirty-tree checkout conflict raises rather than
        # mis-scoring.
        cur = _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD").strip()
        if cur != branch:
            _git(repo_dir, "checkout", branch)
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
        # Remove any orphaned eval container first: a leftover `commit0.eval.<lib>` (from a
        # killed/timed-out prior run) makes commit0 fail with a 409 name-conflict in ~3s,
        # producing a false 0/0/0. Self-heal so verification is robust.
        subprocess.run(["docker", "rm", "-f", f"commit0.eval.{lib}"],
                       capture_output=True, text=True)
        t0 = time.time()                                                        # T4 mtime watermark
        subprocess.run(["commit0", "test", lib, test_dir, "--branch", branch,
                        "--backend", "local", "--timeout", str(timeout_s)],
                       cwd=WORKSPACE, capture_output=True, text=True)            # T2 (no -x)
        run_dir = _newest_since(log_root, t0)
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
