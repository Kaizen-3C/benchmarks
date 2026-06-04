"""Statistical analyzer for the sampling re-test (Phase A/B).

Reads per-rep result JSONs named  <lib>_<arch>_<provider>_rep<k>.json  and folds the
K valid reps per cell into mean +/- 95% CI for every metric, then runs the
significance machinery the paper needs.

Per the SAMPLING_PLAN:
  metrics  : p (pass-rate), cost, Delta (value-add vs co-sampled single-shot), lambda, rho
  CIs      : bootstrap over reps (+ pooled Wilson for the proportion)
  Delta!=0 : bootstrap CI of Delta excludes 0
  A vs B   : Welch t (normal-ish) reported alongside sign-stability
  FDR      : Benjamini-Hochberg across cells

This is PURE ANALYSIS — no LLM, no Docker, $0. Run --selftest to validate the math
on synthetic reps with no input files.

Single source of truth (testing-fix T6): one results root, one counts parser
(counts|final_counts), one cost field (totals.cost_usd), one solved-definition.
"""
from __future__ import annotations
import argparse, glob, json, math, os, random, re, statistics, sys, tempfile
from pathlib import Path

BOOT = 5000
random.seed(0)  # deterministic CIs given the same reps

# ---------- one parser for everything (T6) ----------
def counts_of(d: dict) -> dict:
    c = d.get("final_counts") or d.get("counts") or {}
    return {k: int(c.get(k, 0) or 0) for k in ("passed", "failed", "skipped", "errors")}

def collected(c: dict) -> int:
    return c["passed"] + c["failed"] + c["errors"]   # skipped excluded from denominator

def rate(c: dict) -> float:
    n = collected(c)
    return (c["passed"] / n) if n else 0.0

def cost_of(d: dict) -> float:
    return float((d.get("totals") or {}).get("cost_usd", 0) or 0)

def is_valid_rep(d: dict) -> bool:
    """Invalid = provider/harness failure, not an LLM draw (SAMPLING_PLAN §4).

    A rep is invalid if ANY of: explicitly flagged; an *_error recorded; scoring fell
    outside the full-suite path; cost==0 (provider returned nothing billed); or
    collected==0 (pure 0/0/0 collection race). Note collected = passed+failed+errors,
    so a genuinely collection-gated lib (errors>0, e.g. minitorch) has collected>0 and
    stays VALID — we only drop the empty-race case here."""
    if d.get("rep_invalid"):
        return False
    if any(k.endswith("_error") for k in d):
        return False
    sc = d.get("scoring")
    if sc and sc not in ("commit0-test-full-suite", "full-suite-local-pytest"):
        return False
    if cost_of(d) <= 0:
        return False
    if collected(counts_of(d)) == 0:
        return False
    return True

def is_collection_gated(c: dict) -> bool:
    """T7: errors but ~no pass/fail => collection-gated (e.g. minitorch), not per-test fail."""
    return c["errors"] > 0 and (c["passed"] + c["failed"]) == 0

# ---------- bootstrap / intervals ----------
def boot_ci(xs, fn=statistics.mean, n=BOOT, lo=2.5, hi=97.5):
    if len(xs) < 2:
        v = fn(xs) if xs else 0.0
        return v, v, v
    samples = []
    k = len(xs)
    for _ in range(n):
        samples.append(fn([xs[random.randrange(k)] for _ in range(k)]))
    samples.sort()
    return fn(xs), samples[int(lo/100*n)], samples[int(hi/100*n)]

def boot_diff_ci(a, b, n=BOOT, lo=2.5, hi=97.5):
    """CI for mean(a) - mean(b), independent resampling."""
    if not a or not b:
        return 0.0, 0.0, 0.0
    ka, kb, out = len(a), len(b), []
    for _ in range(n):
        ma = statistics.mean([a[random.randrange(ka)] for _ in range(ka)])
        mb = statistics.mean([b[random.randrange(kb)] for _ in range(kb)])
        out.append(ma - mb)
    out.sort()
    return statistics.mean(a) - statistics.mean(b), out[int(lo/100*n)], out[int(hi/100*n)]

def wilson(passed: int, total: int, z=1.96):
    if total == 0:
        return 0.0, 0.0, 0.0
    p = passed / total
    d = 1 + z*z/total
    c = (p + z*z/(2*total)) / d
    h = z*math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / d
    return p, max(0.0, c-h), min(1.0, c+h)

def welch_t(a, b):
    if len(a) < 2 or len(b) < 2:
        return None, None
    ma, mb = statistics.mean(a), statistics.mean(b)
    va, vb = statistics.variance(a), statistics.variance(b)
    se = math.sqrt(va/len(a) + vb/len(b))
    if se == 0:
        return (math.inf if ma != mb else 0.0), None
    return (ma - mb)/se, se

def bh_fdr(pvals, q=0.05):
    """Benjamini-Hochberg; returns set of indices that pass at FDR q."""
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals); passed = set(); kmax = -1
    for rank, i in enumerate(idx, 1):
        if pvals[i] <= q*rank/m:
            kmax = rank
    for rank, i in enumerate(idx, 1):
        if rank <= kmax:
            passed.add(i)
    return passed

def t_sf_approx(t, df):
    """Two-sided p from t via a normal approx (no scipy dependency)."""
    if t is None:
        return 1.0
    # normal approx is adequate for df>=~10; conservative enough for screening
    z = abs(t)
    return 2 * 0.5 * math.erfc(z / math.sqrt(2))

# ---------- load ----------
REP_RE = re.compile(r"^(?P<lib>.+)_(?P<arch>aider|smolagents|single_shot|reflexion|kaizen_delta|kaizen_stage2)_(?P<prov>anthropic|openai|sonnet)_rep(?P<k>\d+)\.json$")

def load_cells(results_dir: Path):
    cells = {}  # (lib,arch,prov) -> list[dict]
    for p in sorted(results_dir.glob("*_rep*.json")):
        m = REP_RE.match(p.name)
        if not m:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        cells.setdefault((m["lib"], m["arch"], m["prov"]), []).append(d)
    return cells

# ---------- analyze ----------
def analyze(results_dir: Path, baseline_arch="single_shot"):
    cells = load_cells(results_dir)
    rows = []
    # baseline reps per (lib,prov) for Delta
    base = {}
    for (lib, arch, prov), reps in cells.items():
        if arch == baseline_arch:
            base[(lib, prov)] = [rate(counts_of(d)) for d in reps if is_valid_rep(d)]
    for (lib, arch, prov), reps in sorted(cells.items()):
        valid = [d for d in reps if is_valid_rep(d)]
        n_total, n_valid = len(reps), len(valid)
        rates = [rate(counts_of(d)) for d in valid]
        costs = [cost_of(d) for d in valid]
        gated = any(is_collection_gated(counts_of(d)) for d in valid)
        pooled_pass = sum(counts_of(d)["passed"] for d in valid)
        pooled_tot = sum(collected(counts_of(d)) for d in valid)
        pmean, plo, phi = boot_ci(rates) if rates else (0, 0, 0)
        _, wlo, whi = wilson(pooled_pass, pooled_tot)
        cmean, clo, chi = boot_ci(costs) if costs else (0, 0, 0)
        row = dict(lib=lib, arch=arch, prov=prov, n_valid=n_valid, n_total=n_total,
                   p_mean=pmean, p_lo=plo, p_hi=phi, p_wilson=(wlo, whi),
                   cost_mean=cmean, cost_lo=clo, cost_hi=chi,
                   gated=gated, rates=rates)
        # Delta vs co-sampled baseline
        b = base.get((lib, prov))
        if arch != baseline_arch and b and rates:
            dmean, dlo, dhi = boot_diff_ci(rates, b)
            row.update(delta_mean=dmean, delta_lo=dlo, delta_hi=dhi,
                       delta_sig=(dlo > 0 or dhi < 0))
        rows.append(row)
    return rows

def sign_stability(results_dir: Path, prov: str, archA="aider", archB="smolagents"):
    """Per lib: fraction of paired reps where archA's rate > archB's (rep order = pairing)."""
    cells = load_cells(results_dir)
    out = []
    libs = {lib for (lib, a, pr) in cells if pr == prov}
    for lib in sorted(libs):
        ra = [rate(counts_of(d)) for d in cells.get((lib, archA, prov), []) if is_valid_rep(d)]
        rb = [rate(counts_of(d)) for d in cells.get((lib, archB, prov), []) if is_valid_rep(d)]
        if not ra or not rb:
            continue
        k = min(len(ra), len(rb))
        wins = sum(1 for i in range(k) if ra[i] > rb[i])
        t, _ = welch_t(ra, rb)
        out.append((lib, wins, k, statistics.mean(ra)-statistics.mean(rb), t_sf_approx(t, k-1)))
    return out

# ---------- report ----------
def report(results_dir: Path):
    rows = analyze(results_dir)
    if not rows:
        print("no *_rep*.json found in", results_dir); return 0
    print("="*108)
    print(f"{'cell':40} {'nV/nT':>6} {'pass% [95% CI]':>22} {'cost$ [CI]':>18} {'Delta pp [CI] sig':>22}")
    print("-"*108)
    dl_idx, dl_p = [], []
    for i, r in enumerate(rows):
        ci = f"{r['p_mean']*100:5.1f} [{r['p_lo']*100:4.0f},{r['p_hi']*100:4.0f}]"
        cc = f"{r['cost_mean']:5.2f}[{r['cost_lo']:.2f},{r['cost_hi']:.2f}]"
        dd = ""
        if "delta_mean" in r:
            dd = f"{r['delta_mean']*100:+5.1f}[{r['delta_lo']*100:+4.0f},{r['delta_hi']*100:+4.0f}]{' *' if r['delta_sig'] else ''}"
            dl_idx.append(i)
            # crude p for FDR: distance of 0 from the bootstrap CI midpoint in CI-half-widths
            hw = max(1e-9, (r['delta_hi']-r['delta_lo'])/2)
            dl_p.append(min(1.0, math.erfc(abs(r['delta_mean'])/ (hw/1.96) / math.sqrt(2))))
        flags = (" GATED" if r['gated'] else "") + ("" if r['n_valid']==r['n_total'] else f" !{r['n_total']-r['n_valid']}invalid")
        print(f"{r['lib']+'_'+r['arch']+'_'+r['prov']:40} {r['n_valid']}/{r['n_total']:>2} {ci:>22} {cc:>18} {dd:>22}{flags}")
    if dl_idx:
        passed = bh_fdr(dl_p)
        print(f"\nValue-add significant after BH-FDR(q=0.05): "
              f"{sum(1 for j in range(len(dl_idx)) if j in passed)}/{len(dl_idx)} Delta cells")
    for prov in ("openai", "anthropic"):
        ss = sign_stability(results_dir, prov)
        if ss:
            print(f"\nsign-stability aider>smolagents ({prov}):")
            for lib, w, k, dm, p in ss:
                print(f"  {lib:14} {w}/{k} reps  meanΔ={dm*100:+.1f}pp  p~{p:.3f}")
    return 0

# ---------- selftest ----------
def selftest():
    d = Path(tempfile.mkdtemp())
    def w(lib, arch, prov, k, passed, total, cost):
        (d / f"{lib}_{arch}_{prov}_rep{k}.json").write_text(json.dumps({
            "repo": lib, "scoring": "commit0-test-full-suite",
            "final_counts": {"passed": passed, "failed": total-passed, "skipped": 0, "errors": 0},
            "totals": {"cost_usd": cost}, "rep": k}), encoding="utf-8")
    random.seed(1)
    # baseline ~50%, arch ~80% (clear +30pp), with noise; one invalid rep
    for k in range(6):
        w("cachetools", "single_shot", "openai", k, 100+random.randint(-5,5), 215, 0.05)
        w("cachetools", "aider", "openai", k, 172+random.randint(-6,6), 215, 0.6)
    w("cachetools", "aider", "openai", 99, 0, 0, 0.0)  # invalid ($0, 0/0) -> must be dropped
    for k in range(6):
        w("cachetools", "smolagents", "openai", k, 170+random.randint(-6,6), 215, 0.8)
    rows = {(_r['lib'],_r['arch']): _r for _r in analyze(d)}
    aid = rows[("cachetools","aider")]
    assert aid["n_valid"] == 6 and aid["n_total"] == 7, ("invalid-rep gating", aid)
    assert aid["p_lo"] < aid["p_mean"] < aid["p_hi"], "CI ordering"
    assert aid["delta_mean"] > 0.20 and aid["delta_sig"], ("Delta+sig", aid["delta_mean"])
    ci_ok = aid["p_lo"] <= statistics.mean(aid["rates"]) <= aid["p_hi"]
    assert ci_ok, "mean within CI"
    ss = sign_stability(d, "openai")
    assert ss and ss[0][2] == 6, "sign-stability pairs"
    # null case: baseline==arch -> Delta not significant
    for k in range(6):
        w("nulllib", "single_shot", "openai", k, 100+random.randint(-5,5), 215, 0.05)
        w("nulllib", "aider", "openai", k, 100+random.randint(-5,5), 215, 0.05)
    r2 = {(_r['lib'],_r['arch']): _r for _r in analyze(d)}[("nulllib","aider")]
    assert not r2["delta_sig"], ("null should be non-sig", r2.get("delta_mean"))
    print("SELFTEST PASS: invalid-rep gating, CI ordering, Delta+sig, null non-sig, sign-stability")
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default=str(Path(__file__).resolve().parents[2] / "results" / "sampling"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    return report(Path(a.results_dir))

if __name__ == "__main__":
    sys.exit(main())
