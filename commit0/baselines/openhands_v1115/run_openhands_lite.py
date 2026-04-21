"""B6 baseline runner: OpenHands V1 (agent SDK v1.11.5) + Sonnet 4.6 on commit0-lite.

Wraps the upstream `commit0-infer` runner with three additions over a vanilla call:

  1. Hard total-spend cap. A sidecar thread reads the live output.jsonl every
     60 s, sums per-instance cost, and SIGTERMs the runner if total > cap.
  2. 2-pass mode. Each pass writes to its own dir; lets us measure variance.
  3. Pinned-version verification. Aborts if openhands-sdk != 1.11.5 OR if the
     benchmarks repo isn't at SHA 62477b41.

Run pattern (from inside ~/openhands-v1115/, with .venv activated):

    python run_openhands_lite.py --passes 2 --cost-cap-usd 50

The wrapper writes runs/claude-sonnet-4-6/pass{1,2}/output.jsonl and a final
aggregate at runs/claude-sonnet-4-6/aggregate.json.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

PINNED_SDK_VERSION = "1.11.5"
PINNED_BENCHMARKS_SHA = "62477b41"  # 2026-02-24, day of Sonnet 4.6 submission
DEFAULT_COST_CAP_USD = 50.0
COST_POLL_INTERVAL_S = 60
LITE_LIB_COUNT = 16

# Default workspace and output paths assume the layout in SETUP.md.
WORKSPACE = Path.home() / "openhands-v1115"
BENCHMARKS_DIR = WORKSPACE / "benchmarks"
LLM_CONFIG = WORKSPACE / "llm_config_sonnet46.json"


def verify_pins() -> None:
    """Abort if the installed SDK or benchmarks repo isn't at our pinned versions."""
    try:
        import importlib.metadata
        installed = importlib.metadata.version("openhands-sdk")
    except Exception as e:
        sys.exit(f"FATAL: could not import openhands-sdk: {e}")
    if installed != PINNED_SDK_VERSION:
        sys.exit(
            f"FATAL: openhands-sdk=={installed!r} but pin demands {PINNED_SDK_VERSION!r}.\n"
            f"  Install with: pip install openhands-sdk=={PINNED_SDK_VERSION} "
            f"openhands-tools=={PINNED_SDK_VERSION} "
            f"openhands-agent-server=={PINNED_SDK_VERSION} "
            f"openhands-workspace=={PINNED_SDK_VERSION}"
        )

    if not BENCHMARKS_DIR.is_dir():
        sys.exit(f"FATAL: benchmarks repo not found at {BENCHMARKS_DIR}")
    sha = subprocess.check_output(
        ["git", "-C", str(BENCHMARKS_DIR), "rev-parse", "HEAD"], text=True
    ).strip()
    if not sha.startswith(PINNED_BENCHMARKS_SHA):
        sys.exit(
            f"FATAL: benchmarks HEAD={sha[:8]} but pin demands {PINNED_BENCHMARKS_SHA}.\n"
            f"  Fix with: git -C {BENCHMARKS_DIR} checkout {PINNED_BENCHMARKS_SHA}"
        )

    if not LLM_CONFIG.exists():
        sys.exit(f"FATAL: llm config not found at {LLM_CONFIG}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("FATAL: ANTHROPIC_API_KEY not in env (source .env first)")

    print(f"[verify] openhands-sdk=={installed}  benchmarks@{sha[:8]}  ok")


def sum_cost_from_jsonl(path: Path) -> tuple[float, int]:
    """Return (total_cost_usd, instances_done)."""
    if not path.exists():
        return 0.0, 0
    total, n = 0.0, 0
    try:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # OpenHands writes various cost fields; take the most-specific
                # one available. EvalOutput.metrics has { "total_cost": ... }.
                metrics = obj.get("metrics") or {}
                cost = metrics.get("total_cost") or obj.get("total_cost") or 0.0
                try:
                    total += float(cost)
                    n += 1
                except (TypeError, ValueError):
                    pass
    except Exception as e:
        print(f"[cost-monitor] read error: {e}", file=sys.stderr)
    return total, n


class CostMonitor(threading.Thread):
    def __init__(self, output_jsonl: Path, cap_usd: float, proc: subprocess.Popen):
        super().__init__(daemon=True)
        self.output_jsonl = output_jsonl
        self.cap_usd = cap_usd
        self.proc = proc
        self._stop = threading.Event()
        self.last_total = 0.0
        self.last_n = 0
        self.killed_for_cap = False

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.wait(COST_POLL_INTERVAL_S):
            if self.proc.poll() is not None:
                return
            total, n = sum_cost_from_jsonl(self.output_jsonl)
            self.last_total, self.last_n = total, n
            print(f"[cost-monitor] ${total:.2f} across {n}/{LITE_LIB_COUNT} instances "
                  f"(cap ${self.cap_usd:.2f})", flush=True)
            if total >= self.cap_usd:
                print(f"[cost-monitor] CAP EXCEEDED — sending SIGTERM", file=sys.stderr, flush=True)
                self.killed_for_cap = True
                try:
                    self.proc.terminate()
                except Exception as e:
                    print(f"[cost-monitor] SIGTERM failed: {e}", file=sys.stderr)
                # Give it 30s, then escalate to SIGKILL.
                for _ in range(30):
                    if self.proc.poll() is not None:
                        return
                    time.sleep(1)
                try:
                    self.proc.kill()
                except Exception:
                    pass
                return


def run_one_pass(
    pass_n: int, output_dir: Path, max_iterations: int, num_workers: int,
    cost_cap_usd: float,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_jsonl = output_dir / "output.jsonl"

    cmd = [
        sys.executable, "-m", "benchmarks.commit0.run_infer",
        str(LLM_CONFIG),
        "--dataset", "wentingzhao/commit0_combined",
        "--split", "test",
        "--repo-split", "lite",
        "--workspace", "docker",  # local Docker runtime; OpenHands' published runs used "remote" (needs RUNTIME_API_KEY for their hosted service)
        "--max-iterations", str(max_iterations),
        "--num-workers", str(num_workers),
        "--output-dir", str(output_dir),
    ]
    # Required to bypass the SDK's strict workspace-root detection when running
    # from a pip-installed venv rather than a sibling-source uv workspace. The
    # env var was added by our local patch to build.py — see SETUP.md §6.1.
    env = os.environ.copy()
    env.setdefault(
        "OH_SDK_PROJECT_ROOT",
        str(BENCHMARKS_DIR / "vendor" / "software-agent-sdk"),
    )
    print(f"\n=== Pass {pass_n} → {output_dir} ===")
    print(f"  cmd: {' '.join(cmd)}")
    print(f"  cost cap: ${cost_cap_usd:.2f}")
    print(f"  OH_SDK_PROJECT_ROOT={env['OH_SDK_PROJECT_ROOT']}")

    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=BENCHMARKS_DIR, env=env)
    monitor = CostMonitor(output_jsonl, cost_cap_usd, proc)
    monitor.start()
    proc.wait()
    monitor.stop()
    elapsed = time.time() - t0

    final_cost, final_n = sum_cost_from_jsonl(output_jsonl)
    # If the inner process bailed quickly without producing any instances and
    # we DIDN'T kill it for cap, that's an install/import error — surface it.
    suspicious = (
        not monitor.killed_for_cap
        and final_n == 0
        and elapsed < 30
        and proc.returncode != 0
    )
    return {
        "pass": pass_n,
        "exit_code": proc.returncode,
        "wall_seconds": round(elapsed, 1),
        "instances_completed": final_n,
        "total_cost_usd": round(final_cost, 4),
        "killed_for_cap": monitor.killed_for_cap,
        "suspicious_early_exit": suspicious,
        "output_jsonl": str(output_jsonl),
    }


def parse_per_lib_from_output_jsonl(path: Path) -> dict:
    """Extract per-instance metrics. Schema follows EvalOutput in OpenHands' benchmarks."""
    rows: dict[str, dict] = {}
    if not path.exists():
        return rows
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            instance_id = obj.get("instance_id") or obj.get("repo") or "?"
            test_result = obj.get("test_result") or {}
            metrics = obj.get("metrics") or {}
            usage = metrics.get("accumulated_token_usage") or {}
            rows[instance_id] = {
                "test_result": test_result,
                "report": obj.get("report") or {},
                "metrics": {
                    "total_cost": metrics.get("total_cost"),
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                    "cache_read_tokens": usage.get("cache_read_tokens"),
                    "cache_write_tokens": usage.get("cache_creation_tokens"),
                },
                "n_steps": len(obj.get("history") or []),
                "wall_seconds": obj.get("duration") or obj.get("runtime"),
                "error": obj.get("error"),
            }
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--passes", type=int, default=2,
                        help="Number of full lite-sweep passes (default: 2 for variance)")
    parser.add_argument("--cost-cap-usd", type=float, default=DEFAULT_COST_CAP_USD,
                        help="Per-pass hard ceiling. SIGTERM the runner if exceeded.")
    parser.add_argument("--max-iterations", type=int, default=100,
                        help="Agent step cap per instance (matches OpenHands published config).")
    parser.add_argument("--num-workers", type=int, default=16,
                        help="Parallel workers (matches OpenHands published config).")
    parser.add_argument("--skip-verify", action="store_true",
                        help="Skip the version-pin check (testing only).")
    args = parser.parse_args()

    if not args.skip_verify:
        verify_pins()

    runs_dir = WORKSPACE / "runs" / "claude-sonnet-4-6"
    runs_dir.mkdir(parents=True, exist_ok=True)

    pass_summaries = []
    per_lib_per_pass: dict[str, dict] = {}
    for p in range(1, args.passes + 1):
        pass_dir = runs_dir / f"pass{p}"
        summary = run_one_pass(
            p, pass_dir, args.max_iterations, args.num_workers, args.cost_cap_usd,
        )
        per_lib_per_pass[f"pass{p}"] = parse_per_lib_from_output_jsonl(
            pass_dir / "output.jsonl"
        )
        pass_summaries.append(summary)
        print(f"[pass {p}] cost=${summary['total_cost_usd']:.2f}  "
              f"completed={summary['instances_completed']}/{LITE_LIB_COUNT}  "
              f"wall={summary['wall_seconds']:.0f}s  "
              f"killed_for_cap={summary['killed_for_cap']}")

    # Aggregate summary across passes
    aggregate = {
        "pinned_sdk": PINNED_SDK_VERSION,
        "pinned_benchmarks_sha": PINNED_BENCHMARKS_SHA,
        "model": "claude-sonnet-4-6",
        "split": "lite",
        "passes": pass_summaries,
        "per_pass_per_lib": per_lib_per_pass,
        "totals": {
            "total_cost_usd": round(sum(s["total_cost_usd"] for s in pass_summaries), 4),
            "total_wall_seconds": round(sum(s["wall_seconds"] for s in pass_summaries), 1),
            "passes_completed": len(pass_summaries),
            "any_killed_for_cap": any(s["killed_for_cap"] for s in pass_summaries),
        },
    }
    out_path = runs_dir / "aggregate.json"
    out_path.write_text(json.dumps(aggregate, indent=2))
    print(f"\nAggregate: {out_path}")
    print(json.dumps(aggregate["totals"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
