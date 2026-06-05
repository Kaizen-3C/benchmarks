"""Repetition runner for the sampling re-test (Phase A/B).

Runs each (arch x provider x lib) cell K times, scoring every rep through the shared
noise-safe full-suite path (score_branch), GATING invalid reps (provider/harness
failures) and re-drawing until K *valid* reps land, then writing one JSON per rep:

    <results>/sampling/<lib>_<arch>_<provider>_rep<k>.json

Each rep JSON carries rep index + intended temperature + seed (SAMPLING_PLAN T5).
`stats_analyze.py` consumes these. Runs on the WSL host (needs the agent SDKs +
commit0 + Docker). `--dry-run` prints the plan and spends NOTHING.

NOTE (T5 dependency): the production runners do not yet honor temperature/seed; until
they do (env KAIZEN_LLM_TEMPERATURE / KAIZEN_LLM_SEED wired into _llm.LLMClient), reps
carry native sampling variance. The values are recorded regardless so the schema is
forward-compatible.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import score_branch as sb              # shared scoring (T1-T4, T7)
import stats_analyze as sa            # reuse the ONE validity definition (T6)

WORKSPACE = Path.home() / "kaizen-commit0"
BASELINES = WORKSPACE / "baselines"
OUT_DIR = WORKSPACE / "baselines" / "results" / "sampling"

# arch -> how to invoke its runner + which git branch it writes (provider-aware)
def runner_cmd(arch: str, provider: str, lib: str) -> list[str]:
    py = sys.executable
    if arch == "aider":
        return [py, str(BASELINES / "aider" / "run_lite_aider.py"), "--provider", provider, "--only", lib]
    if arch == "smolagents":
        return [py, str(BASELINES / "smolagents" / "run_lite_smolagents.py"), "--provider", provider, "--only", lib]
    if arch == "single_shot":
        script = "run_lite_single_shot.py" if provider == "anthropic" else "run_lite_single_shot_openai.py"
        return [py, str(BASELINES / script), "--only", lib]
    raise ValueError(f"unsupported arch for sampling scaffold: {arch}")

def branch_of(arch: str, provider: str) -> str:
    if arch in ("aider", "smolagents"):
        return arch                                   # CODE_BRANCH in the fixed runners
    if arch == "single_shot":
        return "single_shot_sonnet" if provider == "anthropic" else "single_shot_openai"
    raise ValueError(arch)

def one_rep(arch, provider, lib, k, temperature, seed, dry, model=None):
    """Run + score one rep. Returns the rep dict (or None on dry-run)."""
    cmd = runner_cmd(arch, provider, lib)
    print(f"    rep{k}: {' '.join(cmd)}  [model={model or 'default'}]")
    if dry:
        return None
    env = dict(os.environ)
    if temperature is not None:
        env["KAIZEN_LLM_TEMPERATURE"] = str(temperature)   # T5 (runner-honoring TODO)
    if seed is not None:
        env["KAIZEN_LLM_SEED"] = str(seed + k)
    if model:
        env["KAIZEN_MODEL"] = model   # cheap-model override honored by the inner runner scripts
    subprocess.run(cmd, cwd=WORKSPACE, env=env)
    # robust re-score of the branch the agent just produced (score_branch, not the
    # runner's own scoring) so every rep is scored identically (T1-T4).
    sc = sb.score_branch(lib, branch_of(arch, provider))
    # cost from the runner's own JSON (it tracks the LLM spend)
    runner_json = WORKSPACE / "baselines" / "results" / f"{lib}_{arch}_{provider}.json"
    cost = 0.0
    if runner_json.exists():
        try:
            cost = float((json.loads(runner_json.read_text()).get("totals") or {}).get("cost_usd", 0) or 0)
        except Exception:
            pass
    return {
        "repo": lib, "arch": arch, "provider": provider, "rep": k,
        "model": model, "temperature": temperature, "seed": (None if seed is None else seed + k),
        "scoring": sc["scoring"], "final_counts": sc["counts"],
        "collected": sc["collected"], "rate": sc["rate"],
        "collection_gated": sc["collection_gated"],
        "totals": {"cost_usd": cost},
        "score_attempts": sc["attempts"],
    }

def run_cell(arch, provider, lib, reps, max_redraws, temperature, seed, dry, out_dir, sleep_s=0, model=None):
    print(f"  cell {lib}/{arch}/{provider}: target {reps} valid reps")
    valid = 0; draw = 0; invalid = 0
    while valid < reps and draw < reps + max_redraws:
        d = one_rep(arch, provider, lib, valid, temperature, seed, dry, model)
        draw += 1
        if dry:
            valid += 1; continue
        ok = sa.is_valid_rep(d)
        if not ok:
            invalid += 1
            d["rep_invalid"] = True
            (out_dir / f"{lib}_{arch}_{provider}_INVALID{draw}.json").write_text(json.dumps(d, indent=2))
            print(f"      -> INVALID (cost={d['totals']['cost_usd']}, collected={d['collected']}), re-drawing")
            if sleep_s and (valid < reps and draw < reps + max_redraws):
                print(f"         pacing: sleep {sleep_s}s to let a bad provider window clear")
                time.sleep(sleep_s)
            continue
        (out_dir / f"{lib}_{arch}_{provider}_rep{valid}.json").write_text(json.dumps(d, indent=2))
        print(f"      -> rep{valid} valid: {d['final_counts']['passed']}/{d['collected']} ${d['totals']['cost_usd']:.2f}")
        valid += 1
    if valid < reps:
        print(f"      !! only {valid}/{reps} valid reps after {draw} draws ({invalid} invalid) — provider unstable?")
    return valid, invalid

def _fix_jinja_editable_install():
    """Opt-in WSL workaround: an editable jinja2 install in repos/jinja must sit on a
    non-stub branch or litellm's `import jinja2` breaks mid-run. Gated + validated +
    logged so it is NOT a silent, unrelated side effect on other hosts.

    Controlled by env KAIZEN_FIX_JINJA_EDITABLE (default "1"; set "0" to disable).
    No-ops cleanly if the jinja repo isn't present; warns (does not crash) on failure.
    """
    if os.environ.get("KAIZEN_FIX_JINJA_EDITABLE", "1") == "0":
        return
    jinja_repo = WORKSPACE / "repos" / "jinja"
    if not jinja_repo.is_dir():
        return
    r = subprocess.run(["git", "-C", str(jinja_repo), "checkout", "-f", "smolagents"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [warn] jinja editable-install workaround (checkout smolagents) failed: "
              f"{r.stderr.strip()} — set KAIZEN_FIX_JINJA_EDITABLE=0 if not needed here",
              file=sys.stderr)
    else:
        print("  [info] jinja editable-install pinned to 'smolagents' branch "
              "(KAIZEN_FIX_JINJA_EDITABLE; set 0 to disable)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", required=True, choices=["aider", "smolagents", "single_shot"])
    ap.add_argument("--provider", required=True, choices=["anthropic", "openai"])
    ap.add_argument("--libs", nargs="+", required=True)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--max-redraws", type=int, default=3, help="extra draws allowed per cell for invalid reps")
    ap.add_argument("--sleep", type=int, default=0, help="seconds to pace between re-draws (let a bad provider window clear)")
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--model", default=None, help="litellm model override (e.g. openai/gpt-5.4-mini) for cheap Phase-A runs")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    out_dir = Path(a.out_dir)
    print(f"== sampling: {a.arch} x {a.provider} x {len(a.libs)} libs x {a.reps} reps "
          f"{'(DRY-RUN, no spend)' if a.dry_run else ''} ==")
    print(f"   out: {out_dir}   model={a.model or 'default'} temperature={a.temperature} seed={a.seed} max_redraws={a.max_redraws}")
    if not a.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        _fix_jinja_editable_install()
    tot_valid = tot_invalid = 0
    for lib in a.libs:
        v, iv = run_cell(a.arch, a.provider, lib, a.reps, a.max_redraws,
                         a.temperature, a.seed, a.dry_run, out_dir, a.sleep, a.model)
        tot_valid += v; tot_invalid += iv
    print(f"\n== done: {tot_valid} valid reps, {tot_invalid} invalid (discarded) ==")
    if not a.dry_run:
        print(f"   analyze with: python {HERE.parent/'stats_analyze.py'} --results-dir {out_dir}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
