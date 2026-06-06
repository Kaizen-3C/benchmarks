# After Action Review — Phase-1 full-suite re-validation

**Date:** 2026-06-04
**Disposition:** Re-validation complete. The Phase-1 Aider/smolagents matrix was re-scored on the
**full suite** via `commit0 test --branch` after a scoring bug was found and fixed; 55 of 64
competitor per-lib cells are now valid full-suite, Figure 1 regenerated, caveats resolved. The
remaining 9 cells are a documented, provider-limited gap (not a methodology defect).
**Predecessor:** [`AAR_2026-05-05_PHASE1_ADDENDUM.md`](AAR_2026-05-05_PHASE1_ADDENDUM.md) ·
**Plan:** [`RE-VALIDATION.md`](RE-VALIDATION.md)

---

## 1. Why this happened

Two scoring defects in the Phase-1 competitor cells, found by re-examining the data:

1. **`pytest -x` denominator truncation.** The Aider/smolagents runners scored with `pytest -x`
   (stop at first failure), so every "win" was *N passed, 1 failed* over a handful of tests, not
   the full suite. Inflated, non-comparable to the full-suite (`commit0 test`) cells, and in
   violation of `PROTOCOL.md` §6.
2. **patch-noise-in-commit -> silent baseline scoring (the big one).** `commit0 test --branch`
   builds a `patch.diff` from the branch and applies it in the container. `git add -A` was
   committing **binary agent noise** (`.aider.tags.cache/*.db`, `spec.md`) to the branch; the
   binary diff **fails to apply in the container**, so the cell silently scores the **baseline**
   (unimplemented stubs) with no error. The tell was **identical cross-architecture scores**
   (aider == smolagents == baseline) despite different committed code.

**Impact:** every score produced this session was baseline/invalid until the fix — including the
smoke "aider wcwidth 1/38" (that's wcwidth's *baseline*, not agent incompleteness). The earlier
"floor-lib unlock +92pp" magnitudes were `-x` artifacts.

## 2. The fix

- **`_strip_agent_noise`** removes `.aider*`, `spec.md`, `__pycache__` **before** `git add -A`, so
  the branch (and commit0's patch) is clean code only. Proven: cachetools aider 153 (baseline) ->
  **207** after stripping; KD (always clean) was unaffected (201).
- Scoring routed through full-suite `commit0 test --branch` (never `-x`); every result JSON stamped
  `scoring` / `code_branch` / `patch_file` / `patch_sha256`.
- Provenance guard ([`baselines/check_scoring_provenance.py`](baselines/check_scoring_provenance.py))
  + CI fail if a new untagged competitor cell re-enters the matrix.

## 3. Re-validation executed

- **OpenAI cells (32) recovered for $0** — the agent code was committed to per-lib branches, so we
  re-scored existing branches (clean) with no LLM re-run.
- **smolagents × Sonnet (16) re-run** with the fixed runner -> scored correctly directly.
- **aider × Sonnet: 7 of 16** re-run valid; the other **9 corrupted by provider instability** (see §6).

## 4. Final matrix (honest, full-suite, pass-rate %)

Re-validated competitor columns (KD/OH unchanged; `n/a` = pending re-validation):

| lib | Aider-S | Aider-G | Sm-S | Sm-G |
|---|---|---|---|---|
| wcwidth | 84 | 92 | 84 | 95 |
| deprecated | 95 | 100 | 100 | 100 |
| cachetools | 100 | 96 | 100 | 99 |
| voluptuous* | n/a | 85 | 0 | 89 |
| portalocker | 68 | 72 | 68 | 0 |
| pyjwt | 98 | 100 | 100 | 100 |
| chardet* | n/a | 50 | **100** | 79 |
| tinydb | 99 | 99 | 100 | 100 |
| simpy | n/a | 91 | 69 | 91 |
| imapclient | n/a | 0 | 55 | 60 |
| parsel | 70 | 74 | 61 | 64 |
| marshmallow* | n/a | 0 | 0 | 32 |
| cookiecutter | n/a | 4 | **100** | 64 |
| babel* | n/a | 0 | **100** | 0 |
| jinja* | n/a | 0 | **100** | 100 |
| minitorch* | n/a | 0 | 0 | 0 |

(* floor lib.) The aider/Sonnet `n/a` cells retain old `-x` data, marked pending in the analysis
and rendered `n/a` in Figure 1.

## 5. What the corrected data shows

- **The old `-x` numbers were false** (everything looked ~97%). Honest full-suite: very high on
  well-formed libs (deprecated/pyjwt/tinydb/cachetools ~100%) and **real, large floor-lib unlocks**
  — smolagents×Sonnet cracks **chardet 100%, cookiecutter 100%, jinja 100%, babel 5663/5663
  (verified: +6652 lines of real impl; baseline can't even collect)**.
- **Complementary weaknesses (the paper's thesis), now real:** aider produces **no code** on
  collection-broken libs (jinja/marshmallow/cookiecutter/imapclient) — its test-feedback loop can't
  engage when collection is broken — while smolagents (CodeAct) handles them. Opposite asymmetries
  exist (e.g. smolagents×GPT portalocker 0 vs aider 72).
- These are **per-cell**; the fingerprint is a diagnostic, not a leaderboard (consistent with the
  paper's framing).

## 6. The aider × Anthropic gap — diagnosed, not a key/cap problem

9 aider/Sonnet cells remain old `-x`. Split:
- **3 provider-limited** (voluptuous, chardet, simpy): aider *can* do these (aider×OpenAI =
  126/149, 188/376, 128/140), but **3 separate Anthropic attempts all degraded** into `$0`/baseline.
- **6 genuine fails**: jinja/marshmallow/cookiecutter/imapclient (collection-broken for aider) +
  babel/minitorch (corpus).

**Diagnostics rule out a rate cap:** the key shows Tier-4 limits (2M ITPM, 4000 RPM); a 20-call
burst and a sustained ~80K-token heavy probe both ran **100% clean**. The long-run failures are
connection-level (`server disconnected` / 600s timeout) and **duration/window-dependent** — i.e.
connection instability over multi-hour runs (WSL networking and/or transient capacity), **not** a
throughput cap. **A new/higher key would not help.** Mitigations applied/identified: paced+gated
`repeat_runner` (no corruption on failure), **fail-fast 180s timeouts** (was litellm 600s), and —
to actually land the 3 cells — run **off-WSL2 / off-peak** (deferred).

**The science is covered without these 9:** aider capability via OpenAI, Anthropic side via
smolagents. They are a documented operational gap.

## 7. Named architectural blockers (corrects the campaign AAR)

- **minitorch — collection-gated on `SimpleOps.cmap`** (NOT the numba/corpus issue earlier
  assumed): `tests/test_tensor_general.py:21` does `TensorBackend(SimpleOps)` at import, whose
  `__init__` calls `ops.cmap(...)`; the baseline `SimpleOps` omits `cmap` -> all 10 test files error
  at collection -> 0 on every architecture.
- **Collection-broken floor libs** (jinja relative-imports, marshmallow attribute-access): block
  test-feedback agents (aider) entirely; CodeAct (smolagents) can still write code.

## 8. Testing fixes applied this session (harness, not the kaizen algorithm)

T1 noise-safe scoring · T2 full-suite-only · T3 collection-race retry (0/0/0 + partial collapse) ·
T4 mtime-watermark run selection · T5 seed/temp capture (recorded; runner-honoring TODO) ·
T6 one analyzer/parser · T7 errors-vs-failed split · plus **#3 fail-fast 180s timeouts**. Consolidated
in [`baselines/sampling/score_branch.py`](baselines/sampling/score_branch.py); analysis made
cross-platform (ascii-safe).

## 9. Artifacts & provenance

- 55 valid cells: `scoring` tags + clean `results/patches/*.patch` (sha-verified). Old `-x` data
  archived under `results/_pre_revalidation/`.
- Guard `EXPECTED_PENDING = 10` (9 aider/Sonnet cells + their aggregate).
- Figure 1 regenerated (pending cells -> `n/a`).
- Data-integrity audit: 0 failures, aggregates consistent, no residual bug-signature.

## 10. What remains (deferred, not blocking)

1. **3-cell off-WSL/off-peak retry** for aider×Sonnet voluptuous/chardet/simpy (paced `repeat_runner`).
2. **Statistical sampling re-test** ([`SAMPLING_PLAN.md`](SAMPLING_PLAN.md)) — scaffolding landed;
   Phase A (cheap) not yet run.
3. **Fold the delta-side *Recommendations*** (shared `score_branch` into production runners, B.5
   leakage-scan reframe, aggregator unification) back into `benchmarks-delta`.

## Closing

The matrix is now single-yardstick, honest, and defensible: a real scoring bug was found, fixed,
and the affected cells re-validated full-suite; the surviving zeros are explained (named blockers,
corpus, or a diagnosed provider gap). The corrected data **strengthens** the paper's thesis —
complementary, per-library architectural weaknesses are now backed by full-suite numbers instead of
`-x`-inflated ones.
