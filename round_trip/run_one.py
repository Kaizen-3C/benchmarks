"""End-to-end round-trip runner for ONE commit0-lite library.

Pipeline (per ADR-0063):
    1. Decompose working code    -> spec/<lib>/{adrs,contracts,oracles}/
    2. Run 5 spec-quality gates  (coverage, specificity, consistency,
                                  test_oracle_alignment, implementation_leak)
    3. Recompose from ADRs only  -> recomposed/<lib>/
    4. Run 4 fidelity metrics    (Q1 test / Q2 behavioral / Q3 structural /
                                  Q4 information-loss)
    5. Write results/<lib>_round_trip.json

Phase 1 validation: this must run end-to-end on wcwidth with ZERO LLM
calls, exit 0, print a 5-line progress log, and emit a JSON file whose
shape matches the documented schema.

Run:
    python benchmarks/round_trip/run_one.py wcwidth
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from decompose_from_reference import decompose_from_reference, DEFAULT_REPOS_ROOT  # noqa: E402
from recompose_from_adrs import recompose_from_adrs  # noqa: E402
from gates import ALL_GATES  # noqa: E402
from metrics import ALL_METRICS  # noqa: E402


DEFAULT_SPEC_DIR = HERE / "spec"
DEFAULT_RECOMPOSED_DIR = HERE / "recomposed"
DEFAULT_RESULTS_DIR = HERE / "results"


def _write_json(path: Path, payload: dict) -> None:
    """UTF-8 + newline='' — Windows→Linux-container safe."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="")


def run_one(
    lib: str,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
    spec_dir: Path = DEFAULT_SPEC_DIR,
    recomposed_dir: Path = DEFAULT_RECOMPOSED_DIR,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    repos_root: Path = DEFAULT_REPOS_ROOT,
) -> dict:
    t0 = time.time()
    original_dir = repos_root / lib

    # 1. Decompose
    decomp = decompose_from_reference(lib, spec_dir, provider, model, repos_root)
    print(f"[1/5] decompose: files_in_spec={decomp['files_in_spec']} "
          f"cost=${decomp['cost_usd']:.4f} elapsed={decomp['elapsed_s']}s")

    # 2. Gates
    lib_spec_dir = spec_dir / lib
    gate_results: dict[str, dict] = {}
    for gate_mod in ALL_GATES:
        r = gate_mod.check(lib_spec_dir, original_dir)
        gate_results[r["gate"]] = {"pass": r.get("pass"), "failures": r.get("failures", [])}
    print(f"[2/5] gates: {len(gate_results)} ran "
          f"({', '.join(gate_results.keys())})")

    # 3. Recompose
    recomp = recompose_from_adrs(lib, spec_dir, recomposed_dir, provider, model)
    print(f"[3/5] recompose: files_emitted={recomp['files_emitted']} "
          f"cost=${recomp['cost_usd']:.4f} elapsed={recomp['elapsed_s']}s")

    # 4. Metrics
    lib_recomp_dir = recomposed_dir / lib
    metric_results: dict[str, dict] = {}
    for metric_mod in ALL_METRICS:
        r = metric_mod.compute(original_dir, lib_recomp_dir, spec_dir=lib_spec_dir)
        metric_results[r["metric"]] = {"value": r.get("value"), "detail": r.get("detail", {})}
    print(f"[4/5] metrics: {len(metric_results)} computed "
          f"({', '.join(metric_results.keys())})")

    # 5. Emit result
    totals = {
        "cost_usd": round(decomp["cost_usd"] + recomp["cost_usd"], 4),
        "elapsed_s": round(time.time() - t0, 3),
    }
    payload = {
        "lib": lib,
        "provider": provider,
        "model": model,
        "decompose": decomp,
        "gates": gate_results,
        "recompose": recomp,
        "metrics": metric_results,
        "totals": totals,
    }
    out_path = results_dir / f"{lib}_round_trip.json"
    _write_json(out_path, payload)
    print(f"[5/5] wrote: {out_path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lib", help="commit0-lite library name (e.g., wcwidth)")
    parser.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--repos-root", type=Path, default=DEFAULT_REPOS_ROOT)
    parser.add_argument("--spec-dir", type=Path, default=DEFAULT_SPEC_DIR)
    parser.add_argument("--recomposed-dir", type=Path, default=DEFAULT_RECOMPOSED_DIR)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    args = parser.parse_args()

    run_one(
        args.lib,
        provider=args.provider,
        model=args.model,
        spec_dir=args.spec_dir,
        recomposed_dir=args.recomposed_dir,
        results_dir=args.results_dir,
        repos_root=args.repos_root,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
