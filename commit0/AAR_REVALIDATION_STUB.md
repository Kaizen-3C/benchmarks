# After Action Review — Phase 1 full-suite re-validation  *(STUB — fill in after the re-run)*

> **This is a stub.** Rename to `AAR_<YYYY-MM-DD>_REVALIDATION.md` on completion and fill every
> `TODO`. The "before" column is pre-populated from the committed `-x`-truncated JSONs so the
> deltas compute the moment the re-run lands. Plan: [`RE-VALIDATION.md`](RE-VALIDATION.md).

**Date:** TODO
**Disposition:** TODO (target: Aider + smolagents re-scored on the full suite via `commit0 test --branch`; Figure 1 + headline tables regenerated; truncation caveats removed)
**Predecessor:** [`AAR_2026-05-05_PHASE1_ADDENDUM.md`](AAR_2026-05-05_PHASE1_ADDENDUM.md)
**Driven by:** [`RE-VALIDATION.md`](RE-VALIDATION.md)

## Mission

Replace the `pytest -x` (stop-at-first-failure) Phase-1 competitor numbers — which truncated the
denominator and were not comparable to the full-suite (`commit0 test`) cells — with full-suite,
persisted, reproducible results, so every cell in the matrix is scored on one yardstick.

## What was already in place before the re-run (code, no spend)

- Runners patched to commit generated code to an `aider`/`smolagents` branch, score via
  `commit0 test --branch`, export `results/patches/*.patch`, and stamp
  `scoring`/`code_branch`/`patch_file`/`patch_sha256`. See [`RE-VALIDATION.md`](RE-VALIDATION.md) §5.
- Scoring-provenance guard: [`baselines/check_scoring_provenance.py`](baselines/check_scoring_provenance.py) + CI workflow.
- Interim caveats in README / PROTOCOL §6 / Phase-1 AAR / `results/SCORING_NOTICE.md`.

## Outcome scoreboard — aggregates (before = `-x`-truncated; after = full suite)

| Cell | Before (passed / attempted, `-x`) | After (passed / full-suite) | Δ rate | Cost before → after |
|---|---|---|---|---|
| Aider × Sonnet 4.6 | 493 / 506 (97.4%) | TODO | TODO | $16.80 → TODO |
| Aider × GPT-5.4 | 385 / 398 (96.7%) | TODO | TODO | $9.63 → TODO |
| smolagents × Sonnet 4.6 | 639 / 650 (98.3%) | TODO | TODO | $29.25 → TODO |
| smolagents × GPT-5.4 | 830 / 843 (98.5%) | TODO | TODO | $9.44 → TODO |
| **Re-run total** | — | — | — | **$65.12 → TODO** |

## Per-lib — the cells the `-x` artifact most distorted

"Before" shows passed / collected under `-x` (note every cell stops at "1 failed"); "after" is the
full suite. True suite sizes from full-suite architectures are in parentheses where known.

| Lib (true suite) | Aider-S before | Aider-G before | Sm-S before | Sm-G before | After (each) |
|---|---|---|---|---|---|
| chardet (376) | 6 / 7 | err | err | 6 / 7 | TODO |
| jinja (unknown²) | 24 / 25 | 24 / 25 | 24 / 25 | 24 / 25 | TODO |
| marshmallow (unknown²) | 11 / 12 | err | err | 11 / 12 | TODO |
| cookiecutter (367) | 14 / 15 | 15 / 16 | 14 / 15 | 60 / 61 | TODO |
| voluptuous (149) | 11 / 12 | 0 / 1 | 0 / 1 | 11 / 12 | TODO |
| imapclient (267) | 28 / 29 | 0 / 1 | 22 / 23 | err | TODO |

² jinja & marshmallow had no trusted denominator before this re-run — collection was broken on
every full-suite architecture. **Record the now-observed full-suite size here:** TODO.

## Findings to confirm or revise

1. **Magnitude of the "floor-lib unlock."** The `-x` data implied +85/+92/+96pp on
   chardet/voluptuous/marshmallow/jinja. State the full-suite value-add now: TODO.
2. **Does the qualitative claim survive?** "Aider/smolagents collect past where KD collects 0"
   was the reproducible part. Confirm against the persisted patches: TODO.
3. **Aider voluptuous cost was $0.00** (capture failed on a wall-capped run). Confirm real cost: TODO.
4. **Wall outliers** (Aider × Sonnet hit 80–90 min on marshmallow/voluptuous/babel under `-x`).
   Full-suite iteration may extend these — record new walls and whether any cap fired: TODO.

## Validation-status flips (update RE-VALIDATION.md §2/§3)

- [ ] Aider/smolagents per-lib rates + value_add_pp — moved from ❌ to ✅
- [ ] Phase-1 aggregate headline — moved to ✅
- [ ] Figure 1 regenerated from full-suite JSONs (`paper/figures/figure1_fingerprint_heatmap.py`)
- [ ] README headline table + "What we proved" #3 updated; ⚠ caveat removed
- [ ] PROTOCOL §6 "known violation" note removed
- [ ] `AAR_2026-05-05_PHASE1_ADDENDUM.md` correction banner removed (or pointed at this AAR)
- [ ] `results/SCORING_NOTICE.md` deleted
- [ ] `EXPECTED_PENDING` in `check_scoring_provenance.py` lowered to 0; guard re-run with `--strict` → exit 0
- [ ] Old `-x` JSONs archived under `results/_pre_revalidation/`; new `results/patches/*.patch` committed

## Budget actuals

| | Projected | Actual |
|---|---|---|
| Re-run (4 sweeps) | $65–100 | TODO |
| Wall (total) | ~ Phase-1 + full-suite overhead | TODO |

## Closing

TODO — one paragraph: did full-suite scoring change the architectural picture, and is the matrix
now single-yardstick reproducible end-to-end?
