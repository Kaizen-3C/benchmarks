"""Patch-based measurement-reproducibility check ($0 LLM; Docker only).

The faithful, contamination-proof verifier and the one an EXTERNAL reviewer uses: for
each cell, apply its committed per-provider patch.diff onto a clean `commit0` checkout,
score the resulting branch, and diff against the published counts. Unlike branch-based
verification (verify_artifacts.py), this is correct for aider / smolagents / kaizen_delta
whose runners share ONE branch name across both providers (so the branch only holds the
last-run provider's code). The per-cell patch is provider-specific.

Patches must be extracted to --patches-dir (they live in the data PR; see the runner that
calls `git archive data/phase1-result-patches`). Runs in the WSL workspace.

Usage (in WSL):
    python baselines/verify_patches.py --results-dir /mnt/c/.../commit0/results \
        --patches-dir /tmp/kd_patches/commit0/results/patches --out /mnt/c/.../.git/verify_patches.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent / "sampling"))
import score_branch as sb  # noqa: E402

WORKSPACE = Path.home() / "kaizen-commit0"
KEYS = ("passed", "failed", "errors")
# generous per-lib timeouts so big suites don't time out into a false 0/0/0
TIMEOUT = {"babel": 2400, "marshmallow": 1800, "jinja": 1800, "parsel": 1200,
           "chardet": 1200, "cookiecutter": 1200}
DEFAULT_TIMEOUT = 900
VERIFY_BRANCH = "_verify_patch"


def counts_of(d: dict):
    c = d.get("final_counts") or d.get("counts")
    if c is None:
        c = d if any(k in d for k in ("passed", "failed", "errors")) else None
    return {k: int((c or {}).get(k, 0) or 0) for k in ("passed", "failed", "skipped", "errors")} if c else None


def recorded(results: Path, cell: str):
    f = results / f"{cell}.json"
    return counts_of(json.loads(f.read_text(encoding="utf-8"))) if f.exists() else None


def _normalize(patch: Path) -> Path:
    """Committed patches carry Windows CRLF + no trailing newline, which makes
    `git apply` report 'corrupt patch'. Normalize to LF + trailing newline so the
    artifact applies (the export should be fixed too; see PR #4)."""
    raw = patch.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if not raw.endswith(b"\n"):
        raw += b"\n"
    tmp = Path("/tmp") / (patch.stem + ".norm.patch")
    tmp.write_bytes(raw)
    return tmp


def apply_and_score(lib: str, patch: Path):
    """Apply patch onto clean commit0 -> VERIFY_BRANCH, score full-suite. Returns (counts|None, note)."""
    repo = WORKSPACE / "repos" / lib
    if patch.stat().st_size == 0:
        # Empty patch = agent produced no applyable change -> the cell scores the commit0
        # baseline (a 0-byte file is not a valid diff). Score the baseline branch directly.
        sc = sb.score_branch(lib, "commit0", commit=False, timeout_s=TIMEOUT.get(lib, DEFAULT_TIMEOUT))
        return sc["counts"], "empty->baseline"
    sb._git(repo, "checkout", "-f", "commit0")
    sb._git(repo, "clean", "-fd")
    sb._git(repo, "checkout", "-B", VERIFY_BRANCH, "commit0")
    np = _normalize(patch)
    applied = False
    for args in (["git", "apply", "--recount", "--whitespace=nowarn", str(np)],
                 ["git", "apply", "--3way", "--recount", "--whitespace=nowarn", str(np)]):
        if subprocess.run(args, cwd=repo, capture_output=True, text=True).returncode == 0:
            applied = True
            break
    if not applied:  # GNU patch fallback (more lenient)
        r = subprocess.run(["patch", "-p1", "--no-backup-if-mismatch", "-i", str(np)],
                           cwd=repo, capture_output=True, text=True)
        if r.returncode != 0:
            return None, f"APPLY-FAIL: {(r.stderr or r.stdout or '').strip()[:100]}"
    sb._git(repo, "add", "-A")
    sb._git(repo, "commit", "--allow-empty", "-m", f"{VERIFY_BRANCH} {lib}")
    sc = sb.score_branch(lib, VERIFY_BRANCH, commit=False,
                         timeout_s=TIMEOUT.get(lib, DEFAULT_TIMEOUT))
    return sc["counts"], None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--patches-dir", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", nargs="*", default=[], help="limit to these cell stems")
    a = ap.parse_args()
    results, pdir = Path(a.results_dir), Path(a.patches_dir)

    patches = sorted(pdir.glob("*.patch"))
    if a.only:
        patches = [p for p in patches if p.stem in set(a.only)]
    print(f"verify_patches: {len(patches)} patch(es) from {pdir}")
    print(f"{'cell':40s} {'recorded(p/f/e)':16s} {'fresh(p/f/e)':16s} status")
    match = mismatch = err = 0
    rows = []
    for patch in patches:
        cell = patch.stem                       # {lib}_{arch}_{provider}
        lib = cell.split("_")[0]                 # refined against the known 16-lib set below
        for cand in ["wcwidth","deprecated","cachetools","voluptuous","portalocker","pyjwt",
                     "chardet","tinydb","simpy","imapclient","parsel","marshmallow",
                     "cookiecutter","babel","jinja","minitorch"]:
            if cell.startswith(cand + "_"):
                lib = cand; break
        rec = recorded(results, cell)
        row = {"cell": cell, "lib": lib, "recorded": rec}
        try:
            fresh, note = apply_and_score(lib, patch)
        except Exception as e:
            fresh, note = None, f"ERROR: {e}"
        if fresh is None:
            err += 1; row["status"] = note
            print(f"{cell:40s} {'-':16s} {'-':16s} {note}"); rows.append(row); continue
        row["fresh"] = fresh
        rs = "-" if rec is None else f"{rec['passed']}/{rec['failed']}/{rec['errors']}"
        fs = f"{fresh['passed']}/{fresh['failed']}/{fresh['errors']}"
        if rec is None:
            status = "NO-RECORDED"
        elif all(fresh[k] == rec[k] for k in KEYS):
            status = "MATCH"; match += 1
        else:
            status = "MISMATCH"; mismatch += 1
        row["status"] = status
        print(f"{cell:40s} {rs:16s} {fs:16s} {status}"); rows.append(row)

    # clean up the temp branch
    print("\n" + "=" * 60)
    print(f"SUMMARY: {match} match | {mismatch} mismatch | {err} apply-fail/error")
    if a.out:
        Path(a.out).write_text(json.dumps(
            {"match": match, "mismatch": mismatch, "error": err, "rows": rows}, indent=2))
        print(f"wrote report: {a.out}")
    return 1 if (mismatch or err) else 0


if __name__ == "__main__":
    raise SystemExit(main())
