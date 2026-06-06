# Statistically-significant sampling (re-test) plan

**Status:** scaffolding landed; Phase-A (cheap) not yet run.
**Goal:** turn the matrix from N=1 point estimates into CI-backed, reproducible claims, and
quantify (not just acknowledge) run-to-run LLM variability.

---

## 0. What "statistically significant" means here

Each cell `(architecture × provider × library)` currently has **N=1** run. LLM agents are
stochastic, so that's a point estimate. The re-test runs each sampled cell **K times** to estimate
the *distribution* of each metric and attach confidence intervals, then tests whether the paper's
claims survive run-to-run noise.

**Sample unit = the agent RUN, not the test.** A cell's pass-rate is computed over a fixed hidden
test set (not iid draws); the randomness we quantify is the agent regenerating different code each
run. So "sample size" K = number of independent agent runs per cell.

**Metrics, each reported as mean ± 95% CI:** `p` (pass-rate), `Δ` value-add vs a *co-sampled*
single-shot baseline, `λ` cost-ratio (= cost / baseline cost), `ρ` value-add per dollar (= Δ / cost).
Cost varies run-to-run too (iteration count) → cost gets CIs as well.

---

## 1. Two-phase structure

### Phase A — cheap LLMs: validate the methodology + machinery at scale
- **Purpose:** prove the *pipeline* end-to-end — repetition loop, per-rep storage, valid-rep
  gating, variance/CI computation, significance + FDR, sign-stability — on real (cheap) data at
  high K, for low $.
- **Models:** swap only the model string through the *same* aider/smolagents/litellm path —
  e.g. `claude-haiku-*` + a `gpt-*-mini`. Identical code path = a true rehearsal for Phase B.
- ⚠ **Bank this now:** cheap-model *variance ≠ real-model variance* (cheap models floor-out on
  hard libs → artificially low variance). Phase A validates the **pipeline and the stats code**,
  NOT the value of K. It also shakes out plumbing edge cases (flaky provider, 0%/100% cells,
  cost capture, the collection race).

### Phase B — real LLMs: the actual significance run
- Small **pilot** (K=5) on representative cells with the real models (`claude-sonnet-4-6`,
  `gpt-5.4`) → measure true run-to-run std → **power analysis** → set final K.
- Run final K on the sampled cells; compute CIs + significance + FDR.

---

## 2. Sampling design (do NOT brute-force 140 cells × K)

- **Stratify libraries** and sample representatives:
  - *ceiling* (deprecated, pyjwt — ~100%): K=2–3, just confirm stability.
  - *mid / high-variance* (chardet, parsel, simpy, voluptuous, imapclient): **full K** — this is
    where K matters.
  - *floor-unlock* (jinja, babel, marshmallow, cookiecutter): full K (reproduce the unlocks).
  - *hard-floor* (minitorch — collection-gated, see HARNESS notes): K=2.
- **Adaptive K:** spend reps where variance is. Cells at 0%/100% need few; mid-range and
  `Δ≈0` cells need the most.
- **Always co-sample the single-shot baseline** (same models, same K) so `Δ/λ/ρ` use paired
  distributions, not a fixed N=1 baseline.

---

## 3. Statistical methods (implemented in `baselines/sampling/stats_analyze.py`)

- **CIs:** bootstrap (default) + Wilson interval for the proportion — robust for bounded, small-K,
  near-floor/ceiling data (t-tests are not).
- **Per-cell "Δ ≠ 0":** bootstrap CI of Δ excludes 0.
- **Arch A vs B on lib L:** Welch's t / Mann-Whitney; paired if seeds are fixed across archs.
- **Complementary-weakness robustness:** **sign-stability** (does A>B hold in k/K reps?) — this is
  what the paper's qualitative claims actually need, beyond means.
- **Multiple comparisons:** Benjamini-Hochberg FDR across cells.

---

## 4. The practical risk that will wreck this if ignored: provider/harness failure ≠ LLM variance

This campaign proved Anthropic intermittently returns `$0`/timeout cells, and the harness can
return transient `0/0/0` (collection race). **A provider/harness-failed run is an *invalid sample*,
not a draw from the LLM distribution** — if it leaks into the variance estimate it corrupts
everything. The repetition runner MUST:
- health-check before each rep; **detect and discard** invalid reps and **re-draw** until K *valid*
  reps land. A rep is **invalid** if any of: `cost_usd == 0`, scoring fell back to local/baseline,
  `collected == 0` (0/0/0), or a `*_error` is recorded.
- log discarded reps separately (report attrition, don't hide it).

---

## 5. Testing fixes carried over from the `benchmarks-delta` harness review
*(these are harness/testing fixes — NOT the kaizen Stage-2 algorithm — and apply to THIS repo)*

The delta review found systemic, architecture-agnostic issues. The sampling scaffolding here
**embodies the fixes** so the re-test is sound; the same fixes should later be folded back into the
production runners of both repos.

| # | Issue (seen across runners) | Carried-over fix (in `baselines/sampling/`) |
|---|---|---|
| T1 | No shared noise-guard before `git add -A` → `commit0 test --branch`; binary/non-gitignored noise silently scores the BASELINE | `score_branch.py` strips `.aider*`, `spec.md`, `__pycache__` before commit; verifies the cell isn't a baseline-fallback |
| T2 | `pytest -x` truncation / host-pytest (aider/smol) — wrong/short denominators | `score_branch.py` always scores the FULL suite via `commit0 test --branch` (no `-x`) |
| T3 | Collection race: only pure `0/0/0` retried (and only in one runner); partial collapse mis-read as regression | `score_branch.py` retries on `0/0/0` AND on a sharp collected-count drop vs the cell's own high-water mark |
| T4 | Result selected by latest-mtime log dir → wrong run under concurrency | `score_branch.py` snapshots the log dir before the run and requires a strictly-newer dir |
| T5 | No temperature/seed → unreproducible beyond sampling noise | repetition runner records intended `temperature`/`seed` per rep; **runner-honoring is a TODO dependency** (see §7) |
| T6 | Aggregator inconsistency: 3 result roots, 3 "instances-solved" defs, reflexion cost=$0 mispricing, `counts` vs `final_counts` | `stats_analyze.py` is the single analyzer: one results root, one counts parser (`counts`\|`final_counts`), one cost field, one solved-definition |
| T7 | collection-errors conflated with per-test failures (minitorch is collection-gated on `SimpleOps.cmap`, not corpus) | analyzer separates `errors` (collection) from `failed`; flags collection-gated cells distinctly |

> **Deferred (do AFTER testing + sampling complete):** fold the delta-side *Recommendations*
> (extract one shared `score_branch()` into the production runners, fix/redefine the B.5 leakage
> scan to cover the test-failure-feedback channel, unify the three aggregators) back into
> `benchmarks-delta`. Tracked separately; not part of this sampling work.

---

## 6. Cost model & budget (decide the ceiling)

Grounded in this campaign (OpenAI ~$0.4–0.8/cell, chardet ~$6 outlier; Sonnet ~$2–4/cell; full
matrix ≈ **$247/rep**):
- **Phase A (cheap):** ~1/10 model cost × K=10 × ~12 stratified cells ≈ **$15–60**. Do generously.
- **Phase B (real):** stratified ~12 libs × relevant cells × K=5 ≈ **$150–400**; full 140-cell
  matrix × K=5 ≈ **~$1,200**. → **Strongly recommend stratified.**

**Open decision points:** (1) target CI half-width (e.g. ≤±5pp on mid cells → drives K);
(2) stratified vs full matrix; (3) Phase-B budget ceiling; (4) cheap model pair; (5) keep native
temperature (measure real variance) vs pin temp/seed.

---

## 7. Scaffolding (landed, no spend)

`baselines/sampling/`:
- **`score_branch.py`** — shared, noise-safe, full-suite scoring (T1–T4, T7). Pure scoring; no LLM.
- **`repeat_runner.py`** — orchestrates K valid reps per cell: calls the existing (fixed) runner,
  scores via `score_branch`, gates invalid reps + re-draws, stores `<lib>_<arch>_<prov>_rep<k>.json`
  with rep index + temperature + seed. `--dry-run` prints the plan and spends nothing.
- **`stats_analyze.py`** — reads per-rep JSONs → mean/std/95% CI per metric, Δ-significance,
  sign-stability, Welch/Mann-Whitney, BH-FDR. Pure analysis, `$0`, self-tested on synthetic reps.

**TODO before Phase A spends for real:** wire `temperature`/`seed` through `_llm.LLMClient`/the
agent SDKs so the values `repeat_runner` records are actually applied (T5). Until then reps carry
native sampling variance (acceptable for Phase-A pipeline validation; required for Phase-B rigor).

### Suggested first action
Phase A on ~12 stratified cells at K=10 with `claude-haiku` + a `gpt-mini`, ~$15–60, to exercise
`repeat_runner` + `stats_analyze` + valid-rep gating end-to-end. Then a K=5 real-model pilot to set
K, then stratified Phase B. Report every headline number as **mean ± 95% CI** with sign-stability
for the complementary-weakness claims.
