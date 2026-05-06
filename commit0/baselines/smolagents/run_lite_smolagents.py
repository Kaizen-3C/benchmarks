"""Run smolagents baseline across all 16 commit0-lite libraries.

Day 22 deliverable. Mirrors run_lite_single_shot.py and run_lite_aider.py.

Run:
  python baselines/smolagents/run_lite_smolagents.py --provider anthropic
  python baselines/smolagents/run_lite_smolagents.py --provider openai
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

LITE_ORDER = [
    "wcwidth", "deprecated", "cachetools", "voluptuous", "portalocker",
    "pyjwt", "chardet", "tinydb", "simpy", "imapclient", "parsel",
    "marshmallow", "cookiecutter", "babel", "jinja", "minitorch",
]

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def parse_summary(summary: str) -> dict[str, int]:
    clean = ANSI_RE.sub("", summary or "")
    out = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for n, kind in re.findall(r"(\d+)\s+(passed|failed|skipped|error[s]?)", clean):
        out["errors" if kind.startswith("error") else kind] = int(n)
    return out


def total(per_lib: dict) -> dict:
    libs = list(per_lib.values())
    counts = [lib.get("final_counts") or lib.get("counts") or {} for lib in libs]
    passed = sum(c.get("passed", 0) for c in counts)
    failed = sum(c.get("failed", 0) for c in counts)
    errors = sum(c.get("errors", 0) for c in counts)
    skipped = sum(c.get("skipped", 0) for c in counts)
    attempted = passed + failed + errors
    cost = sum((lib.get("totals") or {}).get("cost_usd", 0) for lib in libs)
    return {
        "libraries_total": len(libs),
        "tests_passed": passed,
        "tests_failed": failed,
        "tests_skipped": skipped,
        "tests_errored": errors,
        "tests_attempted_total": attempted,
        "pass_rate_attempted": round(passed / attempted, 4) if attempted else 0.0,
        "cost_usd_total": round(cost, 2),
        "wall_seconds_total": round(sum(lib.get("elapsed_s", 0) for lib in libs), 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["anthropic", "openai"], required=True)
    parser.add_argument("--only", nargs="*", help="run only these libs")
    parser.add_argument("--skip", nargs="*", default=[])
    parser.add_argument("--sleep", type=int, default=30)
    args = parser.parse_args()

    inner_script = (
        Path(__file__).parent
        / f"smolagents_{'sonnet' if args.provider == 'anthropic' else 'openai'}.py"
    )
    if not inner_script.exists():
        print(f"ERROR: missing inner script {inner_script}")
        return 2

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    aggregate_path = RESULTS_DIR / f"aggregate_lite_smolagents_{args.provider}.json"

    target = args.only if args.only else [l for l in LITE_ORDER if l not in args.skip]

    per_lib: dict = {}
    if aggregate_path.exists():
        try:
            per_lib = json.loads(aggregate_path.read_text()).get("per_library", {})
        except Exception:
            per_lib = {}

    for i, lib in enumerate(target, 1):
        print(f"\n{'=' * 60}\n[{i}/{len(target)}] {lib} (smolagents/{args.provider})\n"
              f"{'=' * 60}", flush=True)
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, str(inner_script), lib], cwd=WORKSPACE, capture_output=False,
        )
        elapsed = time.time() - t0

        per_lib_json = RESULTS_DIR / f"{lib}_smolagents_{args.provider}.json"
        if per_lib_json.exists():
            try:
                data = json.loads(per_lib_json.read_text())
            except Exception as e:
                data = {"load_error": str(e)}
        else:
            data = {"missing_per_lib_json": True}

        data["runner_exit"] = proc.returncode
        data["wrapper_elapsed_s"] = round(elapsed, 1)
        if "final_summary" in data and "final_counts" not in data:
            data["final_counts"] = parse_summary(data["final_summary"])
        per_lib[lib] = data

        snapshot = {
            "architecture": "smolagents",
            "provider": args.provider,
            "split": "lite",
            "completed": list(per_lib.keys()),
            "per_library": per_lib,
            "aggregate": total(per_lib),
        }
        aggregate_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

        c = data.get("final_counts") or {}
        cost = (data.get("totals") or {}).get("cost_usd", 0)
        print(
            f"\n  -> {lib}: passed={c.get('passed', 0)} failed={c.get('failed', 0)} "
            f"errors={c.get('errors', 0)} cost=${cost:.2f}",
            flush=True,
        )

        if i < len(target) and args.sleep > 0:
            time.sleep(args.sleep)

    print("\n" + "=" * 60)
    print("AGGREGATE")
    print("=" * 60)
    print(json.dumps(total(per_lib), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
