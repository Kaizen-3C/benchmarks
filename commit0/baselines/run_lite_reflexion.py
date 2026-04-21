"""Run Reflexion-on-Sonnet across all 16 commit0-lite libraries."""

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
INNER = WORKSPACE / "baselines" / "reflexion_sonnet.py"

# Same order as B2 — small-to-large.
LITE_ORDER = [
    "wcwidth", "deprecated", "cachetools", "voluptuous", "portalocker",
    "pyjwt", "chardet", "tinydb", "simpy", "imapclient", "parsel",
    "marshmallow", "cookiecutter", "babel", "jinja", "minitorch",
]

ANSI = re.compile(r"\x1b\[[0-9;]*m")
SLEEP = 30


def parse_counts(summary: str) -> dict[str, int]:
    out = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for n, kind in re.findall(
        r"(\d+)\s+(passed|failed|skipped|errors?)", ANSI.sub("", summary or "")
    ):
        kind_norm = "errors" if kind.startswith("error") else kind
        out[kind_norm] = int(n)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--skip", nargs="*", default=[])
    parser.add_argument("--max-iters", type=int, default=3)
    parser.add_argument("--sleep", type=int, default=SLEEP)
    args = parser.parse_args()

    target = args.only if args.only else [l for l in LITE_ORDER if l not in args.skip]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    aggregate_path = RESULTS_DIR / "aggregate_lite_reflexion_sonnet.json"

    per_lib: dict[str, dict] = {}
    if aggregate_path.exists():
        try:
            per_lib = json.loads(aggregate_path.read_text()).get("per_library", {})
        except Exception:
            per_lib = {}

    for i, lib in enumerate(target, 1):
        print(f"\n{'=' * 60}\n[{i}/{len(target)}] {lib}\n{'=' * 60}", flush=True)
        proc = subprocess.run(
            [sys.executable, str(INNER), lib, "--max-iters", str(args.max_iters)],
            cwd=WORKSPACE, capture_output=False,
        )

        per_lib_json = RESULTS_DIR / f"{lib}_reflexion_sonnet.json"
        data = json.loads(per_lib_json.read_text()) if per_lib_json.exists() else {
            "missing_per_lib_json": True
        }
        data["runner_exit"] = proc.returncode
        if "best_summary" in data:
            data["counts"] = parse_counts(data["best_summary"])
        per_lib[lib] = data

        # Aggregate
        total_p = sum(l.get("counts", {}).get("passed", 0) for l in per_lib.values())
        total_f = sum(l.get("counts", {}).get("failed", 0) for l in per_lib.values())
        total_s = sum(l.get("counts", {}).get("skipped", 0) for l in per_lib.values())
        total_e = sum(l.get("counts", {}).get("errors", 0) for l in per_lib.values())
        total_in = sum(l.get("totals", {}).get("input_tokens", 0) for l in per_lib.values())
        total_out = sum(l.get("totals", {}).get("output_tokens", 0) for l in per_lib.values())
        total_cache_r = sum(l.get("totals", {}).get("cache_read_input_tokens", 0) for l in per_lib.values())
        total_cache_w = sum(l.get("totals", {}).get("cache_creation_input_tokens", 0) for l in per_lib.values())
        total_t = sum(l.get("totals", {}).get("elapsed_s", 0) for l in per_lib.values())
        attempted = total_p + total_f + total_e

        # Cost model: standard Sonnet 4.6 list price
        # input  $3/MTok | cache_w +25% = $3.75/MTok | cache_r 10% = $0.30/MTok | output $15/MTok
        cost = (
            total_in * 3 / 1_000_000
            + total_cache_w * 3.75 / 1_000_000
            + total_cache_r * 0.30 / 1_000_000
            + total_out * 15 / 1_000_000
        )
        agg = {
            "libraries_total": len(per_lib),
            "tests_passed": total_p,
            "tests_failed": total_f,
            "tests_skipped": total_s,
            "tests_errored": total_e,
            "tests_attempted_total": attempted,
            "pass_rate_attempted": round(total_p / attempted, 4) if attempted else 0,
            "input_tokens_total": total_in,
            "output_tokens_total": total_out,
            "cache_read_total": total_cache_r,
            "cache_creation_total": total_cache_w,
            "wall_seconds_total": round(total_t, 1),
            "cost_usd_estimate": round(cost, 2),
        }
        snapshot = {"model": "claude-sonnet-4-6",
                    "split": "lite",
                    "max_iters": args.max_iters,
                    "completed": list(per_lib.keys()),
                    "per_library": per_lib,
                    "aggregate": agg}
        aggregate_path.write_text(json.dumps(snapshot, indent=2))

        c = data.get("counts", {})
        iters = data.get("iters_run", 0)
        print(f"\n  -> {lib}: passed={c.get('passed', 0)} failed={c.get('failed', 0)} "
              f"err={c.get('errors', 0)} iters={iters} runner_exit={proc.returncode}",
              flush=True)

        if i < len(target) and args.sleep > 0:
            print(f"  (sleeping {args.sleep}s)", flush=True)
            time.sleep(args.sleep)

    print("\n=== AGGREGATE ===")
    print(json.dumps(agg, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
