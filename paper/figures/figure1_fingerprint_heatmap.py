"""Figure 1 — Value-Add Fingerprint Heatmap.

Two-panel figure:
  Panel A (left): value-add heatmap — color = value_add_pp, annotation = pass-rate %
  Panel B (right): llm-lean heatmap — color = log10(llm_lean), annotation = llm_lean ×

Rows: 16 commit0-lite libraries (floor libs marked with *)
Cols: 6 (architecture × provider) cells — KD-S, KD-G, B3-S, B3-G, OH-S, OH-G
      (Phase 1 will add Aider-S, Aider-G, smolagents-S, smolagents-G — script handles
      missing data gracefully, so re-running after Phase 1 produces the extended figure.)

Reads from benchmarks/commit0/results/.
Outputs:
  benchmarks/paper/figures/figure1.pdf  (vector, publication-quality)
  benchmarks/paper/figures/figure1.png  (raster, 300 DPI)

Usage:
  py -3.12 benchmarks/paper/figures/figure1_fingerprint_heatmap.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from matplotlib.colors import TwoSlopeNorm

# ---------- Configuration ----------
ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "commit0" / "results"
OUT_DIR = Path(__file__).resolve().parent

LIBS = [
    "wcwidth", "deprecated", "cachetools", "voluptuous", "portalocker",
    "pyjwt", "chardet", "tinydb", "simpy", "imapclient", "parsel",
    "marshmallow", "cookiecutter", "babel", "jinja", "minitorch",
]
FLOOR = {"chardet", "marshmallow", "babel", "jinja", "minitorch"}

# Column order: (display_label, arch_kind, provider)
COLS = [
    ("KD-S",     "kd",    "anthropic"),
    ("KD-G",     "kd",    "openai"),
    ("B3-S",     "b3",    "anthropic"),
    ("B3-G",     "b3",    "openai"),
    ("Aider-S",  "aider", "anthropic"),
    ("Aider-G",  "aider", "openai"),
    ("Sm-S",     "smol",  "anthropic"),
    ("Sm-G",     "smol",  "openai"),
    ("OH-S",     "oh",    "anthropic"),
    ("OH-G",     "oh",    "openai"),
]


# ---------- Data loading ----------
def loadj(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {}


def lib_passrate(per_lib: dict, lib: str):
    d = (per_lib or {}).get(lib, {}) or {}
    c = d.get("counts") or d.get("final_counts") or {}
    p, f, e = c.get("passed", 0), c.get("failed", 0), c.get("errors", 0)
    a = p + f + e
    if a == 0 and not c:
        return None
    return (100 * p / a) if a else 0


def lib_cost(per_lib: dict, lib: str, provider: str):
    d = (per_lib or {}).get(lib, {}) or {}
    if not d:
        return None
    if "totals" in d and isinstance(d["totals"], dict):
        c = d["totals"].get("cost_usd")
        if c is not None:
            return c
    fresh_in = d.get("input_tokens", 0)
    out = d.get("output_tokens", 0)
    cached = d.get("cached_input_tokens", 0)
    if provider == "anthropic":
        return (fresh_in * 3 + out * 15) / 1_000_000
    return ((fresh_in - cached) * 1.25 + cached * 0.125 + out * 10) / 1_000_000


def kd_per_lib(provider: str) -> dict:
    out = {}
    for lib in LIBS:
        p = RESULTS / f"{lib}_kaizen_delta_{provider}.json"
        if p.exists():
            d = json.loads(p.read_text())
            if "final_counts" in d:
                d["counts"] = d["final_counts"]
            out[lib] = d
    return out


def arch_per_lib_from_aggregate(arch_name: str, provider: str) -> dict:
    """Load per-lib dict (Aider, smolagents). Aggregate + per-lib JSON merge:
    libs not in the aggregate are filled in from per-lib JSONs (covers smoke-
    test runs that the sweep skipped).
    """
    out: dict = {}
    agg = RESULTS / f"aggregate_lite_{arch_name}_{provider}.json"
    if agg.exists():
        d = json.loads(agg.read_text())
        out = dict(d.get("per_library", {}) or {})
    for lib in LIBS:
        if lib in out:
            continue
        p = RESULTS / f"{lib}_{arch_name}_{provider}.json"
        if p.exists():
            out[lib] = json.loads(p.read_text())
    for entry in out.values():
        if "final_counts" in entry and "counts" not in entry:
            entry["counts"] = entry["final_counts"]
    return out


def oh_lib_cost_from_jsonl(jsonl: Path, lib: str):
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


def merge_oh(*dirs: str) -> dict:
    out = {}
    for name in dirs:
        d = RESULTS / name
        rep_p = d / "output.report.json"
        jsonl_p = d / "output.jsonl"
        if not rep_p.exists():
            continue
        rep = json.loads(rep_p.read_text())
        for lib in (rep.get("completed_ids", []) or []):
            status = (
                "RES" if lib in rep.get("resolved_ids", [])
                else "no" if lib in rep.get("unresolved_ids", [])
                else "?"
            )
            cost = oh_lib_cost_from_jsonl(jsonl_p, lib)
            out[lib] = (status, cost)
    return out


# ---------- Load all baselines ----------
b2s = loadj(RESULTS / "aggregate_lite_single_shot_sonnet.json").get("per_library", {})
b2g = loadj(RESULTS / "aggregate_lite_single_shot_openai.json").get("per_library", {})
b3s = loadj(RESULTS / "aggregate_lite_reflexion_sonnet.json").get("per_library", {})
b3g = loadj(RESULTS / "aggregate_lite_reflexion_openai.json").get("per_library", {})
kds = kd_per_lib("anthropic")
kdg = kd_per_lib("openai")
aiders = arch_per_lib_from_aggregate("aider", "anthropic")
aiderg = arch_per_lib_from_aggregate("aider", "openai")
smols  = arch_per_lib_from_aggregate("smolagents", "anthropic")
smolg  = arch_per_lib_from_aggregate("smolagents", "openai")
oh_s = merge_oh("b6_partial_pass1", "b6_4cheap_sonnet", "b6_t3_sonnet")
oh_g = merge_oh("b6_partial_gpt54_3libs", "b6_4cheap_gpt54", "b6_10missing_gpt54")


def cell_for(lib: str, kind: str, provider: str):
    """Return dict with keys: rate, value_add_pp, cost, llm_lean, status, missing."""
    if kind == "kd":
        per_lib = kds if provider == "anthropic" else kdg
        baseline = b2s if provider == "anthropic" else b2g
        rate = lib_passrate(per_lib, lib)
        srate = lib_passrate(baseline, lib)
        if rate is None or srate is None:
            return {"missing": True}
        cost = lib_cost(per_lib, lib, provider) or 0
        s_cost = lib_cost(baseline, lib, provider) or 0.001
        return {
            "missing": False, "status": None,
            "rate": rate,
            "value_add_pp": rate - srate,
            "cost": cost, "llm_lean": cost / max(s_cost, 0.001),
        }
    if kind == "b3":
        per_lib = b3s if provider == "anthropic" else b3g
        baseline = b2s if provider == "anthropic" else b2g
        rate = lib_passrate(per_lib, lib)
        srate = lib_passrate(baseline, lib)
        if rate is None or srate is None:
            return {"missing": True}
        cost = lib_cost(per_lib, lib, provider) or 0
        s_cost = lib_cost(baseline, lib, provider) or 0.001
        return {
            "missing": False, "status": None,
            "rate": rate,
            "value_add_pp": rate - srate,
            "cost": cost, "llm_lean": cost / max(s_cost, 0.001),
        }
    if kind in ("aider", "smol"):
        if kind == "aider":
            per_lib = aiders if provider == "anthropic" else aiderg
        else:
            per_lib = smols if provider == "anthropic" else smolg
        baseline = b2s if provider == "anthropic" else b2g
        rate = lib_passrate(per_lib, lib)
        srate = lib_passrate(baseline, lib)
        if rate is None or srate is None:
            return {"missing": True}
        cost = lib_cost(per_lib, lib, provider) or 0
        s_cost = lib_cost(baseline, lib, provider) or 0.001
        return {
            "missing": False, "status": None,
            "rate": rate,
            "value_add_pp": rate - srate,
            "cost": cost, "llm_lean": cost / max(s_cost, 0.001),
        }
    if kind == "oh":
        oh = oh_s if provider == "anthropic" else oh_g
        baseline = b2s if provider == "anthropic" else b2g
        if lib not in oh:
            return {"missing": True}
        status, cost = oh[lib]
        cost = cost or 0
        srate = lib_passrate(baseline, lib)
        s_cost = lib_cost(baseline, lib, provider) or 0.001
        if status == "RES":
            rate, vap = 100.0, 100 - (srate or 0)
        else:
            rate, vap = None, None
        return {
            "missing": False, "status": status,
            "rate": rate, "value_add_pp": vap,
            "cost": cost, "llm_lean": cost / max(s_cost, 0.001),
        }
    return {"missing": True}


# ---------- Build matrices ----------
nrows, ncols = len(LIBS), len(COLS)
val_matrix = np.full((nrows, ncols), np.nan)
lean_matrix = np.full((nrows, ncols), np.nan)
annot_top = [["" for _ in range(ncols)] for _ in range(nrows)]
annot_bot = [["" for _ in range(ncols)] for _ in range(nrows)]
status_grid = [[None for _ in range(ncols)] for _ in range(nrows)]

for i, lib in enumerate(LIBS):
    for j, (label, kind, provider) in enumerate(COLS):
        c = cell_for(lib, kind, provider)
        if c["missing"]:
            status_grid[i][j] = "missing"
            annot_top[i][j] = "—"
            continue
        # status (OH-only)
        if c["status"] == "no":
            status_grid[i][j] = "unresolved"
            annot_top[i][j] = "no"
            annot_bot[i][j] = ""
            # show llm_lean even for no/unresolved
            lean_matrix[i, j] = c["llm_lean"]
            continue
        # populated cell with rate + value-add
        if c["value_add_pp"] is not None:
            val_matrix[i, j] = c["value_add_pp"]
        if c["llm_lean"] is not None:
            lean_matrix[i, j] = c["llm_lean"]
        if c["rate"] is not None:
            annot_top[i][j] = f"{c['rate']:.0f}%"
        if c["value_add_pp"] is not None:
            sign = "+" if c["value_add_pp"] >= 0 else ""
            annot_bot[i][j] = f"{sign}{c['value_add_pp']:.0f}pp"


# ---------- Plot ----------
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "axes.titleweight": "bold",
})

fig, axes = plt.subplots(1, 2, figsize=(17, 8.5), gridspec_kw={"width_ratios": [1, 1], "wspace": 0.30})

# Row labels: floor libs starred + bold
row_labels = [(f"{lib}*" if lib in FLOOR else lib) for lib in LIBS]
col_labels = [c[0] for c in COLS]

# ----- Panel A: value-add heatmap -----
axA = axes[0]
# Diverging colormap centered at 0; cap at +/-50pp for visual range
vmax = 100.0
norm = TwoSlopeNorm(vmin=-50, vcenter=0, vmax=vmax)
# Mask NaN cells so they render as background
masked_val = np.ma.masked_invalid(val_matrix)
imA = axA.imshow(masked_val, aspect="auto", cmap="RdBu_r", norm=norm)
axA.set_xticks(range(ncols))
axA.set_xticklabels(col_labels, fontsize=10, fontweight="bold")
axA.set_yticks(range(nrows))
axA.set_yticklabels(row_labels, fontsize=9.5)
# Bold floor-lib row labels
for i, lib in enumerate(LIBS):
    if lib in FLOOR:
        axA.get_yticklabels()[i].set_fontweight("bold")
        axA.get_yticklabels()[i].set_color("#7a3a00")
axA.set_title("(A) Value-add — pass-rate Δ vs. single-shot baseline", pad=12)

# Annotate cells
for i in range(nrows):
    for j in range(ncols):
        st = status_grid[i][j]
        if st == "missing":
            # grey hatched cell for not-run
            rect = patches.Rectangle((j-0.5, i-0.5), 1, 1, linewidth=0,
                                     facecolor="#e0e0e0", hatch="///", edgecolor="white")
            axA.add_patch(rect)
            axA.text(j, i, "n/r", ha="center", va="center",
                     color="#888888", fontsize=8, style="italic")
            continue
        if st == "unresolved":
            rect = patches.Rectangle((j-0.5, i-0.5), 1, 1, linewidth=0,
                                     facecolor="#f0e0e0", edgecolor="white")
            axA.add_patch(rect)
            axA.text(j, i, "no", ha="center", va="center",
                     color="#882222", fontsize=8.5, fontweight="bold")
            continue
        # populated
        v = val_matrix[i, j]
        # Choose annotation color based on background luminance
        text_color = "white" if abs(v) > 30 else "#1a1a1a"
        axA.text(j, i-0.18, annot_top[i][j], ha="center", va="center",
                 fontsize=8.5, fontweight="bold", color=text_color)
        axA.text(j, i+0.20, annot_bot[i][j], ha="center", va="center",
                 fontsize=8, color=text_color)

# Grid lines
axA.set_xticks(np.arange(-0.5, ncols), minor=True)
axA.set_yticks(np.arange(-0.5, nrows), minor=True)
axA.grid(which="minor", color="white", linewidth=1.2)
axA.tick_params(which="minor", length=0)

# Colorbar A
cbarA = plt.colorbar(imA, ax=axA, fraction=0.04, pad=0.02, extend="both")
cbarA.set_label("value-add (percentage points)", fontsize=9)


# ----- Panel B: llm-lean heatmap -----
axB = axes[1]
# Log-scale color: log10(llm_lean), so 1× = 0, 10× = 1, 100× = 2
log_lean = np.log10(np.maximum(lean_matrix, 0.1))
masked_lean = np.ma.masked_invalid(log_lean)
imB = axB.imshow(masked_lean, aspect="auto", cmap="YlOrRd", vmin=-0.3, vmax=2.0)

axB.set_xticks(range(ncols))
axB.set_xticklabels(col_labels, fontsize=10, fontweight="bold")
axB.set_yticks(range(nrows))
axB.set_yticklabels(row_labels, fontsize=9.5)
for i, lib in enumerate(LIBS):
    if lib in FLOOR:
        axB.get_yticklabels()[i].set_fontweight("bold")
        axB.get_yticklabels()[i].set_color("#7a3a00")
axB.set_title("(B) LLM-lean — cost ratio vs. single-shot baseline", pad=12)

# Annotate llm-lean cells
for i in range(nrows):
    for j in range(ncols):
        st = status_grid[i][j]
        if st == "missing":
            rect = patches.Rectangle((j-0.5, i-0.5), 1, 1, linewidth=0,
                                     facecolor="#e0e0e0", hatch="///", edgecolor="white")
            axB.add_patch(rect)
            axB.text(j, i, "n/r", ha="center", va="center",
                     color="#888888", fontsize=8, style="italic")
            continue
        v = lean_matrix[i, j]
        if np.isnan(v):
            continue
        # Format llm_lean: <10x as e.g. "1.9x", >=10x as integer
        if v < 10:
            txt = f"{v:.1f}×"
        else:
            txt = f"{v:.0f}×"
        # Color: white if dark background
        text_color = "white" if log_lean[i, j] > 1.0 else "#1a1a1a"
        axB.text(j, i, txt, ha="center", va="center",
                 fontsize=9, fontweight="bold", color=text_color)

axB.set_xticks(np.arange(-0.5, ncols), minor=True)
axB.set_yticks(np.arange(-0.5, nrows), minor=True)
axB.grid(which="minor", color="white", linewidth=1.2)
axB.tick_params(which="minor", length=0)

cbarB = plt.colorbar(imB, ax=axB, fraction=0.04, pad=0.02, extend="max")
cbarB.set_label("log₁₀(llm_lean)  —  0 = same as baseline, 2 = 100×", fontsize=9)
cbarB.set_ticks([0, 1, 2])
cbarB.set_ticklabels(["1×", "10×", "100×"])


# ----- Caption-ready footnote -----
fig.suptitle(
    "Figure 1 — Value-Add Fingerprint across (architecture × model × library) cells on commit0-lite",
    fontsize=12.5, fontweight="bold", y=0.995,
)
fig.text(
    0.5, 0.015,
    "Floor libraries (* and bold row labels): collection or import-graph problems that block most architectures at 0%. "
    "Cells marked 'n/r' = not run (e.g., OH-Sonnet covered 6 of 16 libs). "
    "Cells marked 'no' = OpenHands ran but did not resolve.\n"
    "Phase 1 columns Aider-S/G and Sm-S/G added 2026-05-05 (16-lib sweeps complete).",
    ha="center", fontsize=8.5, style="italic", color="#444444",
)

plt.tight_layout(rect=(0, 0.04, 1, 0.97))

# ---------- Save ----------
OUT_DIR.mkdir(parents=True, exist_ok=True)
pdf_path = OUT_DIR / "figure1.pdf"
png_path = OUT_DIR / "figure1.png"
plt.savefig(pdf_path, format="pdf", bbox_inches="tight")
plt.savefig(png_path, format="png", dpi=300, bbox_inches="tight")

# ---------- Print summary ----------
print(f"Saved: {pdf_path}")
print(f"Saved: {png_path}")
print()
print("Cell coverage:")
total_cells = nrows * ncols
n_missing = sum(1 for i in range(nrows) for j in range(ncols) if status_grid[i][j] == "missing")
n_unresolved = sum(1 for i in range(nrows) for j in range(ncols) if status_grid[i][j] == "unresolved")
n_populated = total_cells - n_missing - n_unresolved
print(f"  Total cells:       {total_cells} (16 libs × {ncols} arch×provider)")
print(f"  Populated (rate):  {n_populated}")
print(f"  OH unresolved:     {n_unresolved}")
print(f"  Not run (n/r):     {n_missing}")
print()
print("Top 5 strongest positive value-add cells:")
flat = [(LIBS[i], COLS[j][0], val_matrix[i, j])
        for i in range(nrows) for j in range(ncols)
        if not math.isnan(val_matrix[i, j])]
for lib, col, v in sorted(flat, key=lambda x: -x[2])[:5]:
    print(f"  {col:6} {lib:14}  {v:+.0f}pp")
print()
print("Top 5 strongest negative value-add cells:")
for lib, col, v in sorted(flat, key=lambda x: x[2])[:5]:
    print(f"  {col:6} {lib:14}  {v:+.0f}pp")
