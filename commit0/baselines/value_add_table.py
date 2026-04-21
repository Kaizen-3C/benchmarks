"""Per-lib us-vs-them table with model, time, cost, AND
'value-add over the LLM' = each architecture's delta vs the same-model
single-shot baseline (B2).

US:   Kaizen-delta (Sonnet, GPT)
THEM: OpenHands V1 partial (Sonnet, GPT) + their published 7/16 if cited
RAW:  B2 single-shot (Sonnet, GPT)
ITER: B3 Reflexion (Sonnet, GPT)

The value-add column answers: "given this model, what does this
architecture add (or subtract) compared to just calling the model once?"

Run: python benchmarks/commit0/baselines/value_add_table.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS = REPO_ROOT / "benchmarks" / "commit0" / "results"

LIBS = [
    "wcwidth", "deprecated", "cachetools", "voluptuous", "portalocker",
    "pyjwt", "chardet", "tinydb", "simpy", "imapclient", "parsel",
    "marshmallow", "cookiecutter", "babel", "jinja", "minitorch",
]

FLOOR_LIBS = {"chardet", "marshmallow", "babel", "jinja", "minitorch"}


def loadj(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def lib_rate(per_lib: dict, lib: str) -> tuple[float | None, int, int]:
    """Return (rate_pct, passed, attempted) for a lib in a per_library dict."""
    d = per_lib.get(lib, {}) if per_lib else {}
    c = d.get("counts", {})
    p, f, e = c.get("passed", 0), c.get("failed", 0), c.get("errors", 0)
    a = p + f + e
    if a == 0 and not d.get("counts"):
        return (None, 0, 0)  # N/A — wasn't run
    return ((100 * p / a) if a else 0, p, a)


def lib_kaizen(per_lib: dict, lib: str) -> tuple[float | None, int, int, float]:
    """Kaizen-delta: same as lib_rate but also returns cost_usd."""
    d = per_lib.get(lib, {}) if per_lib else {}
    if not d or d.get("missing_per_lib_json"):
        return (None, 0, 0, 0.0)
    c = d.get("counts") or d.get("final_counts") or {}
    p, f, e = c.get("passed", 0), c.get("failed", 0), c.get("errors", 0)
    a = p + f + e
    cost = (d.get("totals") or {}).get("cost_usd", 0)
    return ((100 * p / a) if a else 0, p, a, cost)


def lib_b6(b6_partial: dict | None, lib: str) -> tuple[bool | None, float]:
    """B6: returns (resolved, cost) for a lib. None if lib wasn't in this run."""
    if not b6_partial:
        return (None, 0.0)
    rep = b6_partial.get("report", {})
    rows = b6_partial.get("rows", [])
    if lib not in rep.get("completed_ids", []):
        return (None, 0.0)
    resolved = lib in rep.get("resolved_ids", [])
    # Cost per row
    cost = 0.0
    for r in rows:
        if (r.get("instance_id") or r.get("repo") or "").endswith(lib):
            cost = (r.get("metrics") or {}).get("accumulated_cost", 0)
            break
    return (resolved, cost)


def fmt_rate(r: tuple[float | None, int, int]) -> str:
    rate, p, a = r
    if rate is None:
        return "  --   "
    return f"{rate:>3.0f}% ({p:>3}/{a:<3})"


def fmt_delta(arch_rate: tuple[float | None, int, int],
              base_rate: tuple[float | None, int, int]) -> str:
    if arch_rate[0] is None or base_rate[0] is None:
        return "  --  "
    d = arch_rate[0] - base_rate[0]
    if abs(d) < 0.5:
        return "  ~0  "
    return f"{d:+5.0f}pp"


def main() -> int:
    # Load all aggregates
    b2s = loadj(RESULTS / "aggregate_lite_single_shot_sonnet.json") or {}
    b2g = loadj(RESULTS / "aggregate_lite_single_shot_openai.json") or {}
    b3s = loadj(RESULTS / "aggregate_lite_reflexion_sonnet.json") or {}
    b3g = loadj(RESULTS / "aggregate_lite_reflexion_openai.json") or {}
    kds = loadj(RESULTS / "aggregate_lite_kaizen_delta_anthropic.json") or {}
    # Kaizen-delta aggregate may not exist yet; fall back to per-lib JSONs
    if not kds.get("per_library"):
        per_lib = {}
        for lib in LIBS:
            p = RESULTS / f"{lib}_kaizen_delta_anthropic.json"
            if p.exists():
                d = json.loads(p.read_text())
                if "final_counts" in d:
                    d["counts"] = d["final_counts"]
                per_lib[lib] = d
        kds = {"per_library": per_lib}

    # B6 partials
    def load_b6_dir(name: str) -> dict | None:
        d = RESULTS / name
        if not d.is_dir(): return None
        jsonl = d / "output.jsonl"
        report = d / "output.report.json"
        if not jsonl.exists() or not report.exists(): return None
        rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        rep = json.loads(report.read_text())
        return {"rows": rows, "report": rep}
    b6s = load_b6_dir("b6_partial_pass1")
    b6g = load_b6_dir("b6_partial_gpt54_3libs")

    # ------- Table 1: Per-lib pass rate, including value-add deltas -------
    print("=" * 130)
    print("US-vs-THEM per-lib pass rates with value-add over the LLM")
    print("=" * 130)
    print(f"{'lib':12} {'F?':>2} | {'B2-S':>10} | {'B2-G':>10} || "
          f"{'B3-S':>10} {'d_pp':>6} | {'B3-G':>10} {'d_pp':>6} || "
          f"{'B6-S':>6} {'d_pp':>6} | {'B6-G':>6} {'d_pp':>6} || "
          f"{'KD-S':>10} {'d_pp':>6}")
    print("-" * 130)
    for lib in LIBS:
        floor = "*" if lib in FLOOR_LIBS else " "
        r2s = lib_rate(b2s.get("per_library", {}), lib)
        r2g = lib_rate(b2g.get("per_library", {}), lib)
        r3s = lib_rate(b3s.get("per_library", {}), lib)
        r3g = lib_rate(b3g.get("per_library", {}), lib)
        rkds = lib_kaizen(kds.get("per_library", {}), lib)
        b6s_res, _ = lib_b6(b6s, lib)
        b6g_res, _ = lib_b6(b6g, lib)

        def b6_cell(res: bool | None, base: tuple[float | None, int, int]) -> tuple[str, str]:
            if res is None:
                return ("  --  ", "  --  ")
            tag = "RES" if res else "NO "
            base_resolved = base[0] is not None and base[0] >= 99.5  # B2 resolved if 100%
            d_inst = (1 if res else 0) - (1 if base_resolved else 0)
            return (tag, f"{d_inst:+2d}    ")

        b6s_tag, b6s_d = b6_cell(b6s_res, r2s)
        b6g_tag, b6g_d = b6_cell(b6g_res, r2g)
        kd_rate = (rkds[0], rkds[1], rkds[2])

        print(f"{lib:12} {floor:>2} | {fmt_rate(r2s):>10} | {fmt_rate(r2g):>10} || "
              f"{fmt_rate(r3s):>10} {fmt_delta(r3s, r2s):>6} | "
              f"{fmt_rate(r3g):>10} {fmt_delta(r3g, r2g):>6} || "
              f"{b6s_tag:>6} {b6s_d:>6} | {b6g_tag:>6} {b6g_d:>6} || "
              f"{fmt_rate(kd_rate):>10} {fmt_delta(kd_rate, r2s):>6}")

    print("-" * 130)
    print("F?   = floor lib (*) = none of B2/B3 produces working code on either model")
    print("B2-S = single-shot Sonnet 4.6   B2-G = single-shot GPT-5.4")
    print("B3-S = Reflexion-on-Sonnet      B3-G = Reflexion-on-GPT-5.4")
    print("B6-S = OpenHands V1 + Sonnet (RES=resolved 100%, NO=ran but unresolved, --=not run)")
    print("KD-S = Kaizen-delta + Sonnet (per-file decompose+recompose with pytest grounding)")
    print("d_pp = value-add over single-shot of SAME MODEL (architectural delta in pp)")

    # ------- Table 2: Cost & time per architecture (aggregate) -------
    print()
    print("=" * 100)
    print("US-vs-THEM aggregates: cost, time, $/test, $/resolved-instance")
    print("=" * 100)
    print(f"{'baseline':30} {'libs':>5} {'agg%':>6} {'inst':>5} {'cost':>9} "
          f"{'$/test':>9} {'$/inst':>9} {'wall(s)':>8}")
    print("-" * 100)

    def agg_row(label: str, data: dict, model: str = "?"):
        if not data or not data.get("aggregate"):
            return
        a = data["aggregate"]
        p = a.get("tests_passed", 0)
        attempted = a.get("tests_attempted_total", 0)
        rate = (100 * p / attempted) if attempted else 0
        c = a.get("cost_usd_estimate", 0)
        per_lib = data.get("per_library", {})
        instances = sum(1 for lib_data in per_lib.values()
                        if (lib_data.get("counts") or {}).get("passed", 0)
                        > 0
                        and (lib_data.get("counts") or {}).get("passed", 0)
                        == (lib_data.get("counts", {}).get("passed", 0)
                            + lib_data.get("counts", {}).get("failed", 0)
                            + lib_data.get("counts", {}).get("errors", 0))
                        and (lib_data.get("counts") or {}).get("failed", 0) == 0
                        and (lib_data.get("counts") or {}).get("errors", 0) == 0)
        wall = a.get("wall_seconds_total", 0)
        per_test = (c / p) if p else float("inf")
        per_inst = (c / instances) if instances else float("inf")
        print(f"{label:30} {len(per_lib):>5} {rate:>5.1f}% {instances:>4}/16 "
              f"${c:>7.2f} ${per_test:>7.4f} "
              f"{('${:>7.2f}'.format(per_inst)) if per_inst != float('inf') else '   n/a   ':>9} "
              f"{wall:>8.0f}")

    agg_row("B2 single-shot Sonnet", b2s)
    agg_row("B2 single-shot GPT-5.4", b2g)
    agg_row("B3 Reflexion Sonnet", b3s)
    agg_row("B3 Reflexion GPT-5.4", b3g)
    agg_row("Kaizen-delta Sonnet (partial)", kds)

    # B6 partials separately
    def b6_row(label: str, partial: dict | None):
        if not partial: return
        rep = partial["report"]
        rows = partial["rows"]
        cost = sum((r.get("metrics") or {}).get("accumulated_cost", 0) for r in rows)
        completed = rep.get("completed_instances", 0)
        resolved = rep.get("resolved_instances", 0)
        passed = rep.get("total_passed_tests", 0)
        attempted = rep.get("total_tests", 0)
        rate = (100 * passed / attempted) if attempted else 0
        per_test = (cost / passed) if passed else float("inf")
        per_inst = (cost / resolved) if resolved else float("inf")
        print(f"{label:30} {completed:>5} {rate:>5.1f}% {resolved:>4}/16 "
              f"${cost:>7.2f} ${per_test:>7.4f} "
              f"{('${:>7.2f}'.format(per_inst)) if per_inst != float('inf') else '   n/a   ':>9} "
              f"{'   n/a':>8}")

    b6_row("B6 OpenHands Sonnet (3-lib)", b6s)
    b6_row("B6 OpenHands GPT-5.4 (3-lib)", b6g)

    # ------- Table 3: Architectural value-add summary -------
    print()
    print("=" * 100)
    print("ARCHITECTURAL VALUE-ADD: each architecture's aggregate delta vs same-model single-shot")
    print("=" * 100)
    print(f"{'architecture':35} {'agg delta vs B2-same-model':>28} {'cost ratio':>12}")
    print("-" * 100)

    def agg_pct(d): return ((d.get("aggregate", {}) or {}).get("pass_rate_attempted", 0) * 100) if d else 0
    def agg_cost(d): return (d.get("aggregate", {}) or {}).get("cost_usd_estimate", 0) if d else 0

    b2s_pct, b2g_pct = agg_pct(b2s), agg_pct(b2g)
    b2s_cost, b2g_cost = agg_cost(b2s), agg_cost(b2g)

    if b3s:
        d_pp = agg_pct(b3s) - b2s_pct
        d_x = (agg_cost(b3s) / b2s_cost) if b2s_cost else 0
        print(f"{'B3 Reflexion (Sonnet)':35} {d_pp:>+20.1f} pp  vs B2-S  {d_x:>10.1f}x")
    if b3g:
        d_pp = agg_pct(b3g) - b2g_pct
        d_x = (agg_cost(b3g) / b2g_cost) if b2g_cost else 0
        print(f"{'B3 Reflexion (GPT-5.4)':35} {d_pp:>+20.1f} pp  vs B2-G  {d_x:>10.1f}x")
    if kds.get("per_library"):
        # Compare on whatever libs Kaizen-delta has data for
        kd_libs = list(kds["per_library"].keys())
        kd_total_p = sum(((kds["per_library"][l].get("counts") or kds["per_library"][l].get("final_counts") or {}).get("passed", 0))
                         for l in kd_libs)
        kd_total_a = sum(sum(((kds["per_library"][l].get("counts") or kds["per_library"][l].get("final_counts") or {}).get(k, 0))
                             for k in ("passed", "failed", "errors"))
                         for l in kd_libs)
        kd_pct = (100 * kd_total_p / kd_total_a) if kd_total_a else 0
        # Same-libs B2-S
        b2s_pl = b2s.get("per_library", {})
        b2_subset_p = sum((b2s_pl.get(l, {}).get("counts") or {}).get("passed", 0) for l in kd_libs)
        b2_subset_a = sum(sum((b2s_pl.get(l, {}).get("counts") or {}).get(k, 0) for k in ("passed", "failed", "errors"))
                          for l in kd_libs)
        b2_subset_pct = (100 * b2_subset_p / b2_subset_a) if b2_subset_a else 0
        d_pp = kd_pct - b2_subset_pct
        kd_cost = sum((kds["per_library"][l].get("totals") or {}).get("cost_usd", 0) for l in kd_libs)
        b2_subset_cost = sum((b2s_pl.get(l, {}).get("input_tokens", 0) * 3
                              + b2s_pl.get(l, {}).get("output_tokens", 0) * 15) / 1_000_000
                             for l in kd_libs)
        d_x = (kd_cost / b2_subset_cost) if b2_subset_cost else 0
        print(f"{'Kaizen-delta (Sonnet, %d-lib)' % len(kd_libs):35} {d_pp:>+20.1f} pp  vs B2-S  {d_x:>10.1f}x")

    if b6s:
        # B6: instance-level. delta = resolved-by-B6 - resolved-by-B2-on-same-libs
        rep = b6s["report"]
        ran = rep.get("completed_ids", [])
        b6_resolved = rep.get("resolved_instances", 0)
        b2_resolved_same = sum(1 for l in ran if (b2s.get("per_library", {}).get(l, {}).get("counts") or {}).get("failed", 1) == 0
                               and (b2s.get("per_library", {}).get(l, {}).get("counts") or {}).get("errors", 1) == 0
                               and (b2s.get("per_library", {}).get(l, {}).get("counts") or {}).get("passed", 0) > 0)
        b6_cost = sum((r.get("metrics") or {}).get("accumulated_cost", 0) for r in b6s["rows"])
        b2_subset_cost = sum((b2s.get("per_library", {}).get(l, {}).get("input_tokens", 0) * 3
                              + b2s.get("per_library", {}).get(l, {}).get("output_tokens", 0) * 15) / 1_000_000
                             for l in ran)
        d_inst = b6_resolved - b2_resolved_same
        d_x = (b6_cost / b2_subset_cost) if b2_subset_cost else 0
        print(f"{'B6 OpenHands V1 (Sonnet, %d-lib)' % len(ran):35} {('+%d instances' % d_inst):>23}  vs B2-S  {d_x:>10.1f}x")
    if b6g:
        rep = b6g["report"]
        ran = rep.get("completed_ids", [])
        b6_resolved = rep.get("resolved_instances", 0)
        b2g_resolved_same = sum(1 for l in ran if (b2g.get("per_library", {}).get(l, {}).get("counts") or {}).get("failed", 1) == 0
                                and (b2g.get("per_library", {}).get(l, {}).get("counts") or {}).get("errors", 1) == 0
                                and (b2g.get("per_library", {}).get(l, {}).get("counts") or {}).get("passed", 0) > 0)
        b6_cost = sum((r.get("metrics") or {}).get("accumulated_cost", 0) for r in b6g["rows"])
        b2_subset_cost = sum((b2g.get("per_library", {}).get(l, {}).get("input_tokens", 0) * 1.25
                              + b2g.get("per_library", {}).get(l, {}).get("output_tokens", 0) * 10) / 1_000_000
                             for l in ran)
        d_inst = b6_resolved - b2g_resolved_same
        d_x = (b6_cost / b2_subset_cost) if b2_subset_cost else 0
        print(f"{'B6 OpenHands V1 (GPT-5.4, %d-lib)' % len(ran):35} {('+%d instances' % d_inst):>23}  vs B2-G  {d_x:>10.1f}x")

    return 0


if __name__ == "__main__":
    sys.exit(main())
