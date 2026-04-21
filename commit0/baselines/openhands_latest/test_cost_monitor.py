"""Smoke test for the OpenHands cost monitor.

Prevents the $85 incident: our wrapper read `total_cost`, but OpenHands
writes `accumulated_cost`. Field-name drift = silent cap failure.

This test runs ONE inexpensive instance (`wcwidth`, smallest lib), waits for
the output.jsonl to land, then asserts that:

  1. The file exists and has at least 1 row.
  2. The cost-monitor's parser reads a *non-zero* cost from that row.
  3. The field name our parser uses is present in the row's metrics.

Run as a precondition before any expensive sweep:

    python test_cost_monitor.py

Exits 0 on success, non-zero on any assertion failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WORKSPACE = Path.home() / "openhands-latest"
LLM_CONFIG = WORKSPACE / "llm_config_runtime.json"
BENCHMARKS = WORKSPACE / "benchmarks"
INNER_PYTHON = BENCHMARKS / ".venv" / "bin" / "python"


def main() -> int:
    if not INNER_PYTHON.exists():
        print(f"[FAIL] inner venv python not found: {INNER_PYTHON}", file=sys.stderr)
        return 1
    if not LLM_CONFIG.exists():
        print(f"[FAIL] llm config not found at {LLM_CONFIG}", file=sys.stderr)
        return 1
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[FAIL] ANTHROPIC_API_KEY not in env", file=sys.stderr)
        return 1

    # Run one instance: wcwidth (smallest, cheapest)
    with tempfile.TemporaryDirectory(prefix="costmon-") as tmp:
        tmp_dir = Path(tmp)
        instances_file = tmp_dir / "instances.txt"
        instances_file.write_text("wcwidth\n")
        output_dir = tmp_dir / "out"
        output_dir.mkdir()

        cmd = [
            str(INNER_PYTHON), "-m", "benchmarks.commit0.run_infer",
            str(LLM_CONFIG),
            "--dataset", "wentingzhao/commit0_combined",
            "--split", "test",
            "--workspace", "docker",
            "--select", str(instances_file),
            "--max-iterations", "30",   # tight cap, just need cost > 0
            "--num-workers", "1",
            "--output-dir", str(output_dir),
        ]
        env = os.environ.copy()
        env.setdefault("OH_SDK_PROJECT_ROOT",
                       str(BENCHMARKS / "vendor" / "software-agent-sdk"))
        print(f"[smoke] running 1-instance probe in {output_dir}")
        print(f"[smoke] cmd: {' '.join(cmd)}")
        t0 = time.time()
        proc = subprocess.run(cmd, cwd=BENCHMARKS, env=env, capture_output=True, text=True)
        elapsed = time.time() - t0
        print(f"[smoke] exit={proc.returncode}  wall={elapsed:.0f}s")

        # Find the output.jsonl
        jsonl = next(output_dir.rglob("output.jsonl"), None)
        if jsonl is None:
            print(f"[FAIL] no output.jsonl produced; stderr tail:", file=sys.stderr)
            print(proc.stderr[-1000:], file=sys.stderr)
            return 1

        rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        if not rows:
            print(f"[FAIL] {jsonl} is empty", file=sys.stderr)
            return 1
        print(f"[smoke] rows={len(rows)}  jsonl={jsonl}")

        # The actual schema check
        first = rows[0]
        metrics = first.get("metrics") or {}
        candidates = ["accumulated_cost", "total_cost"]
        found_field = None
        cost_value = 0.0
        for f in candidates:
            v = metrics.get(f)
            if v is not None:
                found_field = f
                try:
                    cost_value = float(v)
                except (TypeError, ValueError):
                    pass
                break

        if found_field is None:
            print(f"[FAIL] no cost field in metrics; available keys: {list(metrics.keys())}",
                  file=sys.stderr)
            return 1
        print(f"[smoke] cost field present: '{found_field}' = ${cost_value:.4f}")

        # Now match the wrapper's expected field
        expected = "accumulated_cost"
        if found_field != expected:
            print(f"[FAIL] wrapper expects '{expected}' but OpenHands wrote '{found_field}'\n"
                  f"        Update run_openhands_lite.py:sum_cost_from_jsonl_dir() before "
                  f"running any expensive sweep.", file=sys.stderr)
            return 2

        if cost_value <= 0:
            print(f"[FAIL] cost is {cost_value} -- expected >0 for a real LLM call", file=sys.stderr)
            return 3

        print(f"[OK] cost monitor will read '{expected}' correctly. "
              f"Real cost on this 1-lib probe: ${cost_value:.4f}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
