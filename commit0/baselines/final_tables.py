"""Print one nicely-formatted table per (architecture, model) cell.
Format matches user's preferred style: per-lib rows sorted by pass rate desc.
"""
from __future__ import annotations
import json, re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS = REPO_ROOT / "benchmarks" / "commit0" / "results"

LITE = ["wcwidth","deprecated","cachetools","voluptuous","portalocker","pyjwt",
        "chardet","tinydb","simpy","imapclient","parsel","marshmallow",
        "cookiecutter","babel","jinja","minitorch"]


def loadj(p): return json.loads(p.read_text()) if p.exists() else None


def format_table(title: str, agg_summary: str, rows: list[dict]) -> str:
    """rows: [{'lib':..., 'pass':..., 'fail':..., 'err':..., 'rate_str':..., 'tokens':..., 'sec':...}]"""
    out = [title, agg_summary, ""]
    out.append(f"{'lib':12} {'pass':>5} {'fail':>5} {'err':>4} {'rate':>5} {'input tok':>10} {'sec':>5}")
    out.append("-" * 56)
    for r in rows:
        out.append(f"{r['lib']:12} {r['pass']:>5} {r['fail']:>5} {r['err']:>4} "
                   f"{r['rate_str']:>5} {r['tokens']:>10} {r['sec']:>5}")
    return "\n".join(out)


def cells_from_per_lib(per_lib: dict, token_key="input_tokens", elapsed_key="elapsed_s"):
    rows = []
    for lib in LITE:
        d = per_lib.get(lib, {}) or {}
        c = d.get("counts", {}) or d.get("final_counts", {}) or {}
        p, f, e, s = c.get("passed", 0), c.get("failed", 0), c.get("errors", 0), c.get("skipped", 0)
        a = p + f + e
        if d.get("missing") or (a == 0 and not c):
            continue
        rate_str = f"{(100*p/a):.0f}%" if a else "n/a"
        toks = d.get(token_key, 0)
        if not toks and "totals" in d:
            toks = d["totals"].get(token_key, d["totals"].get("input_tokens", 0))
        sec = d.get(elapsed_key, 0)
        if not sec and "totals" in d:
            sec = d["totals"].get(elapsed_key, 0)
        rows.append({"lib": lib, "pass": p, "fail": f, "err": e, "skip": s,
                     "rate_str": rate_str, "rate_num": (100*p/a) if a else -1,
                     "tokens": f"{toks:,}", "sec": int(sec)})
    rows.sort(key=lambda r: -r["rate_num"])
    return rows


def aggregate_summary(d: dict, label: str) -> str:
    a = d.get("aggregate", {})
    p, f, e, s = a.get("tests_passed", 0), a.get("tests_failed", 0), a.get("tests_errored", 0), a.get("tests_skipped", 0)
    att = p + f + e
    rate = (100 * p / att) if att else 0
    cost = a.get("cost_usd_estimate", 0)
    wall = a.get("wall_seconds_total", 0)
    return f"Aggregate: {p:,} passed / {f:,} failed / {e} errors / {s} skipped -> {rate:.2f}% pass-rate. ${cost:.2f}, {wall/60:.0f} min wall."


def main():
    # B2 Sonnet
    d = loadj(RESULTS / "aggregate_lite_single_shot_sonnet.json")
    if d:
        print(format_table(
            "## B2 baseline -- single-shot Sonnet 4.6 on commit0-lite",
            aggregate_summary(d, "B2-S"),
            cells_from_per_lib(d["per_library"])))
        print()

    # B2 GPT-5.4
    d = loadj(RESULTS / "aggregate_lite_single_shot_openai.json")
    if d:
        print(format_table(
            "## B2 baseline -- single-shot GPT-5.4 on commit0-lite",
            aggregate_summary(d, "B2-G"),
            cells_from_per_lib(d["per_library"])))
        print()

    # B3 Sonnet
    d = loadj(RESULTS / "aggregate_lite_reflexion_sonnet.json")
    if d:
        print(format_table(
            "## B3 baseline -- Reflexion-on-Sonnet 4.6 (3 iter) on commit0-lite",
            aggregate_summary(d, "B3-S"),
            cells_from_per_lib(d["per_library"])))
        print()

    # B3 GPT-5.4
    d = loadj(RESULTS / "aggregate_lite_reflexion_openai.json")
    if d:
        print(format_table(
            "## B3 baseline -- Reflexion-on-GPT-5.4 (3 iter) on commit0-lite",
            aggregate_summary(d, "B3-G"),
            cells_from_per_lib(d["per_library"])))
        print()

    # B6 partials combined per provider
    def b6_combined(label, dirs: list[Path]):
        rows = []
        total_cost, total_passed, total_attempted = 0, 0, 0
        for partial_dir in dirs:
            jsonl = partial_dir / "output.jsonl"
            report = partial_dir / "output.report.json"
            if not jsonl.exists() or not report.exists(): continue
            rep = json.loads(report.read_text())
            for r in [json.loads(l) for l in jsonl.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]:
                instance = r.get("instance_id") or r.get("repo") or "?"
                lib = instance.split("/")[-1] if "/" in instance else instance
                m = r.get("metrics") or {}
                usage = m.get("accumulated_token_usage") or {}
                cost = m.get("accumulated_cost", 0)
                # Per-instance test counts
                resolved = lib in rep.get("resolved_ids", [])
                # No per-instance test breakdown in the report, but we can use the report's totals
                # divided by completed_instances as an approximation (or just show resolved status)
                # For honesty, leave per-test counts blank and show resolved
                rows.append({
                    "lib": lib, "pass": "RES" if resolved else "no",
                    "fail": "-", "err": "-", "skip": "-",
                    "rate_str": "100%" if resolved else "-",
                    "rate_num": 100 if resolved else -1,
                    "tokens": f"{usage.get('prompt_tokens', 0):,}",
                    "sec": int(r.get("duration", 0) or 0),
                })
                total_cost += cost
                total_attempted += 1
                if resolved: total_passed += 1
        rows.sort(key=lambda r: (0 if r["pass"] == "RES" else 1, r["lib"]))
        out = [f"## {label}"]
        out.append(f"Aggregate (partial): {total_passed} resolved / {total_attempted} completed instances. "
                   f"${total_cost:.2f} total spend.")
        out.append("")
        out.append(f"{'lib':12} {'state':>5} {'fail':>5} {'err':>4} {'rate':>5} {'input tok':>10} {'sec':>5}")
        out.append("-" * 56)
        for r in rows:
            out.append(f"{r['lib']:12} {r['pass']:>5} {r['fail']:>5} {r['err']:>4} "
                       f"{r['rate_str']:>5} {r['tokens']:>10} {r['sec']:>5}")
        out.append("Note: B6 reports per-instance resolved/unresolved (100% test pass = RES).")
        out.append("Per-test counts not broken out by report -- see ../results/b6_*/output.report.json")
        return "\n".join(out)

    print(b6_combined(
        "B6 baseline -- OpenHands V1 + Sonnet 4.6 (PARTIAL: only 7 of 16 libs ran)",
        [RESULTS / "b6_partial_pass1", RESULTS / "b6_4cheap_sonnet"]))
    print()
    print(b6_combined(
        "B6 baseline -- OpenHands V1 + GPT-5.4 (PARTIAL: only 7 of 16 libs ran)",
        [RESULTS / "b6_partial_gpt54_3libs", RESULTS / "b6_4cheap_gpt54"]))
    print()

    # Kaizen-delta (whatever we have)
    kd_per_lib = {}
    for lib in LITE:
        p = RESULTS / f"{lib}_kaizen_delta_anthropic.json"
        if p.exists():
            d = json.loads(p.read_text())
            if "final_counts" in d:
                d["counts"] = d["final_counts"]
            d["input_tokens"] = (d.get("totals") or {}).get("input_tokens", 0)
            d["elapsed_s"] = d.get("elapsed_s", 0)
            kd_per_lib[lib] = d
    if kd_per_lib:
        rows = cells_from_per_lib(kd_per_lib)
        # Compute aggregate manually
        p_total = sum(r["pass"] for r in rows)
        f_total = sum(r["fail"] for r in rows)
        e_total = sum(r["err"] for r in rows)
        att = p_total + f_total + e_total
        cost = sum((d.get("totals") or {}).get("cost_usd", 0) for d in kd_per_lib.values())
        agg = (f"Aggregate (PARTIAL: {len(kd_per_lib)} of 16 libs): "
               f"{p_total} passed / {f_total} failed / {e_total} errors -> "
               f"{(100*p_total/att if att else 0):.1f}% pass-rate. ${cost:.2f}.")
        print(format_table(
            f"## Kaizen-delta -- per-file decompose+recompose + Sonnet 4.6 (PARTIAL: {len(kd_per_lib)}/16 libs)",
            agg, rows))


if __name__ == "__main__":
    main()
