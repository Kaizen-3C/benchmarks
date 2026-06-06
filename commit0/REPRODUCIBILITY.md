# Measurement reproducibility (commit0 matrix)

Evidence for the paper's **reproducible-methodology** claim. The *measurement* (score a
fixed code artifact with `commit0 test --branch`) is deterministic and should reproduce
the published counts. This records how we verified that, the result, and the open gaps.
All verification is **$0 LLM** (Docker pytest only) — it re-scores committed code, it does
not call any model.

## Tooling

- [`baselines/verify_artifacts.py`](baselines/verify_artifacts.py) — branch-based: re-score
  the git branch named in each result JSON, diff vs published counts. **Valid only for
  architectures with provider-specific branches** (single_shot, reflexion).
- [`baselines/verify_patches.py`](baselines/verify_patches.py) — patch-based: apply each
  cell's committed per-provider `patch.diff` onto clean `commit0`, score, diff. **This is
  the faithful method and the one an external reviewer uses** (works for aider / smolagents /
  kaizen_delta, whose runners share one branch name across providers).

## Result (2026-06)

| Verifier | Cells scored | Reproduce exactly | Non-repro |
|---|---:|---:|---|
| Branch (single_shot + reflexion) | 58 | **56** | 2 |
| Patch (aider + smolagents) | 44 | **44** | 0 |
| **Total (faithful + scored)** | **102** | **100 (98%)** | **2** |

- The KD **headline claim reproduces**: `voluptuous/kaizen_delta` → 58/91 = **39%**.
- The `pyjwt` denominator spread (182 vs 259) **reproduces** → it is real, code-dependent
  test collection (a methodology caveat, below), not a scoring bug.
- **Patch-based reproduction was 44/44** — zero real mismatches on the artifacts an external
  party would use.

The 2 branch-verified exceptions: `portalocker_single_shot_openai` (33/7 → 35/5, two tests
flipped — env-sensitive) and `tinydb_reflexion_openai` (recorded counts were empty `0/0/0`).

## Known limitations & open items (NOT counted as reproduction failures)

1. **Harness timeouts (11 cells).** Big suites (babel = 5663 tests, marshmallow, jinja) can
   exceed the score timeout and yield a false `0/0/0`. `score_branch` now takes `timeout_s`
   and `verify_patches` sets generous per-lib timeouts; babel still needs a longer budget /
   re-score. Not a data defect.
2. **Empty patches (9 cells).** Cells where the agent produced no applyable code
   (collection-crash floor libs: babel/jinja/marshmallow/minitorch/voluptuous/imapclient
   aider-openai, etc.). The empty diff → baseline collection-error, which matches their
   recorded collection counts. **`cookiecutter_aider_openai` is the exception** (empty patch
   but recorded 16/325) — a genuine provenance gap to re-derive.
3. **Un-verifiable from committed artifacts (41 cells).**
   - **kaizen_delta (32):** the runner uses a single `kaizen_delta` branch for both providers
     (only the last-run provider's code survives) **and exports no patch** — so at most one
     provider per cell is recoverable. A provenance limitation of the KD runner.
   - **9 legacy `aider × anthropic`:** the `pytest -x` cells never re-run (the documented gap).
4. **Confirmed silent-baseline defect.** `imapclient_kaizen_delta` recorded `16/7/15` =
   exactly the single-shot baseline; the real code re-scores to `25/62/4`. The patch-noise
   bug reached a KD cell. (See CORRECTIONS.md.) `voluptuous_kaizen_delta_openai` recorded ==
   baseline too.
5. **Patch artifacts need LF normalization.** The committed `.patch` files carry Windows
   CRLF + no trailing newline, so `git apply` reports "corrupt patch". `verify_patches`
   normalizes on the fly; the files in the data PR should be re-committed normalized so an
   external reviewer can apply them directly.

## Methodology caveat surfaced (for the paper)

For libs whose **test modules import the agent's code** (pyjwt, chardet, ...), *test
collection — and therefore the pass-rate denominator — depends on the generated code*.
Denominators are not constant across cells of the same lib (e.g. pyjwt `single_shot_sonnet`
collects 182, `single_shot_openai` 259, both reproducibly). Pass-**rates** across such cells
are therefore not directly comparable; the value-add metric and PROTOCOL should note this.

## Reproduce it yourself ($0, no API keys)

```bash
# in the WSL workspace (commit0 + Docker), patches extracted from the data PR:
python baselines/verify_patches.py  --results-dir <results> --patches-dir <patches> --out report.json
python baselines/verify_artifacts.py --results-dir <results> --all --out report_branch.json
```
