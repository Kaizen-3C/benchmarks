"""Run Reflexion-on-GPT-5.4 across all 16 commit0-lite libraries."""

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
INNER = WORKSPACE / "baselines" / "reflexion_openai.py"

LITE_ORDER = [
    "wcwidth", "deprecated", "cachetools", "voluptuous", "portalocker",
    "pyjwt", "chardet", "tinydb", "simpy", "imapclient", "parsel",
    "marshmallow", "cookiecutter", "babel", "jinja", "minitorch",
]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def parse_counts(summary):
    out = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for n, kind in re.findall(
        r"(\d+)\s+(passed|failed|skipped|errors?)", ANSI.sub("", summary or "")
    ):
        kn = "errors" if kind.startswith("error") else kind
        out[kn] = int(n)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--skip", nargs="*", default=[])
    parser.add_argument("--max-iters", type=int, default=3)
    parser.add_argument("--sleep", type=int, default=20)
    args = parser.parse_args()

    target = args.only if args.only else [l for l in LITE_ORDER if l not in args.skip]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    aggregate_path = RESULTS_DIR / "aggregate_lite_reflexion_openai.json"

    per_lib = {}
    if aggregate_path.exists():
        try:
            per_lib = json.loads(aggregate_path.read_text()).get("per_library", {})
        except Exception:
            per_lib = {}

    for i, lib in enumerate(target, 1):
        print(f"\n{'=' * 60}\n[{i}/{len(target)}] {lib}\n{'=' * 60}", flush=True)
        proc = subprocess.run([sys.executable, str(INNER), lib,
                               "--max-iters", str(args.max_iters)],
                              cwd=WORKSPACE, capture_output=False)
        per_lib_json = RESULTS_DIR / f"{lib}_reflexion_openai.json"
        data = json.loads(per_lib_json.read_text()) if per_lib_json.exists() else {"missing": True}
        data["runner_exit"] = proc.returncode
        if "best_summary" in data:
            data["counts"] = parse_counts(data["best_summary"])
        per_lib[lib] = data

        total_p = sum(l.get("counts", {}).get("passed", 0) for l in per_lib.values())
        total_f = sum(l.get("counts", {}).get("failed", 0) for l in per_lib.values())
        total_s = sum(l.get("counts", {}).get("skipped", 0) for l in per_lib.values())
        total_e = sum(l.get("counts", {}).get("errors", 0) for l in per_lib.values())
        total_in = sum(l.get("totals", {}).get("input_tokens", 0) for l in per_lib.values())
        total_cr = sum(l.get("totals", {}).get("cached_input_tokens", 0) for l in per_lib.values())
        total_out = sum(l.get("totals", {}).get("output_tokens", 0) for l in per_lib.values())
        total_t = sum(l.get("totals", {}).get("elapsed_s", 0) for l in per_lib.values())
        attempted = total_p + total_f + total_e
        fresh = total_in - total_cr
        # GPT-5.4 list pricing (approx): input $1.25/MTok, cached $0.125/MTok, output $10/MTok
        cost = fresh * 1.25 / 1_000_000 + total_cr * 0.125 / 1_000_000 + total_out * 10 / 1_000_000
        agg = {
            "libraries_total": len(per_lib),
            "tests_passed": total_p, "tests_failed": total_f,
            "tests_skipped": total_s, "tests_errored": total_e,
            "tests_attempted_total": attempted,
            "pass_rate_attempted": round(total_p / attempted, 4) if attempted else 0,
            "input_tokens_total": total_in, "cached_input_tokens_total": total_cr,
            "output_tokens_total": total_out,
            "wall_seconds_total": round(total_t, 1),
            "cost_usd_estimate": round(cost, 2),
        }
        snapshot = {"model": "gpt-5.4", "split": "lite", "max_iters": args.max_iters,
                    "completed": list(per_lib.keys()),
                    "per_library": per_lib, "aggregate": agg}
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
