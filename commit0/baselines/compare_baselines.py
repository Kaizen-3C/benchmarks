"""Compare commit0-lite baselines and quantify the marginal value of each
architectural addition over raw LLM capability.

Reads:
  benchmarks/commit0/results/aggregate_lite_single_shot_sonnet.json   (B2)
  benchmarks/commit0/results/aggregate_lite_reflexion_sonnet.json     (B3)
  benchmarks/commit0/baselines/openhands_v1115/.../aggregate.json     (B6, when available)

Reports a table answering:

  - LLM raw (B2)             : what does the model alone do?
  - + iteration loop (B3)    : what does naive iteration buy?
  - + tools (B6 - B3)        : what does tool use buy on top?
  - vs. cost / time / tokens : how much do those gains cost?

The same framing will later apply to Kaizen-delta:

  - + decomposition (B5 - B6): what does ADR-driven decomposition buy on top?

Usage: python compare_baselines.py [--openhands-aggregate PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS = REPO_ROOT / "benchmarks" / "commit0" / "results"

LITE = [
    "wcwidth", "deprecated", "cachetools", "voluptuous", "portalocker",
    "pyjwt", "chardet", "tinydb", "simpy", "imapclient", "parsel",
    "marshmallow", "cookiecutter", "babel", "jinja", "minitorch",
]


def load_b2() -> dict | None:
    p = RESULTS / "aggregate_lite_single_shot_sonnet.json"
    return json.loads(p.read_text()) if p.exists() else None


def load_b3() -> dict | None:
    p = RESULTS / "aggregate_lite_reflexion_sonnet.json"
    return json.loads(p.read_text()) if p.exists() else None


def load_b6(path: Path | None) -> dict | None:
    if path is None:
        return None
    p = Path(path) if Path(path).is_absolute() else REPO_ROOT / path
    return json.loads(p.read_text()) if p.exists() else None


def b2_per_lib_passrate(b2: dict) -> dict[str, dict]:
    """Return {lib: {passed, attempted, instance_solved}}."""
    out = {}
    for lib in LITE:
        d = (b2.get("per_library") or {}).get(lib, {})
        c = d.get("counts", {})
        passed = c.get("passed", 0)
        failed = c.get("failed", 0)
        errors = c.get("errors", 0)
        attempted = passed + failed + errors
        out[lib] = {
            "passed": passed,
            "attempted": attempted,
            "rate": (passed / attempted) if attempted else 0.0,
            "instance_solved": (attempted > 0 and passed == attempted and failed == 0 and errors == 0),
            "input_tokens": d.get("input_tokens", 0),
            "output_tokens": d.get("output_tokens", 0),
            "elapsed_s": d.get("elapsed_s", 0),
        }
    return out


def b3_per_lib_passrate(b3: dict) -> dict[str, dict]:
    """B3's best-iter result; aggregates token totals across iterations."""
    out = {}
    for lib in LITE:
        d = (b3.get("per_library") or {}).get(lib, {})
        c = d.get("counts", {})
        passed = c.get("passed", 0)
        failed = c.get("failed", 0)
        errors = c.get("errors", 0)
        attempted = passed + failed + errors
        totals = d.get("totals", {})
        out[lib] = {
            "passed": passed,
            "attempted": attempted,
            "rate": (passed / attempted) if attempted else 0.0,
            "instance_solved": (attempted > 0 and passed == attempted and failed == 0 and errors == 0),
            "input_tokens": totals.get("input_tokens", 0),
            "output_tokens": totals.get("output_tokens", 0),
            "cache_read": totals.get("cache_read_input_tokens", 0),
            "cache_write": totals.get("cache_creation_input_tokens", 0),
            "elapsed_s": totals.get("elapsed_s", 0),
            "iters_run": d.get("iters_run", 0),
        }
    return out


def b6_per_lib_passrate(b6: dict) -> dict[str, dict]:
    """OpenHands V1 result. Uses pass1 only (variance handled separately)."""
    out = {}
    pass1 = (b6.get("per_pass_per_lib") or {}).get("pass1") or {}
    for lib in LITE:
        # OpenHands keys may be "instance_id" or "repo" — try both.
        d = pass1.get(lib) or pass1.get(f"commit-0/{lib}") or {}
        report = d.get("report") or {}
        m = d.get("metrics") or {}
        # `report` has e.g. {"resolved": True} or pytest counts.
        resolved = bool(report.get("resolved"))
        passed = report.get("passed_tests") or report.get("num_passed") or 0
        failed = report.get("failed_tests") or report.get("num_failed") or 0
        errors = report.get("errored_tests") or report.get("num_errors") or 0
        attempted = passed + failed + errors
        out[lib] = {
            "passed": passed,
            "attempted": attempted,
            "rate": (passed / attempted) if attempted else 0.0,
            "instance_solved": resolved,
            "input_tokens": m.get("input_tokens") or 0,
            "output_tokens": m.get("output_tokens") or 0,
            "cache_read": m.get("cache_read_tokens") or 0,
            "cache_write": m.get("cache_write_tokens") or 0,
            "elapsed_s": d.get("wall_seconds") or 0,
            "n_steps": d.get("n_steps") or 0,
            "cost_usd": m.get("total_cost") or 0,
        }
    return out


def cost_usd(p: dict, *, cache_aware: bool = True) -> float:
    """Sonnet 4.6 list price."""
    return (
        p.get("input_tokens", 0) * 3 / 1_000_000
        + p.get("output_tokens", 0) * 15 / 1_000_000
        + (p.get("cache_read", 0) * 0.30 / 1_000_000 if cache_aware else 0)
        + (p.get("cache_write", 0) * 3.75 / 1_000_000 if cache_aware else 0)
    )


def aggregate(per_lib: dict[str, dict]) -> dict:
    libs = list(per_lib.values())
    p = sum(l.get("passed", 0) for l in libs)
    a = sum(l.get("attempted", 0) for l in libs)
    instances = sum(1 for l in libs if l.get("instance_solved"))
    cost = sum(cost_usd(l) for l in libs) + sum(l.get("cost_usd", 0) for l in libs if "cost_usd" in l)
    # Avoid double-counting: if cost_usd present, prefer it; else compute from tokens.
    cost = sum(l["cost_usd"] if l.get("cost_usd") else cost_usd(l) for l in libs)
    return {
        "instances_solved": instances,
        "instances_total": len(libs),
        "instance_rate": instances / len(libs) if libs else 0,
        "tests_passed": p,
        "tests_attempted": a,
        "aggregate_pass_rate": (p / a) if a else 0,
        "input_tokens": sum(l.get("input_tokens", 0) for l in libs),
        "output_tokens": sum(l.get("output_tokens", 0) for l in libs),
        "cache_read": sum(l.get("cache_read", 0) for l in libs),
        "cache_write": sum(l.get("cache_write", 0) for l in libs),
        "wall_seconds": sum(l.get("elapsed_s", 0) for l in libs),
        "cost_usd_estimate": round(cost, 2),
    }


def fmt_row(label: str, agg: dict) -> str:
    return (
        f"{label:30}  "
        f"inst {agg['instances_solved']:>2}/{agg['instances_total']:<2}  "
        f"agg {100*agg['aggregate_pass_rate']:>5.1f}%  "
        f"in_tok {agg['input_tokens']/1000:>7.0f}K  "
        f"out_tok {agg['output_tokens']/1000:>5.0f}K  "
        f"sec {agg['wall_seconds']:>5.0f}  "
        f"$ {agg['cost_usd_estimate']:>6.2f}"
    )


def fmt_delta(label: str, ref: dict, cmp: dict) -> str:
    d_inst = cmp["instances_solved"] - ref["instances_solved"]
    d_agg = 100 * (cmp["aggregate_pass_rate"] - ref["aggregate_pass_rate"])
    in_ratio = (cmp["input_tokens"] / ref["input_tokens"]) if ref["input_tokens"] else float("inf")
    out_ratio = (cmp["output_tokens"] / ref["output_tokens"]) if ref["output_tokens"] else float("inf")
    sec_ratio = (cmp["wall_seconds"] / ref["wall_seconds"]) if ref["wall_seconds"] else float("inf")
    cost_ratio = (cmp["cost_usd_estimate"] / ref["cost_usd_estimate"]) if ref["cost_usd_estimate"] else float("inf")
    return (
        f"{label:30}  "
        f"d_inst {d_inst:+d}     "
        f"d_agg {d_agg:+5.1f}pp  "
        f"in_x{in_ratio:>5.1f}   "
        f"out_x{out_ratio:>4.1f}   "
        f"sec_x{sec_ratio:>4.1f}  "
        f"cost_x{cost_ratio:>4.1f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openhands-aggregate", type=str, default=None,
                        help="Path to OpenHands B6 aggregate.json (in WSL workspace or repo).")
    args = parser.parse_args()

    b2 = load_b2()
    b3 = load_b3()
    b6 = load_b6(args.openhands_aggregate)

    rows: list[tuple[str, dict]] = []
    if b2:
        rows.append(("B2 single-shot Sonnet 4.6", aggregate(b2_per_lib_passrate(b2))))
    if b3:
        rows.append(("B3 Reflexion-on-Sonnet 4.6", aggregate(b3_per_lib_passrate(b3))))
    if b6:
        rows.append(("B6 OpenHands V1 + Sonnet 4.6", aggregate(b6_per_lib_passrate(b6))))

    if not rows:
        print("No baseline data found. Run B2/B3/B6 first.", file=sys.stderr)
        return 1

    print("=" * 110)
    print(f"{'baseline':30}  {'instances':9}  {'agg':>7}  "
          f"{'in_tok':>10}  {'out_tok':>9}  {'sec':>5}  {'cost':>8}")
    print("-" * 110)
    for label, agg in rows:
        print(fmt_row(label, agg))

    print()
    print("Marginal value of each architectural addition (vs the prior row):")
    print("-" * 110)
    for i in range(1, len(rows)):
        ref_label, ref = rows[i - 1]
        cmp_label, cmp = rows[i]
        delta_label = f"+ {cmp_label.split()[0]} over {ref_label.split()[0]}"
        print(fmt_delta(delta_label, ref, cmp))

    print()
    print("Notes on metrics:")
    print("  inst    = libraries where pytest passes 100% (OpenHands' published metric)")
    print("  agg     = aggregate test pass rate across all 16 libs (our diagnostic)")
    print("  d_agg   = aggregate-pass-rate delta in percentage points")
    print("  in_x    = input-tokens ratio (cmp / ref)")
    print("  cost    = $ at Sonnet 4.6 list price; cache_read $0.30/MTok, cache_write $3.75/MTok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
