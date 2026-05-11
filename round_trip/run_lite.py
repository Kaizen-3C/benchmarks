"""Parallel round-trip pipeline across the 16 commit0-lite libraries.

Per ADR-0063 + the kaizen-delta tool-routing convention:
  - Decompose / Recompose: Sonnet (balanced reasoning)
  - Q1 (pytest):           no LLM
  - Q3 (AST diff):          no LLM
  - Q4 v1 (symbol cov):     no LLM
  - Q4 v2 (line derivability, future): Haiku (simple per-section yes/no)

Concurrency: ThreadPoolExecutor with --workers (default 4). LLM calls are
I/O bound; 4 in-flight per provider sits well within standard rate limits
(verified during the Phase 1 sweep — same pattern as run_lite_aider.py).

Each library's pipeline is the same `run_one.run_one()` we use for one-off
runs. This wrapper just orchestrates and aggregates.

Run:
    python benchmarks/round_trip/run_lite.py \\
        --provider anthropic \\
        --workers 4 \\
        --rerun-dir /mnt/c/RepoEx/Kaizen-3C/benchmarks-private/round_trip-2026-Q3/reruns/2026-05-06_phase2-pilot

Output layout under --rerun-dir:
    spec/<lib>/         (decompose output, regenerable)
    recomposed/<lib>/   (recompose output, regenerable)
    results/<lib>_round_trip.json
    aggregate_round_trip_<provider>.json   (this script's per-run summary)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from run_one import run_one, DEFAULT_REPOS_ROOT  # noqa: E402

# Resolve provider-specific default model when --model isn't passed.
_BASELINES = HERE.parent / "commit0" / "baselines"
if str(_BASELINES) not in sys.path:
    sys.path.insert(0, str(_BASELINES))
from _llm import DEFAULT_MODELS  # noqa: E402

# Same lib order as the commit0-lite paper (PHASE1_COST_REVIEW.md / fingerprint).
LITE_LIBS = (
    "wcwidth", "deprecated", "cachetools", "voluptuous", "portalocker",
    "pyjwt", "chardet", "tinydb", "simpy", "imapclient", "parsel",
    "marshmallow", "cookiecutter", "babel", "jinja", "minitorch",
)


def _aggregate(results: dict[str, dict]) -> dict:
    """Roll-up per-library results into a single summary."""
    libs = list(results.values())
    cost = sum(r.get("totals", {}).get("cost_usd", 0) for r in libs)
    wall = sum(r.get("totals", {}).get("elapsed_s", 0) for r in libs)

    # Gate aggregates: average pass rate per gate across libs.
    gate_names = ("coverage", "specificity", "consistency",
                  "test_oracle_alignment", "implementation_leak")
    gate_pass_counts = {g: 0 for g in gate_names}
    gate_failure_totals = {g: 0 for g in gate_names}
    n_libs_with_gates = 0
    for r in libs:
        gates = r.get("gates", {})
        if not gates:
            continue
        n_libs_with_gates += 1
        for g in gate_names:
            gr = gates.get(g, {})
            if gr.get("pass") is True:
                gate_pass_counts[g] += 1
            gate_failure_totals[g] += len(gr.get("failures", []))

    # Metric aggregates
    metric_names = ("q1_test_parity", "q3_structural_parity", "q4_information_loss")
    metric_means: dict[str, float | None] = {}
    metric_per_lib: dict[str, dict[str, float | None]] = {}
    for m in metric_names:
        values = []
        per_lib: dict[str, float | None] = {}
        for lib, r in results.items():
            v = r.get("metrics", {}).get(m, {}).get("value")
            per_lib[lib] = v
            if isinstance(v, (int, float)):
                values.append(v)
        metric_means[m] = round(sum(values) / len(values), 4) if values else None
        metric_per_lib[m] = per_lib

    return {
        "libs_total": len(libs),
        "libs_with_gates": n_libs_with_gates,
        "cost_usd_total": round(cost, 4),
        "wall_seconds_total": round(wall, 1),
        "gate_pass_counts": gate_pass_counts,
        "gate_failure_totals": gate_failure_totals,
        "metric_means": metric_means,
        "metric_per_lib": metric_per_lib,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    parser.add_argument("--model", default=None)
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel libraries (default 4).")
    parser.add_argument("--repos-root", type=Path, default=DEFAULT_REPOS_ROOT)
    parser.add_argument("--rerun-dir", type=Path, required=True,
                        help="Output dir; spec/, recomposed/, results/ live here.")
    parser.add_argument("--only", nargs="*",
                        help="Run only these libs (default: all 16).")
    parser.add_argument("--skip", nargs="*", default=[],
                        help="Skip these libs.")
    parser.add_argument("--max-cost-usd", type=float, default=20.0,
                        help="Hard ceiling — abort scheduling if cost so far exceeds this.")
    parser.add_argument(
        "--timeout", type=float, default=None,
        help="Per-LLM-call timeout (seconds). Default: LLMClient default (300s). "
             "Raise to 600 for big libs (chardet, jinja, babel).",
    )
    parser.add_argument(
        "--remediate", action="store_true",
        help="Run a single-pass spec amendment loop after gates fire (Phase 3).",
    )
    parser.add_argument(
        "--code-edit-loop", action="store_true",
        help="Run Stage 2 code-editing iteration loop (ADR-0064).",
    )
    parser.add_argument(
        "--code-edit-max-iters", type=int, default=3,
        help="Max iterations for the code-edit loop (default: 3).",
    )
    args = parser.parse_args()

    targets = list(args.only) if args.only else [
        l for l in LITE_LIBS if l not in args.skip
    ]
    if not targets:
        print("ERROR: no target libs after filtering", file=sys.stderr)
        return 2

    rerun_dir: Path = args.rerun_dir.resolve()
    spec_dir = rerun_dir / "spec"
    recomposed_dir = rerun_dir / "recomposed"
    results_dir = rerun_dir / "results"
    for d in (spec_dir, recomposed_dir, results_dir):
        d.mkdir(parents=True, exist_ok=True)

    print(f"[run_lite] {len(targets)} libs · provider={args.provider} · workers={args.workers}")
    print(f"[run_lite] output: {rerun_dir}")
    print(f"[run_lite] cost ceiling: ${args.max_cost_usd:.2f}")
    print()

    t0 = time.time()
    results: dict[str, dict] = {}
    cost_so_far = 0.0
    aborted = False

    resolved_model = args.model or DEFAULT_MODELS[args.provider]

    def _do_one(lib: str) -> tuple[str, dict]:
        return lib, run_one(
            lib,
            provider=args.provider,
            model=resolved_model,
            spec_dir=spec_dir,
            recomposed_dir=recomposed_dir,
            results_dir=results_dir,
            repos_root=args.repos_root,
            timeout=args.timeout,
            remediate_enabled=args.remediate,
            code_edit_loop_enabled=args.code_edit_loop,
            code_edit_max_iters=args.code_edit_max_iters,
        )

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_do_one, lib): lib for lib in targets}
        for fut in as_completed(futs):
            lib = futs[fut]
            try:
                _lib, r = fut.result()
                results[lib] = r
                lib_cost = r.get("totals", {}).get("cost_usd", 0)
                lib_wall = r.get("totals", {}).get("elapsed_s", 0)
                cost_so_far += lib_cost
                m = r.get("metrics", {})
                q1 = m.get("q1_test_parity", {}).get("value")
                q3 = m.get("q3_structural_parity", {}).get("value")
                q4 = m.get("q4_information_loss", {}).get("value")
                gates_pass = sum(
                    1 for g in r.get("gates", {}).values() if g.get("pass") is True
                )
                gates_total = len(r.get("gates", {}))
                print(
                    f"  ✓ {lib:14} q1={q1} q3={q3} q4={q4} "
                    f"gates={gates_pass}/{gates_total} "
                    f"cost=${lib_cost:.3f} wall={lib_wall:.0f}s "
                    f"(running ${cost_so_far:.2f})",
                    flush=True,
                )
                # Cost-cap check (advisory; in-flight calls still complete).
                if cost_so_far >= args.max_cost_usd and not aborted:
                    print(f"  ⚠ cost ceiling ${args.max_cost_usd:.2f} reached; "
                          f"in-flight runs will complete but no new ones.")
                    aborted = True
            except Exception as e:
                print(f"  ✗ {lib:14} ERROR: {type(e).__name__}: {e}", flush=True)
                results[lib] = {"error": f"{type(e).__name__}: {e}"}

    aggregate = _aggregate(results)
    aggregate["wall_seconds_total_actual"] = round(time.time() - t0, 1)
    aggregate["provider"] = args.provider
    aggregate["model"] = resolved_model

    out = {
        "aggregate": aggregate,
        "per_library": {lib: r for lib, r in results.items()},
        "completed": list(results.keys()),
    }
    aggregate_path = rerun_dir / f"aggregate_round_trip_{args.provider}.json"
    aggregate_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    print()
    print("=" * 60)
    print("AGGREGATE")
    print("=" * 60)
    print(f"libs:          {aggregate['libs_total']}")
    print(f"cost total:    ${aggregate['cost_usd_total']:.2f}")
    print(f"wall actual:   {aggregate['wall_seconds_total_actual']:.0f}s "
          f"(sum-of-libs={aggregate['wall_seconds_total']:.0f}s)")
    print(f"gate passes:   {aggregate['gate_pass_counts']}")
    print(f"metric means:  {aggregate['metric_means']}")
    print(f"wrote:         {aggregate_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
