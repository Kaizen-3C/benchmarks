"""Re-measure Q1 against an existing rerun directory's recomposed/ outputs.

Use after fixing the smoke / test environment (e.g., installing missing test
deps) to get the TRUE Q1 ceiling for that rerun, decoupled from environment
artifacts. Writes a new q1_remeasured.json next to the original results.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from metrics.q1_test_parity import compute  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rerun-dir", type=Path, required=True)
    ap.add_argument("--repos-root", type=Path, required=True)
    ap.add_argument("--write", action="store_true",
                    help="Write q1_remeasured.json into the rerun dir.")
    args = ap.parse_args()

    recomposed_dir = args.rerun_dir / "recomposed"
    libs = sorted(d.name for d in recomposed_dir.iterdir() if d.is_dir())

    rows: list[dict] = []
    print(f"{'lib':14} {'Q1_old':>8} {'Q1_new':>8} {'p/f/e/c':>20}  delta")
    print("-" * 70)

    for lib in libs:
        original = args.repos_root / lib
        recomp = recomposed_dir / lib

        old_q1 = None
        rj = args.rerun_dir / "results" / f"{lib}_round_trip.json"
        if rj.is_file():
            try:
                old_q1 = (json.loads(rj.read_text(encoding="utf-8"))
                          .get("metrics", {})
                          .get("q1_test_parity", {})
                          .get("value"))
            except (OSError, json.JSONDecodeError):
                pass

        if not original.is_dir():
            print(f"{lib:14} {'-':>8} {'-':>8}  skip (no original)")
            continue

        r = compute(original, recomp)
        new_q1 = r.get("value")
        d = r.get("detail", {})
        pfe = (
            f"{d.get('passed', 0)}/{d.get('failed', 0)}/"
            f"{d.get('errors', 0)}/{d.get('collected', 0)}"
        )
        delta = ""
        if isinstance(old_q1, (int, float)) and isinstance(new_q1, (int, float)):
            d_val = new_q1 - old_q1
            delta = f"{d_val:+.3f}" if abs(d_val) > 0.001 else "  ~"

        print(f"{lib:14} "
              f"{old_q1 if isinstance(old_q1, float) else '-':>8.3f}" if isinstance(old_q1, float) else f"{lib:14} {'-':>8}",
              end=" "
        )
        print(
            f"{new_q1 if isinstance(new_q1, float) else '-':>8.3f}" if isinstance(new_q1, float) else f"{'-':>8}",
            f"{pfe:>20}",
            f" {delta}",
        )
        rows.append({"lib": lib, "old_q1": old_q1, "new_q1": new_q1, "detail": d})

    if args.write:
        out = args.rerun_dir / "q1_remeasured.json"
        out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
        print(f"\nwrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
