"""B6 baseline runner: OpenHands V1 (latest SDK) + Sonnet 4.6 on commit0-lite.

Same wrapper as openhands_v1115/run_openhands_lite.py but pointed at the
latest SDK install at ~/openhands-latest/. We pivoted from the v1.11.5 pin
after confirming a Pydantic validator bug in v1.11.5's DockerDevWorkspace
(rejects `base_image`-only construction even though that's the documented
usage; latest SDK accepts it).

This means our B6 number will be "OpenHands SDK [version installed] +
Sonnet 4.6 + local Docker workspace" — NOT a strict reproduction of
OpenHands' published 7/16 (which used v1.11.5 + their hosted RUNTIME_API
service). The architectural comparison vs Kaizen-delta is unaffected:
both will use whatever current SDK + Sonnet 4.6 + same data.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

DEFAULT_COST_CAP_USD = 50.0
COST_POLL_INTERVAL_S = 60
LITE_LIB_COUNT = 16

WORKSPACE = Path.home() / "openhands-latest"
BENCHMARKS_DIR = WORKSPACE / "benchmarks"
# launch_b6.sh writes this at run time with ANTHROPIC_API_KEY substituted
# from the project .env. Never commit it (chmod 600).
LLM_CONFIG = WORKSPACE / "llm_config_runtime.json"
INNER_VENV_PYTHON = BENCHMARKS_DIR / ".venv" / "bin" / "python"


def verify_install() -> None:
    """Sanity check: SDK importable, benchmarks at clean state, llm_config present."""
    if not INNER_VENV_PYTHON.exists():
        sys.exit(f"FATAL: inner venv python not found: {INNER_VENV_PYTHON}")
    sdk_version = subprocess.check_output(
        [str(INNER_VENV_PYTHON), "-c",
         "import importlib.metadata as m; print(m.version('openhands-sdk'))"],
        text=True,
    ).strip()
    bench_sha = subprocess.check_output(
        ["git", "-C", str(BENCHMARKS_DIR), "rev-parse", "HEAD"], text=True
    ).strip()
    if not LLM_CONFIG.exists():
        sys.exit(f"FATAL: llm config not found at {LLM_CONFIG}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("FATAL: ANTHROPIC_API_KEY not in env")
    print(f"[verify] openhands-sdk=={sdk_version}  benchmarks@{bench_sha[:8]}  ok")
    return sdk_version, bench_sha


def sum_cost_from_jsonl_dir(output_dir: Path) -> tuple[float, int]:
    """Total cost + completed instances from any output.jsonl under output_dir."""
    total, n = 0.0, 0
    for jsonl in output_dir.rglob("output.jsonl"):
        try:
            with jsonl.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    metrics = obj.get("metrics") or {}
                    # OpenHands writes 'accumulated_cost'; we previously read 'total_cost'
                    # (silent zero from a typo cost us $85 on the first B6 run -- AAR §What didn't work).
                    # Run test_cost_monitor.py before any expensive sweep to verify this still matches.
                    cost = (metrics.get("accumulated_cost")
                            or metrics.get("total_cost")
                            or obj.get("total_cost")
                            or 0.0)
                    try:
                        total += float(cost)
                        n += 1
                    except (TypeError, ValueError):
                        pass
        except Exception:
            continue
    return total, n


class CostMonitor(threading.Thread):
    def __init__(self, output_dir: Path, cap_usd: float, proc: subprocess.Popen):
        super().__init__(daemon=True)
        self.output_dir = output_dir
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
            total, n = sum_cost_from_jsonl_dir(self.output_dir)
            self.last_total, self.last_n = total, n
            print(f"[cost-monitor] ${total:.2f} across {n}/{LITE_LIB_COUNT} instances "
                  f"(cap ${self.cap_usd:.2f})", flush=True)
            if total >= self.cap_usd:
                print(f"[cost-monitor] CAP EXCEEDED — sending SIGTERM",
                      file=sys.stderr, flush=True)
                self.killed_for_cap = True
                try:
                    self.proc.terminate()
                except Exception:
                    pass
                for _ in range(30):
                    if self.proc.poll() is not None:
                        return
                    time.sleep(1)
                try:
                    self.proc.kill()
                except Exception:
                    pass
                return


def run_one_pass(pass_n: int, output_dir: Path, max_iterations: int,
                 num_workers: int, cost_cap_usd: float) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(INNER_VENV_PYTHON), "-m", "benchmarks.commit0.run_infer",
        str(LLM_CONFIG),
        "--dataset", "wentingzhao/commit0_combined",
        "--split", "test",
        "--repo-split", "lite",
        "--workspace", "docker",
        "--max-iterations", str(max_iterations),
        "--num-workers", str(num_workers),
        "--output-dir", str(output_dir),
    ]
    print(f"\n=== Pass {pass_n} → {output_dir} ===")
    print(f"  cmd: {' '.join(cmd)}")
    print(f"  cost cap: ${cost_cap_usd:.2f}")

    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=BENCHMARKS_DIR)
    monitor = CostMonitor(output_dir, cost_cap_usd, proc)
    monitor.start()
    proc.wait()
    monitor.stop()
    elapsed = time.time() - t0

    final_cost, final_n = sum_cost_from_jsonl_dir(output_dir)
    suspicious = (
        not monitor.killed_for_cap
        and final_n == 0
        and elapsed < 60
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
        "output_dir": str(output_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--cost-cap-usd", type=float, default=DEFAULT_COST_CAP_USD)
    parser.add_argument("--max-iterations", type=int, default=100)
    parser.add_argument("--num-workers", type=int, default=16)
    args = parser.parse_args()

    sdk_version, bench_sha = verify_install()
    runs_dir = WORKSPACE / "runs" / "claude-sonnet-4-6"
    runs_dir.mkdir(parents=True, exist_ok=True)

    pass_summaries = []
    for p in range(1, args.passes + 1):
        pass_dir = runs_dir / f"pass{p}"
        # Wipe any stale outputs to avoid the runner's resume-skip behavior
        if pass_dir.exists():
            import shutil
            shutil.rmtree(pass_dir)
        summary = run_one_pass(
            p, pass_dir, args.max_iterations, args.num_workers, args.cost_cap_usd,
        )
        pass_summaries.append(summary)
        print(f"[pass {p}] cost=${summary['total_cost_usd']:.2f}  "
              f"completed={summary['instances_completed']}/{LITE_LIB_COUNT}  "
              f"wall={summary['wall_seconds']:.0f}s  "
              f"killed_for_cap={summary['killed_for_cap']}  "
              f"suspicious={summary['suspicious_early_exit']}")
        if summary["suspicious_early_exit"]:
            print(f"[FATAL] pass {p} bailed early with no instances. Aborting.",
                  file=sys.stderr)
            break

    aggregate = {
        "sdk_version": sdk_version,
        "benchmarks_sha": bench_sha,
        "model": "claude-sonnet-4-6",
        "split": "lite",
        "passes": pass_summaries,
        "totals": {
            "total_cost_usd": round(sum(s["total_cost_usd"] for s in pass_summaries), 4),
            "total_wall_seconds": round(sum(s["wall_seconds"] for s in pass_summaries), 1),
            "passes_completed": len(pass_summaries),
            "any_killed_for_cap": any(s["killed_for_cap"] for s in pass_summaries),
            "any_suspicious_exit": any(s["suspicious_early_exit"] for s in pass_summaries),
        },
    }
    out_path = runs_dir / "aggregate.json"
    out_path.write_text(json.dumps(aggregate, indent=2))
    print(f"\nAggregate: {out_path}")
    print(json.dumps(aggregate["totals"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
