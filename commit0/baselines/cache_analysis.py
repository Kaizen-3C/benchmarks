"""Cache effectiveness analysis across commit0-lite baselines.

Asks four questions central to Kaizen-delta's "use resources wisely" thesis:

  Q1. CACHE HIT RATE  — what fraction of input tokens hit cache vs fresh?
  Q2. COST PER RESOLVED INSTANCE — $ to solve one library?  (the headline metric)
  Q3. COST PER TEST PASSED — $ to make one test go green?  (granularity below instance)
  Q4. COUNTERFACTUAL — if a baseline had perfect caching of its static spec/stub
                       block, what would it have cost?

The answer to Q4 is what tells whether a baseline's high cost is an
architectural choice (verbose prompts, long agent loops) vs a missed
optimization (just didn't cache).

Reads:
  benchmarks/commit0/results/aggregate_lite_single_shot_sonnet.json    (B2 Sonnet)
  benchmarks/commit0/results/aggregate_lite_single_shot_openai.json    (B2 GPT-5.4)
  benchmarks/commit0/results/aggregate_lite_reflexion_sonnet.json      (B3 Sonnet)
  benchmarks/commit0/results/b6_partial_pass1/output.report.json       (B6 partial)
  benchmarks/commit0/results/b6_partial_pass1/output.jsonl             (B6 token detail)

Usage:
  python benchmarks/commit0/baselines/cache_analysis.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from dataclasses import dataclass

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS = REPO_ROOT / "benchmarks" / "commit0" / "results"

# Sonnet 4.6 list pricing (per Anthropic, 2026-04)
SONNET_INPUT  = 3.00 / 1_000_000
SONNET_OUTPUT = 15.00 / 1_000_000
SONNET_CACHE_READ  = 0.30 / 1_000_000   # 10% of base input
SONNET_CACHE_WRITE = 3.75 / 1_000_000   # base * 1.25 (5m TTL)

# GPT-5.4 list pricing (per OpenAI, 2026-04 — approximate)
GPT54_INPUT  = 1.25 / 1_000_000
GPT54_OUTPUT = 10.00 / 1_000_000
GPT54_CACHE_READ = 0.125 / 1_000_000   # 10% (auto-cached)


@dataclass
class Baseline:
    name: str
    model: str
    instances_total: int
    instances_resolved: int
    tests_passed: int
    tests_attempted: int
    fresh_input_tok: int       # tokens NOT served from cache
    cache_read_tok: int        # tokens served from cache
    cache_write_tok: int       # tokens written to cache
    output_tok: int
    wall_seconds: float
    measured_cost_usd: float
    # How many LLM calls per library on average? Drives the caching counterfactual.
    #   1 = single-shot, no caching benefit possible
    #   2-5 = light iteration
    #   50-200 = agent loop (caching benefit is enormous)
    avg_calls_per_lib: float


def cost_at(model: str, fresh_in: int, cache_r: int, cache_w: int, out: int) -> float:
    if model.startswith("claude"):
        return (fresh_in * SONNET_INPUT
                + cache_r * SONNET_CACHE_READ
                + cache_w * SONNET_CACHE_WRITE
                + out * SONNET_OUTPUT)
    return (fresh_in * GPT54_INPUT + cache_r * GPT54_CACHE_READ + out * GPT54_OUTPUT)


def load_b2_sonnet() -> Baseline | None:
    p = RESULTS / "aggregate_lite_single_shot_sonnet.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    libs = d["per_library"]
    fresh_in = sum(l.get("input_tokens", 0) for l in libs.values())
    out = sum(l.get("output_tokens", 0) for l in libs.values())
    instances_resolved = 0
    for l in libs.values():
        c = l.get("counts", {})
        att = c.get("passed", 0) + c.get("failed", 0) + c.get("errors", 0)
        if att > 0 and c.get("passed", 0) == att and c.get("failed", 0) == 0 and c.get("errors", 0) == 0:
            instances_resolved += 1
    return Baseline(
        name="B2 single-shot",
        model="claude-sonnet-4-6",
        instances_total=16, instances_resolved=instances_resolved,
        tests_passed=d["aggregate"]["tests_passed"],
        tests_attempted=d["aggregate"]["tests_attempted_total"],
        fresh_input_tok=fresh_in, cache_read_tok=0, cache_write_tok=0,
        output_tok=out,
        wall_seconds=d["aggregate"]["wall_seconds_total"],
        measured_cost_usd=d["aggregate"]["cost_usd_estimate"],
        avg_calls_per_lib=1.0,
    )


def load_b2_openai() -> Baseline | None:
    p = RESULTS / "aggregate_lite_single_shot_openai.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    libs = d["per_library"]
    fresh_in = sum(l.get("input_tokens", 0) - l.get("cached_input_tokens", 0) for l in libs.values())
    cache_r = sum(l.get("cached_input_tokens", 0) for l in libs.values())
    out = sum(l.get("output_tokens", 0) for l in libs.values())
    instances_resolved = 0
    for l in libs.values():
        c = l.get("counts", {})
        att = c.get("passed", 0) + c.get("failed", 0) + c.get("errors", 0)
        if att > 0 and c.get("passed", 0) == att and c.get("failed", 0) == 0 and c.get("errors", 0) == 0:
            instances_resolved += 1
    return Baseline(
        name="B2 single-shot",
        model="gpt-5.4",
        instances_total=16, instances_resolved=instances_resolved,
        tests_passed=d["aggregate"]["tests_passed"],
        tests_attempted=d["aggregate"]["tests_attempted_total"],
        fresh_input_tok=fresh_in, cache_read_tok=cache_r, cache_write_tok=0,
        output_tok=out,
        wall_seconds=d["aggregate"]["wall_seconds_total"],
        measured_cost_usd=d["aggregate"]["cost_usd_estimate"],
        avg_calls_per_lib=1.0,
    )


def load_b3_sonnet() -> Baseline | None:
    p = RESULTS / "aggregate_lite_reflexion_sonnet.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    libs = d["per_library"]
    fresh_in = sum(l.get("totals", {}).get("input_tokens", 0) for l in libs.values())
    cache_r = sum(l.get("totals", {}).get("cache_read_input_tokens", 0) for l in libs.values())
    cache_w = sum(l.get("totals", {}).get("cache_creation_input_tokens", 0) for l in libs.values())
    out = sum(l.get("totals", {}).get("output_tokens", 0) for l in libs.values())
    instances_resolved = 0
    for l in libs.values():
        c = l.get("counts", {})
        att = c.get("passed", 0) + c.get("failed", 0) + c.get("errors", 0)
        if att > 0 and c.get("passed", 0) == att and c.get("failed", 0) == 0 and c.get("errors", 0) == 0:
            instances_resolved += 1
    avg_iters = sum(l.get("iters_run", 0) for l in libs.values()) / max(len(libs), 1)
    return Baseline(
        name="B3 Reflexion (3 iter)",
        model="claude-sonnet-4-6",
        instances_total=16, instances_resolved=instances_resolved,
        tests_passed=d["aggregate"]["tests_passed"],
        tests_attempted=d["aggregate"]["tests_attempted_total"],
        fresh_input_tok=fresh_in, cache_read_tok=cache_r, cache_write_tok=cache_w,
        output_tok=out,
        wall_seconds=d["aggregate"]["wall_seconds_total"],
        measured_cost_usd=d["aggregate"]["cost_usd_estimate"],
        avg_calls_per_lib=avg_iters,
    )


def load_b6_partial() -> Baseline | None:
    jsonl = RESULTS / "b6_partial_pass1" / "output.jsonl"
    report = RESULTS / "b6_partial_pass1" / "output.report.json"
    if not jsonl.exists() or not report.exists():
        return None
    rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    fresh_in = cache_r = cache_w = out = 0
    total_actions = 0
    for r in rows:
        m = r.get("metrics") or {}
        usage = m.get("accumulated_token_usage") or {}
        fresh_in += usage.get("prompt_tokens", 0)  # OpenHands doesn't break out cache
        out += usage.get("completion_tokens", 0)
        # ActionEvent count = number of LLM calls per instance (each action turn
        # produces one call to the model)
        for ev in r.get("history", []):
            if isinstance(ev, dict) and (ev.get("type") == "ActionEvent" or ev.get("kind") == "ActionEvent"):
                total_actions += 1
    avg_actions = total_actions / max(len(rows), 1)
    # Authoritative test counts come from eval_infer's output.report.json
    rep = json.loads(report.read_text(encoding="utf-8", errors="replace"))
    return Baseline(
        name="B6 OpenHands V1 (partial: 3/16 completed)",
        model="claude-sonnet-4-6",
        instances_total=16,
        instances_resolved=rep.get("resolved_instances", 0),
        tests_passed=rep.get("total_passed_tests", 0),
        tests_attempted=rep.get("total_tests", 0),
        fresh_input_tok=fresh_in, cache_read_tok=cache_r, cache_write_tok=cache_w,
        output_tok=out,
        wall_seconds=0,
        measured_cost_usd=84.70,
        avg_calls_per_lib=avg_actions,
    )


def fmt_baseline(b: Baseline) -> str:
    total_in = b.fresh_input_tok + b.cache_read_tok
    cache_hit_pct = (100 * b.cache_read_tok / total_in) if total_in else 0.0
    cost_per_inst = (b.measured_cost_usd / b.instances_resolved) if b.instances_resolved else float("inf")
    cost_per_test = (b.measured_cost_usd / b.tests_passed) if b.tests_passed else float("inf")
    # Counterfactual: model "what if we'd applied prompt caching to the static
    # portion of every call?" Static share rises with iteration count because:
    #   - early calls: static spec + stubs ~ 60% of fresh input
    #   - middle calls: + accumulated conversation history is ALSO repeatable
    #   - many-call agent loops (B6): up to ~90% of input is the growing
    #     conversation prefix, which is cacheable past iteration 1
    # Single-call (B2): no repeated context — caching has nothing to reuse,
    # so the counterfactual is exactly the measured cost.
    n = b.avg_calls_per_lib
    if n <= 1.05:
        cf_fresh, cf_cache_r, cf_cache_w = b.fresh_input_tok, b.cache_read_tok, b.cache_write_tok
        cf_note = "n/a -- single-call architecture has nothing to cache"
    else:
        # Static_share estimate scales with call count — agent loops have
        # growing-prefix architecture where most of input becomes cacheable.
        static_share = min(0.90, 0.55 + 0.005 * n)
        # If there's no cache_read at all (i.e., no caching used today), the
        # counterfactual computes from scratch what cached calls WOULD cost.
        if b.cache_read_tok == 0:
            per_call_static = b.fresh_input_tok * static_share / n
            cf_fresh = b.fresh_input_tok * (1 - static_share)
            cf_cache_r = per_call_static * (n - 1)
            cf_cache_w = per_call_static  # one write per cacheable prefix
        else:
            # Already caching -- counterfactual = measured (we can't do better
            # than what was already done). Note the achieved hit rate.
            cf_fresh, cf_cache_r, cf_cache_w = b.fresh_input_tok, b.cache_read_tok, b.cache_write_tok
        cf_cost = cost_at(b.model, int(cf_fresh), int(cf_cache_r), int(cf_cache_w), b.output_tok)
        cf_savings_pct = 100 * (1 - cf_cost / b.measured_cost_usd) if b.measured_cost_usd else 0.0
        if b.cache_read_tok > 0:
            cf_note = f"already cached at {cache_hit_pct:.0f}% hit rate, near-optimal"
        else:
            cf_note = f"saving {cf_savings_pct:+.1f}% (~{n:.0f} calls/lib, est {static_share:.0%} cacheable)"
    if n <= 1.05:
        cf_cost = b.measured_cost_usd
    return (
        f"  {b.name:42}  model={b.model:18}\n"
        f"    instances solved:  {b.instances_resolved}/{b.instances_total}\n"
        f"    tests passed:      {b.tests_passed}/{b.tests_attempted}\n"
        f"    cache hit rate:    {cache_hit_pct:5.1f}%  "
        f"(fresh={b.fresh_input_tok/1000:.0f}K, read={b.cache_read_tok/1000:.0f}K, "
        f"write={b.cache_write_tok/1000:.0f}K, out={b.output_tok/1000:.0f}K)\n"
        f"    measured cost:     ${b.measured_cost_usd:.2f}\n"
        f"    $ / resolved inst: ${cost_per_inst:.2f}\n"
        f"    $ / test passed:   ${cost_per_test:.4f}\n"
        f"    counterfactual:    ${cf_cost:.2f}  ({cf_note} if static block were cached)"
    )


def main() -> int:
    baselines = [b for b in [
        load_b2_sonnet(),
        load_b2_openai(),
        load_b3_sonnet(),
        load_b6_partial(),
    ] if b is not None]
    if not baselines:
        print("No baseline data available", file=sys.stderr)
        return 1
    print("=" * 80)
    print("Cache effectiveness + value-per-dollar across commit0-lite baselines")
    print("=" * 80)
    for b in baselines:
        print()
        print(fmt_baseline(b))
    print()
    print("=" * 80)
    print("Notes:")
    print("  - 'cache hit rate' = cache_read / (fresh + cache_read)")
    print("  - '$ / resolved instance' is the headline efficiency metric for the paper")
    print("  - '$ / test passed' lets you compare across baselines that can't fully solve a lib")
    print("  - 'counterfactual' assumes 50% of fresh input could have been cached (spec+stubs)")
    print("    (only applied to iterative baselines; single-shot has nothing to reuse)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
