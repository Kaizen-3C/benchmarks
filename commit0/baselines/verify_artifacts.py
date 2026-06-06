"""Step-3 measurement-reproducibility check ($0 LLM; Docker pytest only).

Proves the *measurement* reproduces: re-score each committed code branch via
`commit0 test --branch` and diff the fresh pass/fail/error counts against the counts
recorded in the published result JSONs. This is the core evidence for the
"reproducible methodology" claim — anyone can re-derive our numbers from our committed
patches with NO API keys / NO LLM spend — and it adjudicates the open items the matrix
audit surfaced (commit0/AUDIT_FINDINGS.md).

Non-destructive: scores branches with commit=False (never strips/commits the repo).
Runs in the WSL workspace (needs the commit0 CLI + Docker). Compares against the
published counts in --results-dir (point this at the repo's commit0/results via /mnt/c).

Usage (in WSL):
    python baselines/verify_artifacts.py --results-dir /mnt/c/.../commit0/results --only-open
    python baselines/verify_artifacts.py --results-dir ... --cells voluptuous:kaizen_delta_anthropic
    python baselines/verify_artifacts.py --results-dir ... --all        # full matrix (slow)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent / "sampling"))
import score_branch as sb  # noqa: E402  (shared noise-safe scorer; synced to WSL)

LIBS = [
    "wcwidth", "deprecated", "cachetools", "voluptuous", "portalocker",
    "pyjwt", "chardet", "tinydb", "simpy", "imapclient", "parsel",
    "marshmallow", "cookiecutter", "babel", "jinja", "minitorch",
]
SUFFIXES = [
    "aider_anthropic", "aider_openai", "smolagents_anthropic", "smolagents_openai",
    "kaizen_delta_anthropic", "kaizen_delta_openai", "reflexion_sonnet", "reflexion_openai",
    "single_shot_sonnet", "single_shot_openai",
]
# Fast smoke set = the audit's open items (commit0/AUDIT_FINDINGS.md).
OPEN_ITEMS = [
    ("voluptuous", "kaizen_delta_anthropic"),   # aggregate 0% vs standalone 39% (headline)
    ("pyjwt", "single_shot_sonnet"),            # denominator 182 vs ...
    ("pyjwt", "single_shot_openai"),            # ... 259
    ("pyjwt", "kaizen_delta_anthropic"),        # 240
    ("pyjwt", "reflexion_openai"),              # 182
    ("chardet", "smolagents_openai"),           # 394 vs 376
    ("chardet", "reflexion_openai"),            # == baseline (spot-check)
    ("imapclient", "kaizen_delta_anthropic"),   # == baseline (spot-check)
]
KEYS = ("passed", "failed", "errors")  # skipped excluded (varies harmlessly)


def counts_of(d: dict) -> dict | None:
    c = d.get("final_counts") or d.get("counts")
    if c is None:
        if any(k in d for k in ("passed", "failed", "errors")):
            c = d
        else:
            return None
    return {k: int(c.get(k, 0) or 0) for k in ("passed", "failed", "skipped", "errors")}


def recorded(results: Path, lib: str, suffix: str):
    """Return (branch, counts) from the published artifacts (standalone, else aggregate)."""
    branch = counts = None
    f = results / f"{lib}_{suffix}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        branch = d.get("code_branch") or d.get("branch")
        counts = counts_of(d)
    if counts is None:
        agg = results / f"aggregate_lite_{suffix}.json"
        if agg.exists():
            pl = (json.loads(agg.read_text(encoding="utf-8")).get("per_library") or {}).get(lib) or {}
            counts = counts_of(pl)
            branch = branch or pl.get("branch")
    return branch, counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", required=True, help="published results dir (e.g. /mnt/c/.../commit0/results)")
    ap.add_argument("--only-open", action="store_true", help="verify just the audit's open items (fast smoke)")
    ap.add_argument("--all", action="store_true", help="verify the full matrix (slow)")
    ap.add_argument("--cells", nargs="*", default=[], help="lib:suffix pairs, e.g. pyjwt:single_shot_openai")
    ap.add_argument("--out", default=None, help="write a JSON report (per-cell rows + summary)")
    a = ap.parse_args()
    results = Path(a.results_dir)

    if a.only_open:
        targets = OPEN_ITEMS
    elif a.cells:
        targets = [tuple(c.split(":", 1)) for c in a.cells]
    elif a.all:
        targets = [(lib, suf) for lib in LIBS for suf in SUFFIXES
                   if (results / f"{lib}_{suf}.json").exists()]
    else:
        print("specify --only-open, --all, or --cells"); return 2

    print(f"verify_artifacts: re-scoring {len(targets)} cell(s) against {results}")
    print(f"{'cell':40s} {'branch':22s} {'recorded(p/f/e)':18s} {'fresh(p/f/e)':18s} status")
    match = mismatch = skipped = 0
    bad: list[str] = []
    rows: list[dict] = []
    for lib, suffix in targets:
        cell = f"{lib}_{suffix}"
        branch, rec = recorded(results, lib, suffix)
        row = {"cell": cell, "lib": lib, "suffix": suffix, "branch": branch, "recorded": rec}
        if not branch:
            print(f"{cell:40s} {'-':22s} {'-':18s} {'-':18s} NO-BRANCH/RECORD"); skipped += 1
            row["status"] = "NO-BRANCH/RECORD"; rows.append(row); continue
        try:
            sc = sb.score_branch(lib, branch, commit=False)
        except Exception as e:
            print(f"{cell:40s} {branch:22s} re-score ERROR: {e}"); bad.append(f"{cell}: {e}"); mismatch += 1
            row["status"] = "ERROR"; row["error"] = str(e); rows.append(row); continue
        fresh = sc["counts"]
        row["fresh"] = fresh
        rstr = "-" if rec is None else f"{rec['passed']}/{rec['failed']}/{rec['errors']}"
        fstr = f"{fresh['passed']}/{fresh['failed']}/{fresh['errors']}"
        if rec is None:
            status = "NO-RECORDED"; skipped += 1
        elif all(fresh[k] == rec[k] for k in KEYS):
            status = "MATCH"; match += 1
        else:
            status = "MISMATCH"; mismatch += 1; bad.append(f"{cell}: recorded {rstr} -> fresh {fstr}")
        row["status"] = status
        print(f"{cell:40s} {branch:22s} {rstr:18s} {fstr:18s} {status}")
        rows.append(row)

    print("\n" + "=" * 60)
    print(f"SUMMARY: {match} match | {mismatch} mismatch | {skipped} skipped/no-record")
    for b in bad:
        print(f"  MISMATCH  {b}")
    if a.out:
        Path(a.out).write_text(json.dumps(
            {"match": match, "mismatch": mismatch, "skipped": skipped, "rows": rows}, indent=2))
        print(f"\nwrote report: {a.out}")
    if mismatch:
        print("\nFAIL: measurement did not reproduce for the cells above.")
        return 1
    print("\nOK: re-scored counts reproduce the published artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
