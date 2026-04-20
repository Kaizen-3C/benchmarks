# commit0 Greenfield — Evaluation Protocol

**Governed by:** [ADR-0060](../../.architecture/decisions/ADR-0060-commit0-greenfield-benchmark.md)
**Pilot target:** first Kaizen-delta evaluation on the spec-to-code (Greenfield) axis
**Size:** commit0-lite = 16 Python libraries; commit0-full = 54 libraries (gated on lite-SOTA result)
**Projected cost:** $30–80 for a full lite run with Sonnet 4.6; $200–500 for a full 54-library run

This document is the **operational specification** for running the commit0 benchmark under Kaizen-delta. It is intended to be detailed enough that another engineer could execute the benchmark end-to-end without further context. It deliberately mirrors the structure of [`benchmarks/realworld/PROTOCOL.md`](../realworld/PROTOCOL.md) so the two reports compose.

---

## 1. Corpus

### 1.1 Dataset (frozen)

- **HuggingFace dataset:** `wentingzhao/commit0_combined` (also: `wentingzhao/commit0_docstring`, used by upstream as default)
- **Splits used:**
  - `lite` — 16 repos, defined as `SPLIT_LITE` in [`commit0/harness/constants.py`](https://github.com/commit-0/commit0/blob/main/commit0/harness/constants.py)
  - `all` — 54 repos (gated; do not run before lite clears its threshold)
- **Dataset SHA:** pin once the pilot begins; record in every result JSON
- **commit0 CLI version:** pin (`pip install commit0==X.Y.Z`)

### 1.2 commit0-lite library list (16 libs)

| # | Library | Domain | Approximate spec size | Approximate test count |
|---|---------|--------|-----------------------|------------------------|
| 1  | `wcwidth`     | Unicode width    | small  | ~30 |
| 2  | `deprecated`  | Decorators       | small  | ~30 |
| 3  | `cachetools`  | LRU/TTL caches   | small  | ~80 |
| 4  | `voluptuous`  | Schema validation| small  | ~150 |
| 5  | `portalocker` | File locking     | small  | ~50 |
| 6  | `pyjwt`       | JWT tokens       | small  | ~100 |
| 7  | `chardet`     | Encoding detect  | medium | ~100 |
| 8  | `tinydb`      | Document DB      | medium | ~250 |
| 9  | `simpy`       | Discrete-event sim | medium | ~250 |
| 10 | `imapclient`  | IMAP client      | medium | ~150 |
| 11 | `parsel`      | XPath/CSS parse  | medium | ~200 |
| 12 | `marshmallow` | Serialization    | large  | ~600 |
| 13 | `cookiecutter`| Project scaffold | large  | ~400 |
| 14 | `babel`       | i18n             | large  | ~700 |
| 15 | `jinja`       | Templating       | large  | ~800 |
| 16 | `minitorch`   | Tensor library   | large  | ~250 |

(Per-lib counts are approximate — confirmed against actual repo at pilot start.)

### 1.3 Per-task inputs (provided by commit0)

Each task supplies:
- `spec.md` — natural-language specification, 10K–300K tokens, may include diagrams
- Starter repo with **typed function/method stubs** (signatures + docstrings, bodies replaced with `pass` or `raise NotImplementedError`)
- Hidden test suite (the original library's `pytest` suite, withheld from the model)
- Per-library Docker setup (Python version, system deps, install command)
- `setup.sh` to clone+install the starter repo

### 1.4 Oracle (fixed)

- **Primary:** the hidden `pytest` suite shipped with each library, executed inside the per-library Docker container provided by commit0
- **Scoring:** `# tests passed / # tests collected`, summed across libraries for aggregate

### 1.5 Reference upper bound

- **What:** the original published library at the version commit0 forked from. Establishes "what 100% looks like" — by construction this passes 100% of its own tests.
- **Role:** sanity check, not a baseline to beat.

---

## 2. Protocol

### 2.1 Phase 0 — Harness validation (once, before any Kaizen-delta runs)

Goal: confirm the runner is wired correctly by reproducing a published baseline number.

**Execution environment (REQUIRED):** all commit0 commands run inside **WSL2 (Ubuntu 24.04)**, not Windows. Docker Desktop's WSL backend serves the same daemon, so images built in either context are visible from both. Workspace lives at `~/kaizen-commit0/` on the WSL ext4 filesystem (NOT under `/mnt/c/...`, which is slow and has historical Windows-path-handling bugs in commit0 0.1.8 — see §6.1).

```bash
wsl -d Ubuntu-24.04 -- bash -lc '
  cd $HOME/kaizen-commit0
  . .venv/bin/activate
  commit0 <args>
'
```

| Step | Command (run in WSL) | Expected |
|---|---|---|
| 1 | `python3.12 -m venv .venv && . .venv/bin/activate && pip install commit0` | CLI installs cleanly (commit0 0.1.8+) |
| 2 | `commit0 setup lite` | clones 16 starter repos to `repos/` |
| 3 | `commit0 build --num-workers 4` | builds per-library Docker images (~40s) |
| 4 | `commit0 test <repo> tests --reference --backend local --timeout 600` (per repo, looped over the 16 lite libs) | runs hidden tests against reference impl; **must be 100% per library** (skipped tests OK) |
| 5 | Run a single-shot Sonnet 4.6 baseline on one library (e.g., `wcwidth`) | pass rate within ±10pp of published OpenHands-Index Sonnet number for that library |
| 6 | Record both in `results/phase0_harness_validation.json` |

If step 4 is not 100% (excluding skips), the harness is broken — stop and debug. If step 5 deviates wildly, our wiring of Sonnet calls is broken — stop and debug. Do NOT proceed to Kaizen-delta runs until both pass.

**Reference status (validated 2026-04-20):** `wcwidth` reference run on WSL Ubuntu 24.04 + commit0 0.1.8 + Docker Desktop → **38 passed, 1 skipped, 0 failed in 0.76s.** Same Windows-host run requires three local source patches; do not use it.

### 2.2 Phase 1 — Decompose the spec

Goal: extract architectural structure from `spec.md` into Kaizen-delta's canonical spec format.

**Inputs:**
- `spec.md` (per-library, provided by commit0)
- Stub file tree (signatures only, no bodies)
- `decompose/` pipeline from kaizen-delta

**Outputs (in `spec/<library>/`):**
```
spec/<library>/
  manifest.json          # run metadata, dataset SHA, decomposer version
  graph.json             # decomposition graph (see shared/schemas/)
  adrs/
    ADR-0001-<concept>.md     # extracted from "Architecture" / "Design" sections of spec.md
    ADR-0002-<concept>.md
    ...
  contracts/
    <module>.yaml             # one per decomposition node
    ...
  oracles/
    extracted_tests.jsonl     # per-stub: {function, signature, docstring_assertions, examples}
  gaps.json                   # things Decompose couldn't extract
```

**Note:** the *real* oracle is the hidden `pytest` suite; `extracted_tests.jsonl` only measures how well the Decomposer recovers the test contract from spec alone. It is a **diagnostic**, not the scoring target.

**Success criterion for Phase 1:**
- `spec/<library>/` validates against `shared/schemas/`
- Every public function/class in the stub tree appears in at least one contract
- `gaps.json` has ≤ 10 entries per library

### 2.3 Phase 2 — Recompose into stub bodies

Goal: fill the starter repo's stubs with implementations that pass the hidden tests.

**Inputs:**
- `spec/<library>/` from Phase 1
- Starter repo (stub files)
- `target.yaml`:
  ```yaml
  target:
    language: python
    python_version: ">=3.10,<3.13"   # per-library; commit0 ships the exact pin
    framework: <library-specific or none>
    packaging: pip                    # commit0 default; do not change
    test_runner: pytest
  direct_synthesis_max_lines: 80
  ```

**Outputs (in `out/<library>/`):**
```
out/<library>/
  <library>/                  # filled-in source tree
    __init__.py
    <module>.py               # stubs filled with implementations
    ...
  recompose_report.json       # per-stub: ADR-0002 short-circuit vs LLM generator; cost/time
```

**Two-tier strategy per ADR-0002:**

For each stub in the starter repo:
- Test if `(signature, docstring, contract)` matches a registered recipe's `translatable_shapes`
  - If match + prior-pass-rate gate clears + body size estimate ≤ 80 lines: emit via `recompose.src.short_circuit.short_circuit_or_defer()`
  - Otherwise: defer to the generator agent pipeline
- `recompose_report.json` records which path each stub took

**Expected short-circuit firing rate on commit0:** substantially higher than on RealWorld. Many commit0 stubs are pure functions with explicit type signatures and docstring examples — the exact regime ADR-0002 was designed for.

### 2.4 Phase 3 — Score against the hidden oracle

**Steps (per library):**

1. Copy `out/<library>/` over the starter repo (clobbers stubs with implementations)
2. `commit0 test <library>` — runs the hidden `pytest` suite inside the library's Docker container
3. Parse pytest JSON output (`--report-log` or via `pytest-json-report`) → count passed / failed / errored / collected
4. Record per-library result; advance to next library
5. `commit0 evaluate lite --output results/<timestamp>/` — aggregates across all 16 libs

**Result artifact (`results/commit0_lite_<timestamp>.json`):**
```json
{
  "dataset_sha": "...",
  "commit0_cli_version": "...",
  "kaizen_config": {
    "decomposer_version": "...",
    "recomposer_version": "...",
    "adr_0002_short_circuit": true,
    "model": "claude-sonnet-4-6",
    "provider": "anthropic"
  },
  "timestamp": "...",
  "split": "lite",
  "aggregate": {
    "libraries_total": 16,
    "libraries_built": 16,
    "tests_total": 4140,
    "tests_passed": 1280,
    "pass_rate": 0.309
  },
  "per_library": {
    "wcwidth":     {"tests_total": 30,  "passed": 28, "rate": 0.933, "build_status": "passed"},
    "deprecated":  {"tests_total": 30,  "passed": 30, "rate": 1.000, "build_status": "passed"},
    "cachetools":  {"tests_total": 80,  "passed": 64, "rate": 0.800, "build_status": "passed"},
    "...":         {}
  },
  "recompose_report_summary": {
    "stubs_total": 412,
    "short_circuit_adopted": 173,
    "generator_adopted": 235,
    "failed": 4
  },
  "cost_usd": 47.83,
  "wall_clock_seconds": 8400,
  "llm_call_count": 612
}
```

---

## 3. Baselines

Every Kaizen-delta result on commit0-lite is reported alongside at least baselines B0, B1, B4, and B5. B2 and B3 are run if API access is available.

### 3.1 B0: Reference (sanity check, not a competitor)

- **What:** the original library implementation at commit0's fork SHA.
- **Expected pass rate:** 100% by construction.
- **Purpose:** detects harness drift. If B0 ≠ 100%, the run is invalid — debug and rerun.

### 3.2 B1: OpenHands Index published numbers

- **What:** Sonnet, Opus, and GPT-5.2-Codex pass rates as published on the [OpenHands Index leaderboard](https://index.openhands.dev/greenfield).
- **How:** read off the leaderboard. **No rerun.** Cite the leaderboard SHA/snapshot date.
- **Purpose:** independent third-party reference points, not produced by us.

### 3.3 B2: Single-shot Sonnet 4.6

- **What:** feed `spec.md` + the entire stub file tree into one Sonnet call, ask for a complete implementation. No decomposition, no iteration.
- **Expected failure mode on large libs (jinja, babel, marshmallow):** context overflow or partial implementation; report whatever happens honestly.
- **Purpose:** establishes "what does the spec alone get you with one model call?" — the lower bound that any architecture must beat to justify itself.

### 3.4 B3: Reflexion-style iteration

- **What:** apply the `--reflexion-style` mode from the cdaor-benchmarks paper §5.8a. Iteration: generate → run hidden tests → reflect on failures → regenerate. Max 5 iterations per library.
- **Critical:** Reflexion sees test *output* (pass/fail counts, traceback) but NOT test source code. Otherwise it's gradient-descent on the oracle, not Reflexion.
- **Models to run:** primary arm on Sonnet 4.6 (matches §5.8a); secondary arm on a GPT-5.x model via `OPENAI_API_KEY` for cross-provider comparison against the OpenHands Index numbers.
- **Purpose:** validates whether "simple iteration wins" (as it did on HumanEval/MBPP §5.8a) extends to multi-file Greenfield tasks. If yes, Kaizen-delta's decomposition adds little; if no, decomposition is load-bearing.

### 3.5 B4: Kaizen-delta without ADR-0002 short-circuit

- **What:** disable the high-confidence bypass; route every stub through the full generator agent pipeline.
- **Purpose:** measures the marginal value of the test-aware adoption path on Greenfield (vs. ADR-0059 where it measures the same on D/R).

### 3.6 B5: Kaizen-delta with ADR-0002 short-circuit (primary)

- **What:** full Kaizen-delta pipeline as designed.
- **Purpose:** the headline configuration.

---

## 4. Iteration budget

Realistic timeline for a first commit0-lite pilot:

| Block | Activity | Deliverable |
|---|---|---|
| 0.5 day | Phase 0 harness validation (steps 1–6) | `phase0_harness_validation.json`; reference 100%, single-shot baseline within ±10pp of published |
| 1 day | Implement Decompose for commit0 specs (extract ADRs from spec.md sections, build contracts from stubs) | `decompose/src/` extended with commit0-spec extractor |
| 1 day | Implement Recompose for stub-fill (vs. RealWorld's whole-app generation) | `recompose/src/recipes/commit0_stubfill.py` |
| 0.5 day | End-to-end dry run on smallest 3 libs (`wcwidth`, `deprecated`, `cachetools`) — fix crashes, not quality | one runnable per-library output, any pass rate |
| 1–2 days | Iterate on decomposer granularity until lite aggregate ≥30% (the SOTA threshold) | `results/dry_run_*.json` showing progress |
| 1 day | Run all 5 baselines (B0, B2, B3, B4, B5; B1 is read-off) | `results/baselines_*.json` |
| 0.5 day | Paper section + figure generation | new §5.10 in `cdaor-benchmarks/paper/cdaor.md` |

**Total: ~5–6 working days for a first publishable lite result.**

If lite clears 30% on at least one configuration, gate to commit0-full opens (estimate +1–2 weeks for full 54-library run + retries).

---

## 5. Reproducibility requirements

- **Dataset:** pin `wentingzhao/commit0_docstring` (or `_combined`) revision SHA in result JSON
- **CLI:** pin `commit0==X.Y.Z` in `benchmarks/commit0/requirements.txt`
- **Runner:** pin OpenHands/benchmarks runner SHA if used; otherwise pin our own `benchmarks/commit0/runner.py` SHA
- **Docker:** per-library images use commit0's pinned base tags (do not override)
- **Models:** pin model strings exactly (e.g., `claude-sonnet-4-6`, no aliases)
- **Audit:** every LLM call logged via `cost_tracking/` with prompt + response + model version + timestamp
- **Scripts:**
  - `benchmarks/commit0/scripts/run_lite.sh` — full lite run, single configuration
  - `benchmarks/commit0/scripts/run_full.sh` — full 54-library run (gated)
  - `benchmarks/commit0/scripts/run_baselines_lite.sh` — runs B2, B3, B4, B5 on lite
- **Raw outputs:** preserve full `pytest` JSON per library, not just summary counts

---

## 6. Failure handling

A library can fail in several ways. Each is recorded distinctly so they're not confused with low pass rate:

| Failure mode | Detection | Recorded as |
|---|---|---|
| `commit0 build` fails | non-zero exit on `commit0 build <lib>` | `build_status: "failed"`, `tests_passed: 0` |
| Generated code doesn't import | `ImportError` on test collection | `build_status: "import_error"`, `tests_passed: 0` |
| Tests time out | wall-clock > 30 min/library (commit0 default) | `build_status: "timeout"`, `tests_passed: <count up to timeout>` |
| Tests fail | normal pytest failures | `build_status: "passed"`, `tests_passed: <real count>` |
| Decomposer crashes | exception in `decompose/` pipeline | library skipped, recorded in `failures.json` |

Aggregate pass rate is **(sum of tests_passed) / (sum of tests_total across all 16)**, regardless of build_status. A library that fails to build contributes 0 to the numerator and its full test count to the denominator — there are no "free" exclusions.

### 6.1 Host environment bugs (Windows)

commit0 0.1.8's local backend has three independent bugs when run directly on a Windows host (outside WSL). These were all discovered during Phase 0 on 2026-04-20 and patched in-tree to complete the validation spike; the supported path forward is **WSL2, not Windows patches**.

Documented for posterity and in case upstream PRs are warranted:

1. **`docker_utils.copy_to_container` backslash handling** — uses `pathlib.WindowsPath` to build bash commands for the Linux container; `shlex.split` chokes on `\` with `ValueError: No escaped character`. Fix: render container paths with `Path.as_posix()`.
2. **`run_pytest_ids` write mode** — `eval.sh` and `patch.diff` are written with Python's default text mode, which emits CRLF on Windows. bash inside the container then sees `set -uxo pipefail\r` as an invalid option name and bails in ~80 ms with no output. Fix: pass `newline=""` to `write_text()`.
3. **`execution_context.exec_run_with_timeout` file-collection** — `Path("/testbed") / "test_output.txt"` serializes as `\testbed\test_output.txt` on Windows, so the `test -e` check inside the container always fails and the output file is never collected back, even though it was created. Fix: render with `as_posix()` before bash interpolation; keep the Path for `src.name` use.

These only manifest when the commit0 CLI runs on a Windows-native Python interpreter. Inside WSL, stock `pip install commit0` works without any source modification.

---

## 7. Open questions to resolve before pilot

1. **Decomposer impedance:** commit0 specs are written for humans, not for the Decomposer. They will not have explicit "ADR" sections. We need to verify the Decomposer can produce useful ADRs from prose; if not, prepend a lightweight "spec-normalizer" pass (Sonnet, single call) that restructures `spec.md` into ADR-friendly headings before Decompose runs.
2. **Stub-vs-whole-file:** commit0 starter repos vary — some have one stub per file (easy), some have multiple stubs per file with shared state (harder). Recompose must handle both.
3. **Model alignment with OpenHands Index:** the Index reports Opus, GPT-5.2-Codex, Sonnet. We default to Sonnet 4.6 (cost). Decide whether to also run Opus for direct apples-to-apples on a subset (≥3 libs).
4. **HuggingFace token:** the dataset is public, so no `HF_TOKEN` needed. Confirm this still holds at pilot start (datasets can be gated retroactively).
5. **`.env` loading:** all provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OLLAMA_HOST`, `DEFAULT_LLM_PROVIDER`) live in the project-root `.env`. Runner scripts must `source .env` (bash) or use `python-dotenv` (Python) — naked subshells will not inherit them.

---

## 8. References

- [ADR-0060](../../.architecture/decisions/ADR-0060-commit0-greenfield-benchmark.md) — governing ADR
- [ADR-0059](../../.architecture/decisions/ADR-0059-realworld-dr-benchmark.md) — sister benchmark for D/R axis
- [ADR-0002](../../.architecture/decisions/ADR-0002-llm-provider-abstraction.md) — short-circuit policy under test
- [commit0 GitHub](https://github.com/commit-0/commit0) · [project site](https://commit-0.github.io/) · [paper (arXiv:2412.01769)](https://arxiv.org/abs/2412.01769)
- [OpenHands/benchmarks runner](https://github.com/OpenHands/benchmarks) (MIT)
- [OpenHands Index leaderboard](https://index.openhands.dev/greenfield) — published baseline numbers
- [HuggingFace dataset](https://huggingface.co/datasets/wentingzhao/commit0_combined)
- Sister protocol: [`benchmarks/realworld/PROTOCOL.md`](../realworld/PROTOCOL.md)
