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

Final tally after clearing the orphaned-container noise (below) and re-scoring those cells:

| Verifier | Cells scored | Reproduce exactly | Non-repro |
|---|---:|---:|---|
| Branch (single_shot + reflexion) | 64 | **60** | 4 |
| Patch (aider + smolagents, non-empty) | 46 | **46** | 0 |
| **Total (faithful + scored)** | **110** | **106 (96%)** | **4** |

- The KD **headline claim reproduces**: `voluptuous/kaizen_delta` → 58/91 = **39%**.
- The babel **headline cell reproduces**: `babel/smolagents-anthropic` → **5663 passed** (in 17s,
  once the stale container is removed — see below).
- The `pyjwt` denominator spread (182 vs 259) **reproduces** → it is real, code-dependent
  test collection (a methodology caveat, below), not a scoring bug.
- **Patch-based reproduction was 46/46** — zero real mismatches on the artifacts an external
  party would use.

The **4 real non-reproductions**:
- `portalocker_reflexion_sonnet` / `_openai` — the committed reflexion branch is **corrupt**: the
  LLM's chain-of-thought prose leaked into `portalocker/utils.py` (`"Wait - I still haven't
  resolved the semaphore test..."`) → `SyntaxError` → import fails → `0/0/0`. The recorded
  `30/10` / `13/27` were scored from clean code that was never committed; **reflexion exports no
  patch**, so these are unverifiable from the committed artifact. (A reflexion-runner provenance
  defect — committed code ≠ scored code.)
- `portalocker_single_shot_openai` (33/7 → 35/5, two tests flipped — env-sensitive).
- `tinydb_reflexion_openai` (recorded counts were empty `0/0/0`).

## Known limitations & open items (NOT counted as reproduction failures)

1. **Orphaned-container failures (RESOLVED).** The cells that first showed `0/0/0` were *not*
   timeouts — a leftover `commit0.eval.<lib>` container (e.g. babel's, "Up 37 hours" from a
   killed prior run) made commit0 fail with a 409 name-conflict in ~3s → false `0/0/0`. babel
   actually runs in <10s and reproduces `5663 passed` once the orphan is removed. `score_branch`
   now `docker rm -f`s any stale `commit0.eval.<lib>` before each run (self-healing). All 6 babel
   cells reproduced on re-score; only `portalocker_reflexion` remained (corrupt branch, above).
   Not a data defect.
2. **Empty patches (9 cells) — adjudicated.** Cells where the agent produced no applyable
   code (collection-crash floor libs). An empty patch means "no change → score the `commit0`
   baseline"; `verify_patches` now scores the baseline for a 0-byte patch. **8 of 9 are
   consistent** — recorded counts == baseline (e.g. `imapclient_aider_openai` 0/0/18,
   `minitorch_*` 0/0/10, `babel_aider_openai` 0/0/22), i.e. they faithfully reproduce.
   **`cookiecutter_aider_openai` is a confirmed provenance gap:** recorded `16/325/26` ≠
   baseline `111/242/14`, yet both the patch (empty) *and* the shared `aider` branch (an empty
   commit) hold no code — the agent code that produced these counts was never persisted. The
   value is a real non-baseline result from the original run but is **not independently
   reproducible** from committed artifacts (flagged `provenance_gap` in its JSON; counts
   retained, not proven wrong).
3. **Un-verifiable from committed artifacts (41 cells).**
   - **kaizen_delta (32):** the runner uses a single `kaizen_delta` branch for both providers
     (only the last-run provider's code survives) **and exports no patch** — so at most one
     provider per cell is recoverable. A provenance limitation of the KD runner.
   - **9 legacy `aider × anthropic`:** the `pytest -x` cells never re-run (the documented gap).
4. **Confirmed silent-baseline defect.** `imapclient_kaizen_delta` recorded `16/7/15` =
   exactly the single-shot baseline; the real code re-scores to `25/62/4`. The patch-noise
   bug reached a KD cell. (See CORRECTIONS.md.) `voluptuous_kaizen_delta_openai` recorded ==
   baseline too.
5. **Patch CRLF / apply hygiene (RESOLVED).** The committed `.patch` blobs are stored **LF**
   and their `patch_sha256` matches; the CRLF only appeared on Windows checkout (autocrlf).
   `.gitattributes` now marks `commit0/results/patches/** -text`, so checkouts preserve the
   exact LF bytes on every platform (sha-verify + apply work). The patches are kept
   **byte-faithful** to the scored code (some preserve a no-trailing-newline final line, so
   plain `git apply` needs `--recount` + a trailing newline — `verify_patches` does this
   automatically; documented in `commit0/results/patches/README.md`). We deliberately did NOT
   rewrite the patch bytes (which would desync the recorded shas from the original run).

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
