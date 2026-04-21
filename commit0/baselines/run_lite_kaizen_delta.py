"""Kaizen-delta sweep across all 16 commit0-lite libraries.

Runs `kaizen_delta.py` for each lib, aggregates per-lib JSONs, and
writes a single `aggregate_lite_kaizen_delta_<provider>.json` matching
the schema used by other baselines (so compare_baselines.py picks it up).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE = Path.home() / "kaizen-commit0"
RESULTS_DIR = WORKSPACE / "baselines" / "results"
INNER = WORKSPACE / "baselines" / "kaizen_delta.py"

LITE_ORDER = [
    "wcwidth", "deprecated", "cachetools", "voluptuous", "portalocker",
    "pyjwt", "chardet", "tinydb", "simpy", "imapclient", "parsel",
    "marshmallow", "cookiecutter", "babel", "jinja", "minitorch",
]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--skip", nargs="*", default=[])
    parser.add_argument("--max-retries-per-file", type=int, default=1)
    parser.add_argument("--sleep", type=int, default=20)
    args = parser.parse_args()

    target = args.only if args.only else [l for l in LITE_ORDER if l not in args.skip]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    aggregate_path = RESULTS_DIR / f"aggregate_lite_kaizen_delta_{args.provider}.json"

    per_lib: dict[str, dict] = {}
    if aggregate_path.exists():
        try:
            per_lib = json.loads(aggregate_path.read_text()).get("per_library", {})
        except Exception:
            per_lib = {}

    for i, lib in enumerate(target, 1):
        print(f"\n{'=' * 60}\n[{i}/{len(target)}] {lib}\n{'=' * 60}", flush=True)
        proc = subprocess.run(
            [sys.executable, str(INNER), lib,
             "--provider", args.provider,
             "--max-retries-per-file", str(args.max_retries_per_file)],
            cwd=WORKSPACE, capture_output=False,
        )
        per_lib_json = RESULTS_DIR / f"{lib}_kaizen_delta_{args.provider}.json"
        data = (json.loads(per_lib_json.read_text())
                if per_lib_json.exists() else {"missing_per_lib_json": True})
        data["runner_exit"] = proc.returncode
        # Promote final_counts to canonical 'counts' for compare_baselines compatibility
        if "final_counts" in data:
            data["counts"] = data["final_counts"]
            data["pytest_summary"] = data.get("final_summary", "")
        per_lib[lib] = data

        # Aggregate
        total_p = sum(l.get("counts", {}).get("passed", 0) for l in per_lib.values())
        total_f = sum(l.get("counts", {}).get("failed", 0) for l in per_lib.values())
        total_s = sum(l.get("counts", {}).get("skipped", 0) for l in per_lib.values())
        total_e = sum(l.get("counts", {}).get("errors", 0) for l in per_lib.values())
        total_in = sum(l.get("totals", {}).get("input_tokens", 0) for l in per_lib.values())
        total_cr = sum(l.get("totals", {}).get("cache_read_tokens", 0) for l in per_lib.values())
        total_cw = sum(l.get("totals", {}).get("cache_write_tokens", 0) for l in per_lib.values())
        total_out = sum(l.get("totals", {}).get("output_tokens", 0) for l in per_lib.values())
        total_t = sum(l.get("elapsed_s", 0) for l in per_lib.values())
        total_cost = sum(l.get("totals", {}).get("cost_usd", 0) for l in per_lib.values())
        attempted = total_p + total_f + total_e
        agg = {
            "libraries_total": len(per_lib),
            "tests_passed": total_p, "tests_failed": total_f,
            "tests_skipped": total_s, "tests_errored": total_e,
            "tests_attempted_total": attempted,
            "pass_rate_attempted": round(total_p / attempted, 4) if attempted else 0,
            "input_tokens_total": total_in,
            "cache_read_input_tokens_total": total_cr,
            "cache_creation_input_tokens_total": total_cw,
            "output_tokens_total": total_out,
            "wall_seconds_total": round(total_t, 1),
            "cost_usd_estimate": round(total_cost, 2),
        }
        snapshot = {
            "model": data.get("model", "?"),
            "split": "lite",
            "provider": args.provider,
            "completed": list(per_lib.keys()),
            "per_library": per_lib,
            "aggregate": agg,
        }
        aggregate_path.write_text(json.dumps(snapshot, indent=2))

        c = data.get("counts", {})
        files_acc = data.get("files_accepted", 0)
        files_total = data.get("files_total", 0)
        print(f"\n  -> {lib}: passed={c.get('passed', 0)} failed={c.get('failed', 0)} "
              f"err={c.get('errors', 0)}  files_accepted={files_acc}/{files_total}  "
              f"runner_exit={proc.returncode}", flush=True)
        if i < len(target) and args.sleep > 0:
            print(f"  (sleeping {args.sleep}s)", flush=True)
            time.sleep(args.sleep)

    print("\n=== AGGREGATE ===")
    print(json.dumps(agg, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
