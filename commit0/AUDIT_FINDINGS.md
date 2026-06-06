# Matrix audit findings (unknown-defect sweep)

Produced by `python commit0/baselines/audit_matrix.py` — a floor-free, triangulation +
invariant audit designed to surface defects we never enumerated (see the module docstring).
This file records what it surfaced and how each item is being resolved. The provenance
guard (`check_scoring_provenance.py`) covers the *known* defect classes; this audit covers
the *unknowns*.

## Resolved (corrected in-place, $0)

- **4 stale aggregate `scoring` tags.** `aggregate_lite_*` still tagged 4 cells
  `commit0-test-full-suite` after the standalone cells were re-marked
  `pending-regeneration` (the mis-stamped collection-crash cells). Triangulation
  (aggregate ↔ standalone) caught the incomplete edit. Aggregate entries updated to
  match: `aider_openai/marshmallow`, `aider_openai/jinja`,
  `smolagents_anthropic/marshmallow`, `smolagents_openai/portalocker`.

## Open — require the deterministic re-score (step 3) to adjudicate; NOT guess-edited

These are genuine *unknowns* the sweep found. Ground truth comes from re-running
`commit0 test --branch` on the committed code, not from editing JSONs.

1. **`kaizen_delta_anthropic/voluptuous` aggregate ≠ standalone (HARD).**
   Aggregate records **0/0/0/2 (0%)**; the standalone cell records **58/91 (39%)**.
   39% is the *headline-cited* KD result ("voluptuous 0% → 39%"), and
   `value_add_fingerprint.py` / Figure 1 read the **standalone**, so the published number
   is internally consistent — but the aggregate is **stale** (pre-unlock). **Action:**
   re-score voluptuous on the KD-anthropic branch; if it confirms ~39%, regenerate the
   aggregate; if not, the headline finding must be corrected. **This gates a paper claim.**

2. **`pyjwt` denominator varies 182↔259 across fully-collected cells (HARD).**
   e.g. `single_shot_sonnet=182` vs `single_shot_openai=259` (same architecture, different
   provider). Likely a real **methodology subtlety**: for libs whose test modules import
   agent-written code, *test collection — and thus the pass-rate denominator — depends on
   the generated code*, so pass-RATES across such cells are not directly comparable.
   **Action:** re-score + inspect `test_output.txt` for the 182 vs 259 cells; if confirmed,
   document the denominator-comparability caveat in PROTOCOL.md and ensure the value-add
   metric accounts for it. (If counts don't reproduce, it's a scoring bug instead.)

3. **`chardet` 376 vs 394 (WARN).** `smolagents_openai=394`, all others `376`. chardet is
   collection-sensitive; one cell likely unlocked 18 more tests. Low priority; confirm on
   re-score.

4. **Two cells identical to the single-shot baseline (WARN)** — verify the patch applied
   (not a silent baseline scored): `kaizen_delta_anthropic/imapclient` (16/7/0/15) and
   `reflexion_openai/chardet` (1/375/0/0). Both *could* be legitimate "architecture added
   nothing over single-shot," but a re-score / patch diff confirms it.

## Not run in this checkout

- **Patch-sha verification** is SKIPPED here because `commit0/results/patches/` lives in the
  data PR (#4). Run `audit_matrix.py` on a checkout/branch that has the patches, or in the
  WSL workspace, to verify every `patch_sha256` against its file.

## Meta-note (why the first audit run was noisy)

The first pass reported ~46 "hard" findings; tightening removed false positives that came
from the *audit's own* crude heuristics — a hardcoded floor-lib set (replaced by the
floor-free "fully-collected cells must agree" invariant) and a provenance check that
duplicated the guard without its known-pending tolerance. The lesson — detectors must
themselves be validated — is exactly what the mutation harness (`MUTATION_PLAN.md`) is for.
