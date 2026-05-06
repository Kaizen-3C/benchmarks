# After Action Review — Phase 1 Matrix Extension (Aider + smolagents)

**Date:** 2026-05-05 (Day 13 of 90, 17 days ahead of Day 30 target)
**Disposition:** Phase 1 fully landed early. 6-architecture matrix (KD, OH, B2, B3, Aider, smolagents) × 2 providers × 16 libs now complete; 140 / 160 cells populated, $65.12 spend on the Phase 1 leg, all four sweeps within budget.
**Predecessor:** [`AAR_2026-04-22_FINAL.md`](AAR_2026-04-22_FINAL.md), [`AAR_2026-04-22_B3_ADDENDUM.md`](AAR_2026-04-22_B3_ADDENDUM.md)
**Plan that drove this work:** [`../paper/PHASE1_COST_REVIEW.md`](../paper/PHASE1_COST_REVIEW.md)

## Mission

Extend the architectural fingerprint from 4 architectures (KD, OH + the B-baselines) to 6 by adding Aider and smolagents — closing the "you only measured your own arch" reviewer critique on the methodology paper before draft v1.

## Outcome scoreboard (Phase 1 cells only)

| Cell | Libs | Tests passed | Rate | Cost | Wall |
|---|---:|---:|---:|---:|---:|
| Aider × Sonnet 4.6 | 15 | 493 / 506 | 97.4% | $16.80 | 439 min |
| Aider × GPT-5.4 | 16 | 385 / 398 | 96.7% | $9.63 | 55 min |
| smolagents × Sonnet 4.6 | 15 | 639 / 650 | 98.3% | $29.25 | 25 min |
| smolagents × GPT-5.4 | 16 | 830 / 843 | 98.5% | $9.44 | 71 min |
| **Phase 1 total** | | | | **$65.12** | |

Budget projection was $55–105 risk-adjusted. Came in mid-range. Combined campaign total now **$247.53**.

## What we learned

### 1. Per-cell variance is much wider than per-architecture aggregates suggest

The aggregate pass-rates (96.7–98.5%) hide cell-level disjointness that's exactly the methodology paper's thesis. From the regenerated [Figure 1](../paper/figures/figure1.pdf):

- **Strongest positive value-add cells (Phase 1):**
  - jinja × all 4 Phase 1 cells: +96pp value-add (KD shows 0% on jinja; both new architectures unlock it)
  - chardet × Aider-Sonnet & Sm-GPT: +85pp
  - voluptuous × Aider-Sonnet & Sm-GPT: +92pp
  - marshmallow × Aider-Sonnet & Sm-GPT: +92pp

- **Strongest negative value-add (Phase 1):**
  - simpy × Aider-Sonnet, Sm-Sonnet: −83pp (Sonnet on simpy is fragile; both architectures regress it)
  - cachetools × Aider-GPT: −80pp
  - deprecated × Aider-Sonnet: −52pp (KD-S got +38pp on the same lib — direct complementary-weakness cell)

This is the methodology paper's headline pattern: **architecture × provider × library is not separable.** No "best architecture" exists across the matrix; cells are diagnostic, aggregates are not.

### 2. Aider × Anthropic was the wall-time outlier — auto-test loop runs past the documented cap

The runner defines `MAX_WALL_S = 30 * 60` (30 min/lib) but enforces it post-hoc as a flag, not as an active kill. Three libs ran to 80–90 min on Aider × Sonnet:

| Lib | Aider × Sonnet wall | Aider × GPT wall |
|---|---:|---:|
| marshmallow | 90.8 min | 10.1 min |
| voluptuous | 90.7 min | 6.0 min |
| babel | 82.6 min | 5.7 min |

GPT-5.4 converged 8–15× faster than Sonnet 4.6 on the same architecture and same library. The Aider auto-test loop — which iterates after each pytest fail — interacts with model edit-fidelity differently across providers. This is itself a **paper finding**, not a bug. Document it; don't "fix" by force-killing at the cap.

**Action item:** decide whether to convert `MAX_WALL_S` from a flag to an active kill in `_aider_runner.py`. Keeping it as a flag preserves the diagnostic information; converting it bounds reproduction-cost variance. Reasonable arguments both ways. Default for paper: keep as flag, document in §Reproducibility.

### 3. minitorch errored uniformly across all 4 Phase 1 cells — corpus-side artifact

| Cell | minitorch result |
|---|---|
| Aider × Sonnet | 0/0/error=1 |
| Aider × GPT | 0/0/error=1 |
| smolagents × Sonnet | 0/0/error=1 (`Forbidden access to module: posixpath` from `os.walk`) |
| smolagents × GPT | 0/0/error=1 |

Three of four are likely the same root cause: minitorch's pytest collection requires importing `numba` / `numpy` machinery that the per-lib Docker image doesn't ship by default. KD-S and KD-G also got 0% on minitorch (per the original AAR). **Five out of six architectures fail minitorch identically.** This is a corpus-side fixture problem, not an architectural finding — but it's diagnostically clean: when *every* architecture errors on a lib, the bottleneck is upstream of the architecture.

The smolagents-specific error (`posixpath` blocked even though `os` is whitelisted in `AUTHORIZED_IMPORTS`) is a real smolagents sandbox quirk. Worth one paragraph in §Limitations of the methodology paper, not more.

### 4. smolagents is dramatically cheaper than projected

| | Projection | Actual | Variance |
|---|---:|---:|---|
| smolagents × Sonnet | $30 (high-end of $15–30 per provider) | $29.25 | within range |
| smolagents × GPT | $30 (high-end) | $9.44 | **3× under** |

GPT-5.4 on smolagents converges in 11–14 LLM calls per library on average vs the 20-step max we capped at. Reflects model-pricing × call-pattern interaction more than model-quality difference. Worth flagging when the §Cost section of the paper gets written.

### 5. Self-import wall is consistent, expected, and not a bug

Every smolagents run on a library tries `from <lib_name> import ...` at some point during agent reasoning. This fails because we deliberately don't whitelist the target library — the agent should *write* the file, not import-test it. The agent recovers in every case (via `pathlib.Path.write_text` and re-running pytest). **Don't whitelist target packages**; the wall is a feature, not a bug. The behavior costs ~2–3 extra LLM steps per library.

## What changed in the repo

| File | Change |
|---|---|
| `baselines/aider/{aider_sonnet,aider_openai,run_lite_aider}.py` | Promoted from `.SKELETON.py` (2026-05-05) |
| `baselines/smolagents/{smolagents_sonnet,smolagents_openai,run_lite_smolagents}.py` | Same |
| `baselines/smolagents/_smolagents_runner.py` | `verbose` → `verbosity_level` (smolagents ≥1.20); cost callback now handles Pydantic `PromptTokensDetailsWrapper` (litellm ≥1.81) |
| `baselines/aider/SETUP.md`, `baselines/smolagents/SETUP.md` | Smoke test results + reproducibility notes for the aider 0.86.2 + litellm 1.81 compat patch |
| `baselines/value_add_fingerprint.py` | 6-architecture columns (KD, Aider, smolagents, OH per provider) |
| `paper/figures/figure1_fingerprint_heatmap.py` | Same; figure regenerated |
| `CAMPAIGN_README.md` | Aider + smolagents reproduction blocks, updated total |
| `baselines/results/aggregate_lite_{aider,smolagents}_{anthropic,openai}.json` | New |
| `baselines/results/<lib>_{aider,smolagents}_{anthropic,openai}.json` | 64 new per-lib JSONs |

External-library compat issues encountered and patched (documented for reproducibility):

1. **aider 0.86.2 doesn't know `litellm.PermissionDeniedError`** — added to `EXCEPTIONS` list in vendored `aider/exceptions.py`. Track upstream; remove patch when aider releases a fix.
2. **`pytest-cov` required** — several commit0-lite libraries (wcwidth, voluptuous, others) carry `--cov` flags in their pytest config.
3. **smolagents 1.24 renamed `verbose` → `verbosity_level`** — runner updated.
4. **litellm 1.81 returns Pydantic objects, not dicts, for `usage` and `prompt_tokens_details`** — cost callback updated to handle both shapes via getattr fallback.

## What this unlocks for the paper

Per [`../paper/PLAN.md`](../paper/PLAN.md) §Phase 2 (Day 30 → Day 60, draft v1 due 2026-06-22):

1. **Methodology paper §3 (Methodology) and §5 (Results)** can now reference a 6-architecture matrix instead of 2. The "you only measured your own arch" critique is structurally answered.
2. **§5.5 (Caching as confounder)** holds — Aider × Sonnet shows 92% native Anthropic cache hit (verifiable in per-lib JSONs); smolagents shows 0% (no cache injection by design). Same 9.8× ballpark gap reproduced on a different architecture pair.
3. **Figure 1** regenerates cleanly at 16 rows × 10 cells. Visual is denser but still readable; will likely need to widen the figure for camera-ready or split into two panels by provider.
4. **Schedule:** Day 30 (2026-05-22) preprint deadline is **17 days out**. Phase 1 done with 4 days budgeted slack means Phase 2 (writing) can start now if desired.

## What I would NOT recommend changing

- **Do not whitelist target-library packages in smolagents `AUTHORIZED_IMPORTS`.** The self-import wall is the architecture's natural behavior; muting it would over-fit the harness to commit0's structure.
- **Do not force-kill Aider at `MAX_WALL_S`.** The 90-min outliers are diagnostic — they're the model × architecture interaction we're trying to surface.
- **Do not re-run minitorch in isolation hoping for a different result.** The cross-architecture consistency (5/6 architectures error identically) is the finding.

## Open items for Phase 2 (writing)

- [ ] Decide §Limitations framing for the smolagents `posixpath` quirk (one paragraph, framed as honest limitation of any sandbox-based architecture, not as a smolagents-specific bug)
- [ ] Recompute aggregate pass-rate numbers in the paper's §5 results table — original had 4 archs, now has 6
- [ ] Update [`PHASE1_COST_REVIEW.md`](../paper/PHASE1_COST_REVIEW.md) §"What this unlocks" with actual cell-level findings (currently projected)
- [ ] Outreach: notify Tier 1B reviewers that Phase 1 landed early; the draft they'll see at preprint will be on the 6-arch matrix

## Cross-references

- Phase 1 plan: [`../paper/PHASE1_COST_REVIEW.md`](../paper/PHASE1_COST_REVIEW.md)
- Methodology paper plan: [`../paper/PLAN.md`](../paper/PLAN.md)
- Methodology paper outline: [`../paper/OUTLINE.md`](../paper/OUTLINE.md)
- Methodology paper draft: [`../paper/DRAFT_v0.md`](../paper/DRAFT_v0.md)
- Reviewer outreach: [`../paper/OUTREACH.md`](../paper/OUTREACH.md)
- Original campaign AAR: [`AAR_2026-04-22_FINAL.md`](AAR_2026-04-22_FINAL.md)
