# Re-validation plan — Phase 1 (Aider + smolagents) full-suite re-scoring

**Status:** OPEN — scoring fix landed in the runners; re-run not yet executed.
**Owner:** (assign before spend)
**Estimated model spend:** ~$65 (one Phase-1 re-run; see §4)
**Canonical issue doc — link here from anywhere that quotes a Phase-1 number.**

---

## 1. The defect (what makes Phase-1 numbers non-reproducible)

The two Phase-1 competitor runners scored the **authoritative** pass/fail counts with
`pytest -x` (stop at the first failure):

- [`baselines/aider/_aider_runner.py`](baselines/aider/_aider_runner.py) — `DEFAULT_TEST_CMD = "pytest -x --tb=no -q"`, reused by `_final_pytest`.
- [`baselines/smolagents/_smolagents_runner.py`](baselines/smolagents/_smolagents_runner.py) — same, plus the in-prompt command at the old line ~203.

Every other architecture (B2 single-shot, B3 reflexion, KD) scores the **full suite**
through `run_pytest_via_commit0()` in
[`baselines/single_shot_sonnet.py`](baselines/single_shot_sonnet.py) (`commit0 test <lib> <test_dir> --branch ...`, no `-x`).

`-x` truncates the denominator to whatever ran *before the first failure*. Every committed
Aider/smolagents "win" therefore ends in exactly **"N passed, 1 failed"** with a tiny
collected count, against suites that are 150–376 tests:

| Lib | True suite¹ | Aider/smol collected | Committed result |
|---|---:|---:|---|
| chardet | 376 | 7 | 6 passed, **1 failed** → "86%" |
| jinja | unknown² | 25 | 24 passed, **1 failed** → "96%" |
| marshmallow | unknown² | 12 | 11 passed, **1 failed** → "92%" |
| cookiecutter | 367 | 15–61 | N passed, **1 failed** |
| voluptuous | 149 | 12 | 11 passed, **1 failed** → "92%" |

¹ From the max collected across the full-suite architectures (KD/B2/B3).
² jinja & marshmallow have **no trusted denominator anywhere in the repo** — collection
is broken (0 collected) on every full-suite architecture, and the OH report stores only an
aggregate `total_tests`, not per-lib. A quantitative rate for these two cannot be stated
without a re-run.

This violates the repo's own scoring rule, [`PROTOCOL.md` §6 line 307](PROTOCOL.md)
("(sum of tests_passed) / (sum of tests_total) … its full test count to the denominator —
there are no 'free' exclusions"). The rates feed straight into
[`baselines/value_add_fingerprint.py`](baselines/value_add_fingerprint.py) (`lib_passrate`,
≈line 29) and therefore into Figure 1.

**Why offline re-scoring is impossible (validated 2026-06-02):** the competitor code was
**never persisted anywhere**, so there is nothing to re-score against:

- The runners never commit, branch, or export a diff. Aider runs with
  `auto_commits=False, dirty_commits=False` ([`_aider_runner.py`](baselines/aider/_aider_runner.py));
  smolagents edits the working tree via the agent's `Path.write_text`. Their only disk writes
  are `spec.md` and the result JSON.
- The committed JSONs carry **zero code** — keys are
  `[repo, model, branch, elapsed_s, final_summary, final_counts, totals, *_diagnostics]`. No
  source, no diff, no `per_file`. (`"branch": "aider"` is a label string, not a git ref.)
- There are **no code artifacts** in `results/` — only JSON count files.

The generated code existed only as uncommitted working-tree edits under
`~/kaizen-commit0/<lib>/` on the WSL host, overwritten on each subsequent run. Unrecoverable.
We cannot know how many post-`-x` tests would have passed, so the only path to a defensible
number is to **re-run** with full-suite scoring **and persist the code this time** (§7).

> Contrast: KD *does* commit its output to a per-repo `kaizen_delta` git branch
> ([`kaizen_delta.py`](baselines/kaizen_delta.py) lines 388–526) and scores via
> `commit0 test --branch` — which is why Stage-2 can reseed from it. But those branches also
> live only in the WSL workspace, never mirrored into this repo. "Not in the repo" is true for
> every architecture; "never committed anywhere" is true specifically for the two competitors.

---

## 2. What is validated reproducible (keep as-is — NOT in scope for the re-run)

- **Deterministic code/methodology facts** — the `-x` vs full-suite asymmetry itself; anyone can `grep` it.
- **B2 single-shot, B3 reflexion, KD, OH** cells — scored via full-suite `commit0 test`; protocol-compliant and mutually comparable (modulo model nondeterminism).
- **All four analysis scripts** — execute and regenerate their tables from the committed JSONs (`python baselines/value_add_fingerprint.py` etc.).
- **The qualitative Phase-1 finding** — "Aider/smolagents get *past test collection* on jinja & marshmallow where KD collects 0 tests." This is true regardless of `-x` (0 vs >0 collected) and is the genuine, defensible competitor contribution. Only the *magnitude* (+92pp/+96pp) is unvalidated.

## 3. What must be re-tested (in scope)

| Item | Reason |
|---|---|
| Every Aider & smolagents **per-lib rate + value_add_pp** (4 cells × 16 libs) | scored under `-x` |
| Phase-1 **aggregate headline** (493/506, 385/398, 639/650, 830/843) | truncated denominators summed |
| Floor-lib **"unlock +Npp"** claims | competitor(`-x`) vs baseline(full-suite) mixes yardsticks |
| jinja / marshmallow **denominators** | unknown in the repo entirely |
| Aider **voluptuous cost = $0.00** (and any wall-capped cell's cost) | cost capture failed on capped runs |

---

## 4. Re-run procedure

Prereqs are the standard Phase-1 environment — WSL2, the `kaizen-commit0` venv, Docker — per
[`CAMPAIGN_README.md`](CAMPAIGN_README.md). The scoring fix is already in the runners (see §5),
so a plain re-run produces full-suite numbers.

```bash
# inside WSL, kaizen-commit0 venv
cd ~/kaizen-commit0/baselines

# Aider — both providers (move existing JSONs aside first; do not overwrite blind)
python aider/run_lite_aider.py --provider anthropic
python aider/run_lite_aider.py --provider openai

# smolagents — both providers
python smolagents/run_lite_smolagents.py --provider anthropic
python smolagents/run_lite_smolagents.py --provider openai
```

**Budget:** original Phase 1 was **$65.12** for exactly these four sweeps
([`AAR_2026-05-05_PHASE1_ADDENDUM.md`](AAR_2026-05-05_PHASE1_ADDENDUM.md)). Full-suite scoring
adds test iterations on the auto-test loop, so budget **$65–100** and re-confirm the wall-clock
caps. The Aider × Sonnet auto-test loop was the wall outlier (80–90 min on 3 libs) — expect that to persist or grow.

**Environment parity — resolved.** The runners now commit the agent's edits to a per-repo
`aider` / `smolagents` branch and score through `commit0 test --branch` — the identical Docker
path the full-suite cells use (§5, §7). Local `pytest` remains only as a fallback if `commit0
test` emits no parseable summary, flagged in the JSON's `"scoring"` field.

**After the re-run:**
1. Move the old JSONs to `results/_pre_revalidation/` (preserve provenance; don't delete).
   The re-run also writes per-cell patches to `results/patches/` — commit those too.
2. Regenerate analysis: `python baselines/value_add_fingerprint.py`, `phase1_summary.py`, `value_add_table.py`.
3. Regenerate Figure 1: `python paper/figures/figure1_fingerprint_heatmap.py`.
4. Update the headline tables in `README.md` and the Phase-1 AAR with the new numbers; remove the interim caveats this doc points to.
5. Fill in [`AAR_REVALIDATION_STUB.md`](AAR_REVALIDATION_STUB.md) (before/after deltas are
   pre-populated) and rename it `AAR_<date>_REVALIDATION.md`.
6. Lower `EXPECTED_PENDING` to 0 in the guard and confirm `--strict` exits 0.

---

## 5. Scoring + persistence fix applied (root cause)

Landed in [`_aider_runner.py`](baselines/aider/_aider_runner.py) and
[`_smolagents_runner.py`](baselines/smolagents/_smolagents_runner.py) so any future run is
protocol-aligned and self-documenting:

- Before editing, the runner opens a fresh branch off the pinned `commit0` starter
  (`_start_branch`: `checkout commit0` → `-b <arch>`). The agent's `-x` loop is unchanged
  (convergence heuristic only).
- After the agent finishes, `_persist_and_score`:
  1. commits the edits onto the `aider` / `smolagents` branch,
  2. scores the **full suite** via `commit0 test --branch <arch>` — the same Docker path as
     single_shot/reflexion/KD (local full-suite `pytest` only as a no-summary fallback),
  3. exports `git diff commit0..<arch>` to `results/patches/<lib>_<arch>_<provider>.patch`.
- Each result JSON is stamped `"scoring"` (`commit0-test-full-suite` or the local fallback),
  `"code_branch"`, `"patch_file"`, and `"patch_sha256"`.

Both modules compile clean. The agent SDKs (aider/smolagents) and the commit0 CLI are imported
lazily / invoked as subprocesses, so a full end-to-end exercise happens on the WSL re-run host.

**Provenance guard (implemented).** [`baselines/check_scoring_provenance.py`](baselines/check_scoring_provenance.py)
fails the build if a NEW untagged competitor cell appears (it tolerates the 68 known-legacy
`-x` JSONs as a pinned `EXPECTED_PENDING` baseline, and warns when that count drops so you lower
it). Wired into CI via [`.github/workflows/scoring-guard.yml`](../.github/workflows/scoring-guard.yml)
(stdlib only). Run `--strict` after the re-run to assert zero pending.

---

## 6. Affected committed artifacts

- 64 per-lib JSONs: `results/<lib>_aider_{anthropic,openai}.json`, `results/<lib>_smolagents_{anthropic,openai}.json`
- 4 aggregates: `results/aggregate_lite_{aider,smolagents}_{anthropic,openai}.json`
- Derived: Figure 1 (`paper/figures/figure1.*`) and any table that quotes a Phase-1 rate.

See [`results/SCORING_NOTICE.md`](results/SCORING_NOTICE.md) for the in-place data caveat.

---

## 7. Where the re-run saves generated code (so this never recurs)

Persisting the code is mandatory for the re-run — it makes results auditable, makes future
re-scoring possible without another paid run, and (via a branch) enables Docker-parity scoring
through the same `commit0 test` path every other architecture uses. Three layers, cheapest to
richest:

1. **Per-repo git branch `aider` / `smolagents`** (mirrors KD). Before scoring, the runner does
   `git checkout commit0 -b <arch>` at the start and `git add -A && git commit` after the agent
   finishes. This lives in the WSL workspace (`~/kaizen-commit0/<lib>/`), same as the KD
   branches. **Primary benefit:** the authoritative score can then run via
   `commit0 test <lib> <test_dir> --branch <arch>` — byte-identical scoring path to
   single_shot/reflexion/KD, resolving the local-pytest-vs-Docker parity caveat in §4. This
   supersedes the interim local `SCORING_TEST_CMD` fix.

2. **Committed patch artifact in THIS repo** (the durable, public, workspace-independent copy).
   After the run, export `git diff commit0..<arch>` to
   `results/patches/<lib>_<arch>_<provider>.patch` and commit it. Small, reviewable, and enough
   to reconstruct the exact code (apply patch onto the pinned `commit0` starter at the recorded
   `dataset_sha`) and re-score offline forever after. This is the artifact that would have made
   the *current* re-run unnecessary.

3. **JSON provenance fields** so a cell points at its own code:
   `"code_branch": "<arch>"`, `"patch_file": "patches/<lib>_<arch>_<provider>.patch"`,
   `"patch_sha256": "<hash>"`, alongside the existing `"scoring"` tag.

**Status: implemented (2026-06-02).** All three layers are wired into both runners (see §5):
layer 1 (branch + `commit0 test --branch` scoring) also fixes parity, layer 2
(`results/patches/*.patch`) is the public-repo guarantee, layer 3 (`code_branch` / `patch_file`
/ `patch_sha256` JSON fields) is the audit trail. Storage is trivial — these are stub libraries
and the diffs are a few KB each. The $65 re-run now buys permanently-reproducible artifacts
rather than another set of disposable counts.
