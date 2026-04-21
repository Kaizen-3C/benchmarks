"""Run single-shot Sonnet baseline across all 16 commit0-lite libraries.

Saves per-library JSON to baselines/results/<lib>_single_shot_sonnet.json
(via the inner script) and aggregates them into
baselines/results/aggregate_lite_single_shot_sonnet.json after each lib
completes (so a mid-run crash doesn't lose data).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE = Path.home() / "kaizen-commit0"
RESULTS_DIR = WORKSPACE / "baselines" / "results"
INNER_SCRIPT = WORKSPACE / "baselines" / "single_shot_sonnet.py"

# commit0-lite, ordered small-to-large so a wiring bug surfaces quickly.
LITE_ORDER = [
    "wcwidth",
    "deprecated",
    "cachetools",
    "voluptuous",
    "portalocker",
    "pyjwt",
    "chardet",
    "tinydb",
    "simpy",
    "imapclient",
    "parsel",
    "marshmallow",
    "cookiecutter",
    "babel",
    "jinja",
    "minitorch",
]

# Strip ANSI color codes so summaries are readable in JSON.
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
SUMMARY_RE = re.compile(
    r"(\d+) failed[, ]+|(\d+) passed[, ]+|(\d+) skipped[, ]+|(\d+) error",
)


def parse_summary(summary: str) -> dict[str, int]:
    """Extract passed/failed/skipped/error counts from a pytest summary line."""
    clean = ANSI_RE.sub("", summary or "")
    out = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for n, kind in re.findall(
        r"(\d+)\s+(passed|failed|skipped|error[s]?)", clean
    ):
        kind_norm = "errors" if kind.startswith("error") else kind
        out[kind_norm] = int(n)
    return out


def total(per_lib: dict[str, dict]) -> dict[str, object]:
    libs = list(per_lib.values())
    summaries = [lib.get("counts", {}) for lib in libs]
    passed = sum(s.get("passed", 0) for s in summaries)
    failed = sum(s.get("failed", 0) for s in summaries)
    skipped = sum(s.get("skipped", 0) for s in summaries)
    errors = sum(s.get("errors", 0) for s in summaries)
    attempted = passed + failed + errors
    return {
        "libraries_total": len(libs),
        "tests_passed": passed,
        "tests_failed": failed,
        "tests_skipped": skipped,
        "tests_errored": errors,
        "tests_attempted_total": attempted,
        "pass_rate_attempted": round(passed / attempted, 4) if attempted else 0.0,
        "input_tokens_total": sum(lib.get("input_tokens", 0) for lib in libs),
        "output_tokens_total": sum(lib.get("output_tokens", 0) for lib in libs),
        "wall_seconds_total": round(sum(lib.get("elapsed_s", 0) for lib in libs), 1),
    }


SLEEP_BETWEEN_LIBS = 30  # seconds; helps stay under Sonnet TPM after big calls


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="run only these libs")
    parser.add_argument("--skip", nargs="*", default=[], help="skip these libs")
    parser.add_argument("--sleep", type=int, default=SLEEP_BETWEEN_LIBS)
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    aggregate_path = RESULTS_DIR / "aggregate_lite_single_shot_sonnet.json"

    target = args.only if args.only else [l for l in LITE_ORDER if l not in args.skip]

    # Preserve any existing per-lib results so we can rerun a subset and
    # update the aggregate without losing the ones we already have.
    per_lib: dict[str, dict] = {}
    if aggregate_path.exists():
        try:
            prior = json.loads(aggregate_path.read_text())
            per_lib = prior.get("per_library", {})
        except Exception:
            per_lib = {}

    for i, lib in enumerate(target, 1):
        print(f"\n{'=' * 60}\n[{i}/{len(target)}] {lib}\n{'=' * 60}", flush=True)
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, str(INNER_SCRIPT), lib],
            cwd=WORKSPACE,
            capture_output=False,  # stream to terminal
        )
        runner_exit = proc.returncode
        elapsed = time.time() - t0

        # The inner script wrote a per-lib JSON. Load it.
        per_lib_json = RESULTS_DIR / f"{lib}_single_shot_sonnet.json"
        if per_lib_json.exists():
            try:
                data = json.loads(per_lib_json.read_text())
            except Exception as e:
                data = {"load_error": str(e)}
        else:
            data = {"missing_per_lib_json": True}

        data["runner_exit"] = runner_exit
        data["wrapper_elapsed_s"] = round(elapsed, 1)
        if "pytest_summary" in data:
            data["counts"] = parse_summary(data["pytest_summary"])
            data["pytest_summary_clean"] = ANSI_RE.sub("", data["pytest_summary"]).strip()
        per_lib[lib] = data

        # Write incrementally so crashes don't lose data.
        snapshot = {
            "model": "claude-sonnet-4-6",
            "split": "lite",
            "completed": list(per_lib.keys()),
            "per_library": per_lib,
            "aggregate": total(per_lib),
        }
        aggregate_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

        c = data.get("counts", {})
        print(
            f"\n  -> {lib}: passed={c.get('passed', 0)} failed={c.get('failed', 0)} "
            f"skipped={c.get('skipped', 0)} errors={c.get('errors', 0)} "
            f"runner_exit={runner_exit}",
            flush=True,
        )

        # Rate-limit cushion before next lib.
        if i < len(target) and args.sleep > 0:
            print(f"  (sleeping {args.sleep}s before next lib)", flush=True)
            time.sleep(args.sleep)

    print("\n" + "=" * 60)
    print("AGGREGATE")
    print("=" * 60)
    print(json.dumps(total(per_lib), indent=2))
    print(f"\nFull report: {aggregate_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
