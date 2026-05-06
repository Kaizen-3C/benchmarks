"""Value-add architectural fingerprint table.

For each (architecture x model x library) cell:
  value_add_pp     = arch_pass_rate - single_shot_LLM_pass_rate (same model)
  value_add_$_pp   = arch_cost / max(value_add_pp, 0.01)
  llm_lean         = arch_cost / single_shot_LLM_cost (same model, same lib)

Reads from benchmarks/commit0/results/. Outputs to stdout.
Also flags architectural weakness signatures per ADR-0063 §weakness_fingerprints.
"""

from __future__ import annotations

import json
from pathlib import Path

R = Path(__file__).resolve().parents[2] / "commit0" / "results"

LIBS = ["wcwidth","deprecated","cachetools","voluptuous","portalocker",
        "pyjwt","chardet","tinydb","simpy","imapclient","parsel",
        "marshmallow","cookiecutter","babel","jinja","minitorch"]
FLOOR = {"chardet","marshmallow","babel","jinja","minitorch"}


def loadj(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {}


def lib_passrate(per_lib: dict, lib: str) -> tuple[int, int, float | None]:
    """Return (passed, attempted, rate or None if not run)."""
    d = (per_lib or {}).get(lib, {}) or {}
    c = d.get("counts") or d.get("final_counts") or {}
    p, f, e = c.get("passed", 0), c.get("failed", 0), c.get("errors", 0)
    a = p + f + e
    if a == 0 and not c:
        return 0, 0, None  # not run
    return p, a, ((100 * p / a) if a else 0)


def lib_cost(per_lib: dict, lib: str, source_provider: str) -> float | None:
    """Cost from per-library JSON. Some baselines store cost differently."""
    d = (per_lib or {}).get(lib, {}) or {}
    if not d:
        return None
    # Prefer pre-computed cost
    if "totals" in d and isinstance(d["totals"], dict):
        c = d["totals"].get("cost_usd")
        if c is not None:
            return c
    # B2: compute from tokens
    fresh_in = d.get("input_tokens", 0)
    out = d.get("output_tokens", 0)
    cached = d.get("cached_input_tokens", 0)
    if source_provider == "anthropic":
        return (fresh_in * 3 + out * 15) / 1_000_000
    return ((fresh_in - cached) * 1.25 + cached * 0.125 + out * 10) / 1_000_000


def oh_status(report: dict, lib: str) -> tuple[str, float | None]:
    """OH instance status: RES / no / FAIL. Cost from report metrics."""
    if not report:
        return "FAIL", None
    if lib in report.get("resolved_ids", []):
        return "RES", None
    if lib in report.get("unresolved_ids", []):
        return "no", None
    if lib in report.get("completed_ids", []):
        return "?", None
    return "FAIL", None


def oh_lib_cost_from_jsonl(jsonl: Path, lib: str) -> float | None:
    if not jsonl.exists():
        return None
    for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        iid = obj.get("instance_id") or ""
        if iid.endswith(lib):
            return (obj.get("metrics") or {}).get("accumulated_cost", 0)
    return None


def merge_oh_dirs(*dir_names: str) -> dict:
    """Merge multiple OH result dirs into one (lib -> (status, cost))."""
    out = {}
    for name in dir_names:
        d = R / name
        rep_p = d / "output.report.json"
        jsonl_p = d / "output.jsonl"
        if not rep_p.exists():
            continue
        rep = json.loads(rep_p.read_text())
        for lib in (rep.get("completed_ids", []) or []):
            status, _ = oh_status(rep, lib)
            cost = oh_lib_cost_from_jsonl(jsonl_p, lib) if jsonl_p.exists() else None
            out[lib] = (status, cost)
    return out


# ----- Load all baselines -----
b2s = loadj(R / "aggregate_lite_single_shot_sonnet.json").get("per_library", {})
b2g = loadj(R / "aggregate_lite_single_shot_openai.json").get("per_library", {})
b3s = loadj(R / "aggregate_lite_reflexion_sonnet.json").get("per_library", {})
b3g = loadj(R / "aggregate_lite_reflexion_openai.json").get("per_library", {})

# KD per-lib (separate JSONs, not aggregated dict)
def kd_per_lib(provider: str) -> dict:
    out = {}
    for lib in LIBS:
        p = R / f"{lib}_kaizen_delta_{provider}.json"
        if p.exists():
            d = json.loads(p.read_text())
            if "final_counts" in d:
                d["counts"] = d["final_counts"]
            out[lib] = d
    return out
kds = kd_per_lib("anthropic")
kdg = kd_per_lib("openai")

# Aider and smolagents per-lib loaders — same JSON schema as KD (final_counts + totals)
def arch_per_lib_from_aggregate(arch_name: str, provider: str) -> dict:
    """Load per-lib dict for new architectures (Aider, smolagents).

    Reads the aggregate JSON if present, then *also* globs per-lib JSONs and
    fills in any libs missing from the aggregate (e.g. smoke-test runs that
    weren't included in the sweep's --skip set).
    """
    out: dict = {}
    agg = R / f"aggregate_lite_{arch_name}_{provider}.json"
    if agg.exists():
        d = json.loads(agg.read_text())
        out = dict(d.get("per_library", {}) or {})
    for lib in LIBS:
        if lib in out:
            continue
        p = R / f"{lib}_{arch_name}_{provider}.json"
        if p.exists():
            out[lib] = json.loads(p.read_text())
    # Normalize counts key for downstream helpers
    for entry in out.values():
        if "final_counts" in entry and "counts" not in entry:
            entry["counts"] = entry["final_counts"]
    return out


aiders = arch_per_lib_from_aggregate("aider", "anthropic")
aiderg = arch_per_lib_from_aggregate("aider", "openai")
smols  = arch_per_lib_from_aggregate("smolagents", "anthropic")
smolg  = arch_per_lib_from_aggregate("smolagents", "openai")

# OH merged across all subset dirs
oh_s = merge_oh_dirs("b6_partial_pass1", "b6_4cheap_sonnet", "b6_t3_sonnet")
oh_g = merge_oh_dirs("b6_partial_gpt54_3libs", "b6_4cheap_gpt54", "b6_10missing_gpt54")


# ----- Compute value-add fingerprint per cell -----
def compute_cell(arch_per_lib, lib, single_shot_per_lib, source_provider):
    """For KD-style architectures with full per-lib pass-rate."""
    p, a, rate = lib_passrate(arch_per_lib, lib)
    sp, sa, srate = lib_passrate(single_shot_per_lib, lib)
    if rate is None or srate is None:
        return None
    cost = lib_cost(arch_per_lib, lib, source_provider) or 0
    s_cost = lib_cost(single_shot_per_lib, lib, source_provider) or 0.001
    value_add_pp = rate - srate
    value_add_dollar_pp = (cost / max(value_add_pp, 0.01)) if value_add_pp > 0 else None
    llm_lean = cost / max(s_cost, 0.001)
    return {
        "passed": p, "attempted": a, "rate": rate,
        "cost": cost, "value_add_pp": value_add_pp,
        "value_add_dollar_pp": value_add_dollar_pp, "llm_lean": llm_lean,
    }


def compute_oh_cell(oh_dict, lib, single_shot_per_lib, source_provider):
    """For OH (binary RES/no/FAIL)."""
    if lib not in oh_dict:
        return None
    status, cost = oh_dict[lib]
    cost = cost or 0
    sp, sa, srate = lib_passrate(single_shot_per_lib, lib)
    if srate is None:
        return None
    s_cost = lib_cost(single_shot_per_lib, lib, source_provider) or 0.001
    # OH's pass-rate is binary: RES = 100, anything else = unknown (we don't have per-test counts in report)
    if status == "RES":
        rate = 100.0
        value_add_pp = 100 - srate
    elif status == "no":
        # we can't know exact pass-rate; report as "?"
        rate = None
        value_add_pp = None
    else:
        rate = None
        value_add_pp = None
    value_add_dollar_pp = (cost / max(value_add_pp, 0.01)) if (value_add_pp and value_add_pp > 0) else None
    llm_lean = cost / max(s_cost, 0.001)
    return {
        "status": status, "rate": rate, "cost": cost,
        "value_add_pp": value_add_pp,
        "value_add_dollar_pp": value_add_dollar_pp, "llm_lean": llm_lean,
    }


# ----- Print the table -----
def fmt_cell(c, kind="kd"):
    if c is None:
        return f"{'  --':>16}"
    if kind == "oh":
        if c['status'] == "RES":
            return f"RES +{c['value_add_pp']:>3.0f}pp x{c['llm_lean']:>4.0f}"
        if c['status'] == "no":
            return f" no  ?      x{c['llm_lean']:>4.0f}"
        return f"FAIL  --       --"
    # KD-style
    va = c['value_add_pp']
    sign = "+" if va >= 0 else ""
    return f"{c['rate']:>3.0f}% {sign}{va:>+4.0f}pp x{c['llm_lean']:>4.1f}"


print("=" * 200)
print("VALUE-ADD FINGERPRINT — each cell shows: pass-rate, value_add_pp vs same-model B2, llm_lean (cost ratio vs B2)")
print("=" * 200)
hdr = (
    f"{'lib':12} {'F?':>2} | "
    f"{'KD-S':>16} {'KD-G':>16} | "
    f"{'Aider-S':>16} {'Aider-G':>16} | "
    f"{'Sm-S':>16} {'Sm-G':>16} | "
    f"{'OH-S':>17} {'OH-G':>17}"
)
print(hdr); print("-" * len(hdr))

floor_unlocks = []
big_wins = []
big_losses = []
oh_resolved = []

for lib in LIBS:
    f = "*" if lib in FLOOR else " "
    kds_cell    = compute_cell(kds,    lib, b2s, "anthropic")
    kdg_cell    = compute_cell(kdg,    lib, b2g, "openai")
    aiders_cell = compute_cell(aiders, lib, b2s, "anthropic")
    aiderg_cell = compute_cell(aiderg, lib, b2g, "openai")
    smols_cell  = compute_cell(smols,  lib, b2s, "anthropic")
    smolg_cell  = compute_cell(smolg,  lib, b2g, "openai")
    ohs_cell    = compute_oh_cell(oh_s, lib, b2s, "anthropic")
    ohg_cell    = compute_oh_cell(oh_g, lib, b2g, "openai")
    print(
        f"{lib:12} {f:>2} | "
        f"{fmt_cell(kds_cell, 'kd'):>16} {fmt_cell(kdg_cell, 'kd'):>16} | "
        f"{fmt_cell(aiders_cell, 'kd'):>16} {fmt_cell(aiderg_cell, 'kd'):>16} | "
        f"{fmt_cell(smols_cell, 'kd'):>16} {fmt_cell(smolg_cell, 'kd'):>16} | "
        f"{fmt_cell(ohs_cell, 'oh'):>17} {fmt_cell(ohg_cell, 'oh'):>17}"
    )

    # Collect findings
    cell_labels = [
        (kds_cell, f"KD-S {lib}"), (kdg_cell, f"KD-G {lib}"),
        (aiders_cell, f"Aider-S {lib}"), (aiderg_cell, f"Aider-G {lib}"),
        (smols_cell, f"Sm-S {lib}"),    (smolg_cell, f"Sm-G {lib}"),
    ]
    for cell, label in cell_labels:
        if cell and cell['value_add_pp'] is not None:
            if cell['value_add_pp'] >= 10: big_wins.append((label, cell))
            if cell['value_add_pp'] <= -10: big_losses.append((label, cell))
            if lib in FLOOR and cell['rate'] > 0: floor_unlocks.append((label, cell))
    for cell, label in [(ohs_cell, f"OH-S {lib}"), (ohg_cell, f"OH-G {lib}")]:
        if cell and cell.get('status') == 'RES':
            oh_resolved.append((label, cell))
            if lib in FLOOR: floor_unlocks.append((label + " (RES)", cell))

print()
print("Legend:")
print("  KD cells: pass% +pp vs same-model B2 xN llm_lean (cost ratio)")
print("  OH cells: RES = resolved 100% / no = unresolved / FAIL = didn't complete")
print("  +/- pp:   value-add over the LLM's single-shot baseline (same model)")
print("  llm_lean: cost ratio -- 1x means 'spent same as just calling the LLM once'")
print()

# ----- Architectural-weakness signatures -----
print("=" * 100)
print("ARCHITECTURAL-WEAKNESS SIGNATURES (per ADR-0063 §weakness_fingerprints)")
print("=" * 100)

print()
print(f"OH WEAKNESS — high llm_lean for low/negative value-add")
print("(cells where OH spent much more than the LLM and didn't resolve):")
for lib in LIBS:
    cell = compute_oh_cell(oh_s, lib, b2s, "anthropic")
    if cell and cell['llm_lean'] > 5 and cell.get('status') in ("no", "FAIL"):
        print(f"  OH-S {lib:13} {cell['status']:>4} llm_lean={cell['llm_lean']:>5.0f}x cost=${cell['cost']:.2f}")
    cell = compute_oh_cell(oh_g, lib, b2g, "openai")
    if cell and cell['llm_lean'] > 5 and cell.get('status') in ("no", "FAIL"):
        print(f"  OH-G {lib:13} {cell['status']:>4} llm_lean={cell['llm_lean']:>5.0f}x cost=${cell['cost']:.2f}")

print()
print(f"KD WEAKNESS — negative value-add (per-file regen damaged working code):")
for label, cell in big_losses:
    print(f"  {label:18} rate={cell['rate']:>3.0f}%  value_add={cell['value_add_pp']:+.0f}pp  cost=${cell['cost']:.2f}  llm_lean={cell['llm_lean']:.1f}x")

print()
print(f"FLOOR-LIB UNLOCKS (only baseline >0% on a floor lib):")
seen_libs = set()
for label, cell in floor_unlocks:
    lib = label.split()[1].rstrip(":")
    rate = cell.get('rate', 100 if cell.get('status') == 'RES' else None)
    print(f"  {label:30} rate={rate}  cost=${cell['cost']:.2f}")

print()
print(f"BIG WINS (KD value-add >= 10pp):")
for label, cell in big_wins:
    print(f"  {label:18} rate={cell['rate']:>3.0f}%  value_add=+{cell['value_add_pp']:.0f}pp  cost=${cell['cost']:.2f}  llm_lean={cell['llm_lean']:.1f}x")
