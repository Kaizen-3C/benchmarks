# Corrections

This document records material errors found in this repository's published numbers, in
the spirit of leading with our own mistakes. It is linked from the top of the
[README](README.md). For the operational detail of the re-run see
[`commit0/AAR_2026-06-04_REVALIDATION.md`](commit0/AAR_2026-06-04_REVALIDATION.md) and
[`commit0/RE-VALIDATION.md`](commit0/RE-VALIDATION.md).

---

## 2026-06 — Phase-1 (Aider / smolagents) pass-rates were wrong (two scoring bugs)

**Scope.** Only the **Aider** and **smolagents** cells (the 2026-05 "Phase 1" additions)
were affected. The single-shot (B2), reflexion (B3), Kaizen-delta (KD), and OpenHands (OH)
cells were scored by a different, correct path and are **unchanged**.

**Direction of the error.** The original Phase-1 numbers were **inflated** — high pass-rates
over implausibly small denominators. The corrected full-suite numbers are lower (and, for the
OpenAI cells, dramatically larger denominators).

### Bug 1 — `pytest -x` denominator truncation

The Aider/smolagents runners scored with `pytest -x`, which **stops at the first failure**.
A cell that should report "N passed out of the full suite" instead reported, e.g.,
"39 passed, 1 failed" over a handful of tests — a truncated denominator. This both inflated
the apparent pass-rate and made the cells non-comparable to the full-suite (`commit0 test`)
cells, violating [`commit0/PROTOCOL.md`](commit0/PROTOCOL.md) §6.

### Bug 2 — patch-noise in the committed branch → silent baseline scoring (critical)

`commit0 test --branch` applies the agent's branch as a `patch.diff` **inside the scoring
container**. The runners committed the agent's working tree with `git add -A`, which swept in
**binary agent noise** — `.aider.tags.cache.v4/*` (sqlite databases), `spec.md`, `__pycache__`.
The binary diff **fails to apply** in the container, and commit0 then silently scores the
**unmodified baseline** with no error raised.

- **Tell-tale:** identical cross-architecture scores (aider == smolagents == baseline) despite
  the agents having produced different code.
- **Proof:** `cachetools` aider scored 153 (the baseline) before the fix and **207** after the
  agent noise was stripped — the patch then applied and the agent's real code was scored.

### The fix

- Strip agent noise (`.aider*`, `spec.md`, `__pycache__`) **before** `git add -A`, so the
  branch — and thus the container's `patch.diff` — is clean code only.
- Always score the **full suite** via `commit0 test --branch` (never `-x`).
- Gate the "scored via commit0" provenance on a **parseable** pytest summary, not merely a
  non-empty one (commit0 falls back to the last 500 bytes of stdout/stderr otherwise, which
  would mis-stamp a cell as full-suite-scored with zero counts).
- Stamp every cell with `scoring` / `code_branch` / `patch_file` / `patch_sha256` provenance.
- A **provenance guard** ([`commit0/baselines/check_scoring_provenance.py`](commit0/baselines/check_scoring_provenance.py))
  and a CI workflow fail the build if a new untagged competitor cell re-enters the matrix.

### Corrected numbers

| Cell | Original (wrong) | Corrected (full-suite, 2026-06) |
|---|---:|---:|
| Aider × Sonnet | 493 / 506 | **partial — 7 / 16 cells** (9 a documented provider gap) |
| Aider × GPT-5.4 | 385 / 398 | **1,508 / 2,212** |
| smolagents × Sonnet | 639 / 650 | **8,437 / 8,638** |
| smolagents × GPT-5.4 | 830 / 843 | **3,223 / 4,519** |

The authoritative per-cell matrix is regenerated from the checked-in `commit0/results/*.json`
by `python commit0/baselines/value_add_fingerprint.py` and by Figure 1
(`paper/figures/figure1_fingerprint_heatmap.py`).

### Re-validation status

- **OpenAI cells (32) recovered for $0** — re-scored from the already-committed branches; no LLM
  re-run was needed.
- **smolagents × Sonnet (16)** re-run with the fixed runner.
- **Aider × Sonnet: 7 / 16** valid; the other **9 cells are a documented provider-limited gap**
  (connection/duration-level failures on the run host, *not* a rate cap — diagnostics ruled that
  out). They render `n/a` in Figure 1 and are flagged pending by the provenance guard.

### Known limitations (honesty about what is *not* yet established)

- **n = 1.** Every per-cell number is a **single-run point estimate** with native LLM sampling
  variance. There are **no confidence intervals yet**. A statistically-significant re-test
  (repeated draws, bootstrap CIs, Welch tests, BH-FDR, sign-stability) is planned and scaffolded
  under [`commit0/baselines/sampling/`](commit0/baselines/sampling/) ([`SAMPLING_PLAN.md`](commit0/SAMPLING_PLAN.md)).
- **Not bit-reproducible.** The runners do not yet honor a fixed temperature/seed, and provider
  behavior is time-dependent, so an independent re-run will not match exactly.
- **Provenance artifacts.** The exact code each agent produced is exported as a per-cell
  `patch.diff` under `commit0/results/patches/`, each referenced by `patch_sha256` in the
  corresponding result JSON. (These ~135k lines of generated data are tracked via a separate
  data PR to keep the code/docs PR within automated-review size limits.)

### Effect on the methodology paper

The complementary-weakness thesis (each architecture's weakness is another's strength) is
re-checked against the corrected full-suite numbers and still holds; any quantitative claim that
descended from the original `-x` numbers must be re-derived from the regenerated matrix above.
