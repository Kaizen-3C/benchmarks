# Mutation harness — scope (follow-on)

**Goal.** Bound the probability of an *undetected* scoring/data defect by testing our
*detectors*, not the data. A per-defect sweep finds known defect classes; an audit finds
inconsistencies. Neither tells you **"if a bug existed, would we catch it?"** Mutation
testing answers exactly that: inject a known fault, confirm a detector fails; if a mutant
**survives** (all detectors stay green), we've found a blind spot to close.

This is the meta-validation that lets the paper claim *"we would have caught it"* rather
than *"we looked and didn't see it."*

## Mechanism

For each mutation `m` in a catalogue:
1. Apply `m` to a **copy** of the scoring/data (a temp results dir or a patched module).
2. Run the detectors: `check_scoring_provenance.py`, `audit_matrix.py` (and, where the
   mutation is in scoring *code*, a re-score on one cell).
3. Record **killed** (some detector exits non-zero) or **survived** (all green).
4. Revert. Never touch the real `results/` or committed modules.

Output: a kill-matrix (mutation × detector) + a list of survivors. Survivors are the
actionable result — each names a defect we could ship undetected.

## Mutation catalogue (initial)

**Data mutations** (inject into a copied results dir; should be killed by the guard/audit):
- `D1` flip a cell's `scoring` to `commit0-test-full-suite` while leaving `final_counts`
  0/0/0/0 → must be killed (mis-stamp check).
- `D2` corrupt a `patch_sha256` → must be killed (patch-sha check; requires patches present).
- `D3` set an aggregate `per_library` entry's counts to differ from the standalone → must
  be killed (triangulation).
- `D4` replace a competitor cell's counts with the single-shot baseline's counts → should
  be flagged (silent-baseline tell) for a healthy cell.
- `D5` change one fully-collected cell's `collected` so a lib's denominators disagree →
  must be killed (denominator invariance).
- `D6` blank a tagged cell's `patch_file` → must be killed (provenance completeness).
- `D7` set a passed>0 cell's `cost_usd` to 0 with a valid scoring tag → should be flagged
  (cost anomaly).

**Code mutations** (patch a scoring module in a temp copy; re-score one cell, expect the
result to change *and* a detector to notice):
- `C1` drop `re.I` from `_counts_from_summary` → an upper-case summary mis-parses to 0 →
  should surface as a mis-stamp / 0-collected on a known-non-zero cell.
- `C2` revert the `collected>0` gate in `_persist_and_score` → a 0-collected cell gets
  stamped full-suite → must be killed (mis-stamp).
- `C3` revert `git(..., check=True)` to swallow errors, force a `git add` failure →
  baseline scored silently → should surface (silent-baseline / denominator).
- `C4` skip `_strip_agent_noise` → binary noise → container patch-apply fails → baseline
  scored → should surface (silent-baseline / denominator drop).

## Success criteria

- **Every `Dn` killed** by at least one detector → the audit/guard cover the known classes.
- **Every `Cn`** produces a detectable downstream signal → the runtime fixes are observable.
- **Any survivor** → open a ticket; add a detector rule until it's killed. Track the
  **kill rate** over time; the paper can cite "N mutations, M killed, K survivors closed."

## Cost & placement

Pure-data mutations (`D*`) are **$0** and fast (operate on copied JSONs). Code mutations
(`C*`) need **one re-score per mutation** in WSL (Docker pytest, no LLM = $0 spend, minutes
each). Harness: `commit0/baselines/mutation_harness.py` (not yet built). Run manually first;
wire the `D*` subset into CI once green.
