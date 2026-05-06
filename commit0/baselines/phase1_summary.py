"""Phase 1 sweep summary — quick aggregate across the 4 new (arch x provider) cells.

Run:  python benchmarks/commit0/baselines/phase1_summary.py
"""
from __future__ import annotations

import json
from pathlib import Path

R = Path.home() / "kaizen-commit0" / "baselines" / "results"

CELLS = [
    ("aider/anthropic", "aggregate_lite_aider_anthropic.json"),
    ("aider/openai",    "aggregate_lite_aider_openai.json"),
    ("smol/anthropic",  "aggregate_lite_smolagents_anthropic.json"),
    ("smol/openai",     "aggregate_lite_smolagents_openai.json"),
]


def main() -> None:
    print(f"{'cell':<18} {'libs':>4} {'pass':>5} {'att':>5} {'rate':>7} {'cost':>9} {'wall_min':>9}")
    print("-" * 70)
    total_cost = 0.0
    for label, fname in CELLS:
        p = R / fname
        if not p.exists():
            print(f"{label:<18}  (not found: {fname})")
            continue
        d = json.loads(p.read_text())
        a = d["aggregate"]
        total_cost += a["cost_usd_total"]
        rate = a["pass_rate_attempted"] * 100
        wall_min = a["wall_seconds_total"] / 60
        print(
            f"{label:<18} {a['libraries_total']:>4} "
            f"{a['tests_passed']:>5} {a['tests_attempted_total']:>5} "
            f"{rate:>6.1f}% ${a['cost_usd_total']:>6.2f} {wall_min:>8.1f}"
        )
    print(f"\nTotal Phase 1 compute: ${total_cost:.2f}\n")

    # Per-lib wall-time outliers per cell
    for label, fname in CELLS:
        p = R / fname
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        libs = [(name, lib.get("elapsed_s", 0)) for name, lib in d["per_library"].items()]
        libs.sort(key=lambda x: -x[1])
        print(f"{label} top-3 longest libs:")
        for name, sec in libs[:3]:
            print(f"  {name:<14} {sec/60:>5.1f} min")
        print()


if __name__ == "__main__":
    main()
