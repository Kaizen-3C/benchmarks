# Sampling results — agent value-add significance (Tier-1, 2026-06)

Step 4 of the validation plan: *characterize agent value-add variance and test significance,
so "value-add" claims are distinguishable from LLM run-to-run noise.* Method: K=5 reps/cell
via `repeat_runner` (valid-rep gating), each rep scored canonically by `score_branch`
(commit0 full-suite), analyzed by `stats_analyze` (bootstrap 95% CIs, paired value-add Δ vs
the single-shot baseline, BH-FDR q=0.05, sign-stability). **OpenAI (gpt-5.4), default
temperature** (so variance matches the published numbers). Cost: **~$17.5**.

## cachetools (near-saturated lib)
| arch | pass% [95% CI] | Δ vs single_shot [CI] | sig |
|---|---|---|---|
| aider | 100.0 [100,100] | +13.0 [+2,+25] | |
| smolagents | 99.7 [99,100] | +12.7 [+1,+24] | |
| kaizen_delta | 95.5 [93,97] | +8.6 [−3,+21] | |
| reflexion | 82.9 [81,85] | −4.1 [−16,+8] | |
| single_shot (baseline) | 87.0 [75,98] | — | |

**0/4 significant after BH-FDR.** Complementary pattern is visible (aider/smolagents win,
reflexion regresses), but effects are small and the **baseline is noisy (87% ±12pp)**, so
nothing survives multiple-comparison correction at K=5. Agentic archs are far more
*reproducible* than single-shot (σ≈0 vs ≈12pp) — a finding in itself.

## voluptuous (floor lib — architectural unlock)
| arch | pass% [95% CI] | Δ vs single_shot [CI] | sig |
|---|---|---|---|
| **aider** | **88.7 [87,91]** | **+82.6 [+70,+90]** | **\*** |
| smolagents | 40.0 [0,80] | +33.8 [−6,+80] | bimodal, n.s. |
| reflexion | 24.7 [0,59] | +18.5 [−11,+51] | bimodal, n.s. |
| kaizen_delta | 0.0 [0,0] | −6.2 [−19,+0] | no unlock |
| single_shot (baseline) | 6.2 [0,19] | — | |

**1/4 significant after BH-FDR (aider).**

## What the sampling establishes (and corrects)
1. **A real, large, reliable value-add:** aider unlocks voluptuous at **+82.6pp, significant
   even at K=5** — the headline "agent value-add" claim, now with a CI.
2. **Bimodal pseudo-unlocks exposed:** smolagents/reflexion *sometimes* crack voluptuous and
   *sometimes* crash (149/149 vs 0/2 across reps) → wide CIs → **not significant**. A single
   run would have over-claimed these as reliable unlocks; sampling shows they aren't.
3. **A provider-specific over-generalization caught:** KD does **not** unlock voluptuous on
   OpenAI (0/0/0, all 5 reps). The published "KD cracked voluptuous 0→39%" was **Sonnet-only**
   and must be qualified to the provider.
4. **Calibration:** significance tracks effect size vs noise — large unlocks clear K=5, small
   near-saturated effects (cachetools) correctly do not. This is the cost-effective design:
   sample the large-effect claim-bearing cells; near-saturated cells need much larger K.

## Caveats / scope
- **OpenAI only** (reliable on the run host); Anthropic-provider claims (incl. the Sonnet KD
  voluptuous result) need a separate run when the provider is stable / off-peak.
- **K=5** — bootstrap CIs are wide on bimodal cells; raising K tightens them where needed.
- **reflexion** is scored at its *last* iteration (`score_branch`), vs the published *best*
  iteration — may understate reflexion; refine if a reflexion claim is load-bearing.
- These are **2 libs** (a demonstration that the pipeline produces calibrated significance),
  not yet the full set of cited cells.

## Reproduce
```bash
# WSL: bash sync_to_wsl.sh && bash preflight_clean.sh
python baselines/sampling/repeat_runner.py --arch <arch> --provider openai --libs <lib> --reps 5 --out-dir <out>
python baselines/sampling/stats_analyze.py --results-dir <out>
```
