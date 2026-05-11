"""Run smoke_test against an existing rerun directory's recomposed/ outputs.

Zero LLM cost. Categorizes each library's failure mode:

  - import_ok=True, collect_ok=True   -> would-have-passed-collection
  - import_ok=True, collect_ok=False  -> collection failure (test-side)
  - import_ok=False                    -> package import failure
                                          (the named ceiling)

Compares against Q1 to surface where smoke and Q1 disagree.

Usage:
    python benchmarks/round_trip/smoke_ablation.py \\
        --rerun-dir <path/to/2026-05-07_phase-A-runnable-spec> \\
        --repos-root //wsl.localhost/Ubuntu-24.04/home/aadame/kaizen-commit0/repos
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from smoke_test import smoke_test  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rerun-dir", type=Path, required=True)
    ap.add_argument("--repos-root", type=Path, required=True)
    ap.add_argument("--write", action="store_true",
                    help="Write smoke_ablation.json into the rerun dir.")
    args = ap.parse_args()

    recomposed_dir = args.rerun_dir / "recomposed"
    results_dir = args.rerun_dir / "results"
    if not recomposed_dir.is_dir():
        print(f"missing: {recomposed_dir}", file=sys.stderr)
        return 2

    libs = sorted(d.name for d in recomposed_dir.iterdir() if d.is_dir())
    rows: list[dict] = []
    counts = {
        "import_fail": 0, "collect_fail": 0, "smoke_ok": 0,
        "smoke_ok_q1_zero": 0, "smoke_fail_q1_pos": 0,
    }

    for lib in libs:
        original_dir = args.repos_root / lib
        recomp = recomposed_dir / lib
        if not original_dir.is_dir():
            rows.append({"lib": lib, "skip": "original missing"})
            continue
        s = smoke_test(original_dir, recomp)

        # Pull Q1 from the existing results JSON for comparison.
        q1: float | None = None
        rj = results_dir / f"{lib}_round_trip.json"
        if rj.is_file():
            try:
                q1 = (json.loads(rj.read_text(encoding="utf-8"))
                      .get("metrics", {})
                      .get("q1_test_parity", {})
                      .get("value"))
            except (OSError, json.JSONDecodeError):
                pass

        category = (
            "import_fail" if not s["import"]["ok"]
            else "collect_fail" if not s["collect"].get("ok")
            else "smoke_ok"
        )
        counts[category] += 1
        if category == "smoke_ok" and q1 == 0:
            counts["smoke_ok_q1_zero"] += 1
        if category != "smoke_ok" and isinstance(q1, float) and q1 > 0:
            counts["smoke_fail_q1_pos"] += 1

        rows.append({
            "lib": lib,
            "package_name": s.get("package_name"),
            "category": category,
            "import_ok": s["import"]["ok"],
            "collect_ok": s["collect"].get("ok"),
            "q1": q1,
            "first_traceback_head": s.get("first_traceback", "")[:240],
        })

    # Print human-readable table.
    print(f"{'lib':14} {'pkg':14} {'category':14} {'import':>6} {'collect':>7}  {'Q1':>5}")
    print("-" * 78)
    for r in rows:
        if "skip" in r:
            print(f"{r['lib']:14} -             SKIP ({r['skip']})")
            continue
        q1 = f"{r['q1']:.3f}" if isinstance(r["q1"], float) else "  -  "
        print(f"{r['lib']:14} {(r['package_name'] or '?'):14} "
              f"{r['category']:14} {str(r['import_ok']):>6} "
              f"{str(r['collect_ok']):>7}  {q1:>5}")

    print()
    print("Counts:")
    for k, v in counts.items():
        print(f"  {k:24} {v}")

    if args.write:
        out = args.rerun_dir / "smoke_ablation.json"
        out.write_text(json.dumps({"rows": rows, "counts": counts},
                                  indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
