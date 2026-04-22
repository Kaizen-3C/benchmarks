# ADR-0060: commit0 as the Greenfield-Generation Benchmark

- **Status:** Proposed (amended 2x — see Amendments 1 & 2)
- **Date:** 2026-04-20
- **Deciders:** Project owner
- **Related:** ADR-0001 (Charter), ADR-0002 (High-Confidence Short-Circuit), ADR-0056 (ADR Quality Gate), ADR-0059 (RealWorld Decompose/Recompose Benchmark)

## Context

ADR-0059 selected RealWorld Rails→FastAPI as the primary Decompose/Recompose benchmark — i.e., **rebuild stack A as stack B given a working A**. That covers cross-paradigm translation but leaves a second axis of the Kaizen-delta charter untested: **build a working library from a specification with no source-stack reference**. This is the "spec → code" axis that an ADR-driven workflow is supposed to be best at.

OpenHands's January 2026 [Index](https://openhands.dev/blog/openhands-index) introduced a five-task evaluation matrix and labels this axis "Greenfield development." Their Greenfield slot is powered by **commit0** ([commit-0/commit0](https://github.com/commit-0/commit0), [arXiv:2412.01769](https://arxiv.org/abs/2412.01769)) — 54 real Python libraries that an agent must rebuild from scratch given (1) a specification document, (2) a starter repo with stubs, and (3) the original library's full unit-test suite as the oracle.

Three properties make commit0 a near-perfect fit for Kaizen-delta:

1. **Spec-driven by construction.** Every task hands the agent a 10K–300K-token spec doc plus typed stubs. This is exactly the contract Kaizen-delta's Decomposer is designed to consume — the spec *is* the ADR + interface contract, already separated from the implementation.
2. **Standardized oracle.** Scoring is "fraction of upstream unit tests that pass." Deterministic, dockerized, no judge-LLM noise. Comparable across runs, providers, and to published numbers.
3. **Headroom is real.** Published SOTA: **6.12% on the full set, 29.30% on the lite subset** ([paper §4](https://arxiv.org/html/2412.01769v1)). Any non-trivial improvement is a publishable result; we are not trying to squeeze the last 2% from a saturated benchmark.

No prior Kaizen-delta benchmark exercises long-horizon spec-to-code generation against an external standard. Internal scoring on synthetic specs (the cdaor-benchmarks `paper/` work) cannot be cited externally. commit0 closes that gap.

## Decision

Adopt **commit0** as the primary Greenfield-generation benchmark for Kaizen-delta, complementary to (not replacing) ADR-0059's RealWorld D/R benchmark. Run the **commit0-lite** subset (16 libraries, defined as `SPLIT_LITE` in [`commit0/harness/constants.py`](https://github.com/commit-0/commit0/blob/main/commit0/harness/constants.py)) end-to-end first; promote to the full 54-library suite only if lite shows pass-rate > published SOTA on at least one configuration.

The lite subset: `tinydb, simpy, deprecated, wcwidth, voluptuous, cachetools, imapclient, marshmallow, jinja, cookiecutter, portalocker, parsel, pyjwt, chardet, babel, minitorch`.

## Why commit0 specifically

- **Dataset realism.** Libraries like `tinydb`, `simpy`, `mimesis` are real PyPI packages, not toy CRUD apps. Specs include text + diagrams; tests cover edge cases the spec only implies.
- **Long-horizon match.** OpenHands Index data shows GPT-5.2-Codex "worked twice as long as Claude Opus" on Greenfield and won by a wide margin — i.e., the benchmark rewards multi-step planning, which is what Kaizen-delta's ADR-driven decomposition is for.
- **Existing harness.** [OpenHands/benchmarks/commit0](https://github.com/OpenHands/benchmarks) already has a runner under MIT license. We integrate, we don't reimplement.
- **Reproducibility cheap.** Each library task ships a Dockerfile; scoring is `pytest` exit codes. No bespoke infra.
- **Citable.** OpenReview-published, indexed against GPT-5.2-Codex / Opus / Sonnet baselines on the public OpenHands leaderboard. A reviewer's first question — "did you compare to a standard benchmark?" — is answered by name.

## Why a *separate* ADR from RealWorld

RealWorld and commit0 test different task classes and should be reported separately:

| Axis | Benchmark | What it proves |
|---|---|---|
| Cross-stack translation (D/R) | RealWorld Rails→FastAPI (ADR-0059) | Decomposer can extract a contract from working code; Recomposer can re-emit on a new stack |
| Spec-to-code (Greenfield) | commit0 (this ADR) | Given a contract+stubs+oracle, the system can generate a passing implementation |

A win on one is not a win on the other. Reporting them under one ADR would conflate the claims.

## Scope

**In scope:**
- Adopting commit0 as the corpus
- commit0-lite (7 libs) as the initial pilot; full 54 as a follow-on gate
- Wiring OpenHands's runner into `benchmarks/commit0/`
- Defining the per-library Kaizen-delta workflow (spec → ADR extraction → stub fill → test loop)
- Defining baselines (single-shot, Reflexion, OpenHands-published numbers, Kaizen-delta with/without ADR-0002 short-circuit)

**Not in scope (separate ADRs if pursued):**
- SWE-Bench Verified / Multimodal — these test "fix existing code" and are an entirely different axis (ADR-0061 candidate)
- GAIA — agentic reasoning, not software generation
- Custom synthetic-spec benchmarks beyond the cdaor-benchmarks corpus

## Consequences

### Positive

- **Externally citable Greenfield number.** OpenHands Index and the commit0 leaderboard provide ready-made comparison points (GPT-5.2-Codex, Opus, Sonnet). Reviewers can locate Kaizen-delta in a known landscape without taking our word for the metric.
- **Spec-driven workflow finally validated end-to-end.** Today the Decomposer's output (ADRs, contracts) is only consumed internally. commit0 makes the spec→code path the *whole* path, so a regression in extraction quality shows up directly as a pass-rate drop.
- **Composable with ADR-0002.** The high-confidence short-circuit was designed for cases where a stub + tests + spec uniquely determine the implementation. commit0 is that case at scale; expected short-circuit firing rate is substantially higher than on RealWorld.
- **Cheap to start.** commit0-lite is 16 libraries; a first end-to-end pass on the smallest 3–5 is a half-day spike, not a 1–2 week iteration loop like RealWorld.

### Negative

- **Python-only.** commit0 does not exercise multi-language Recomposition. We do not claim it does; that is RealWorld's job and SWE-Bench Multi's.
- **Spec-quality is fixed.** commit0 ships specs as-given; it does not measure how well Kaizen-delta would handle a *bad* spec. This is acceptable as a Greenfield benchmark but is not a substitute for spec-quality testing.
- **Library scope is narrow per task.** commit0 libraries are mostly small/medium (avg ~2k LOC). It does not test repository-scale planning the way SWE-Bench-Verified does on multi-thousand-file projects.
- **Failure to beat published SOTA on lite is informative but unflattering.** A commit0-lite pass rate at-or-below 29.3% would suggest Kaizen-delta's ADR overhead does not buy generation quality on this task class. We commit in advance to publishing whatever we measure.

### Neutral

- **Provider-agnostic.** Same harness runs Sonnet, Opus, GPT-5.x, qwen3-coder. Lets us factor out model effects from architecture effects when comparing to OpenHands Index numbers.
- **Composes cleanly with ADR-0059.** Same runner pattern (Docker + test-suite oracle + per-run audit). Most of the `benchmarks/realworld/` infrastructure is reusable.

## Evaluation Protocol Summary

Full detail to live in `benchmarks/commit0/PROTOCOL.md` (to be drafted alongside this ADR). High-level:

1. **Input:** for each commit0 library — `spec.md`, starter repo with stubs, hidden test suite, `target.yaml` (Python version, test command, time budget)
2. **Decompose step:** run Kaizen-delta Decomposer on `spec.md` to produce `adrs/*.md` + `contracts/*.yaml` + `oracles/tests.jsonl`. (The hidden tests are the *real* oracle; the extracted oracles measure how well Decomposer recovers the test contract from spec alone.)
3. **Recompose step:** Recomposer fills the stubs against the extracted ADRs/contracts; ADR-0002 short-circuit fires where stubs+contracts are sufficient.
4. **Score step:** dockerized `pytest` against the hidden tests; record pass rate per library and aggregate.
5. **Report:** primary pass rate (aggregate + per-library), short-circuit firing rate, time/cost per library, comparison to baselines and to OpenHands Index published numbers.

### Baselines to compare against

1. **OpenHands Index published numbers** (Opus, GPT-5.2-Codex, Sonnet) — read off the leaderboard, no rerun needed.
2. **Single-shot Sonnet 4.6**: feed spec + stubs in one call, no decomposition. Establishes "what does the spec alone get you?"
3. **Reflexion-on-Sonnet**: the §5.8a baseline from the cdaor-benchmarks paper — run Reflexion's reflect-on-failure loop directly on stubs+tests with no ADR extraction.
4. **Kaizen-delta, ADR-0002 off**: measures marginal value of the short-circuit on Greenfield (vs. ADR-0059 where it measures marginal value on D/R).
5. **Kaizen-delta, ADR-0002 on**: headline configuration.

## Scoring Rubric

| Metric | How measured |
|---|---|
| **Primary: Pass rate** | % of hidden unit tests passing, summed across libraries |
| Per-library pass rate | Same, broken down per library (so partial wins are visible) |
| Library completion rate | % of libraries where the generated code at least imports + collects tests |
| Short-circuit firing rate | % of stub fills emitted via ADR-0002 vs. the LLM generator |
| Cost per library | $USD spend, broken out for Decompose vs. Recompose vs. retry |
| Time per library | wall-clock, same breakdown |
| Spec-recovery score | similarity between Decomposer-extracted oracles and the hidden test suite (diagnostic only — informs Decomposer quality) |

A paper-defensible result on **commit0-lite** is **pass-rate strictly greater than the measured single-shot Sonnet 4.6 baseline (B2 = 50.75%)**, on at least one Kaizen-delta configuration, with cost ≤ 3× B2's $7.31 (~$22). Promotion to the full 54-library run requires this gate.

(Original gate of 29.30% — the published full-commit0 SOTA — was set before B2 was measured. B2 turned out to be substantially higher than published SOTA on the lite subset; see Amendment 1.)

## Reproducibility Requirements

- Pinned commit0 git SHA + dataset hash
- Pinned OpenHands/benchmarks runner SHA
- Per-library Docker images with pinned base tags
- Per-run audit: every LLM call logged with prompt + response + model version (same scheme as ADR-0059)
- `scripts/run_commit0_lite.sh` and `scripts/run_commit0_full.sh`
- All raw `pytest` output preserved per library, not just summary counts

## Alternatives Considered

### Build a custom spec-driven benchmark from scratch
**Pros:** Tailored exactly to Kaizen-delta's spec format; no impedance mismatch. **Cons:** Not citable; reviewers will discount any number from a self-graded benchmark; ignores 12+ months of community work on commit0; defeats the point of having an external standard.

### Adopt SWE-Bench Verified instead
**Pros:** Larger, more recognized, multi-file. **Cons:** Tests "fix this bug given a failing test," not "build this from spec." Wrong axis for an ADR-driven workflow's primary claim. Belongs in a future ADR-0061, not as a substitute here.

### Adopt GAIA
**Pros:** General-purpose, in OpenHands Index. **Cons:** Tests agentic reasoning + tool use, not software generation. Off-charter for Kaizen-delta.

### Use OpenHands Index runner directly without writing our own integration
**Pros:** Zero integration cost. **Cons:** Couples our scoring to their harness lifecycle; they revise the matrix periodically. Owning the wiring keeps us in control of what gets logged for the audit trail.

## Pragmatic Enforcer Analysis

**Reviewer:** Pragmatic Enforcer
**Mode:** Balanced
**Necessity Assessment:** 8/10 — the spec-to-code axis is currently untested externally, and ADR-0059 explicitly does not cover it.
**Complexity Assessment:** 3/10 — adopting an existing dockerized benchmark with an existing runner is among the cheapest ways to get a citable number.
**Recommendation:** Approve, with the lite-subset gate as written. Do not run the full 54-library suite until lite clears the SOTA threshold; that gate prevents burning compute on a configuration that isn't winning.
**Pragmatic Score:** Necessity 8/10, Complexity 3/10, Ratio 2.7

**Rationale:** Low marginal cost (existing harness, existing dataset, existing leaderboard) for a high-value missing capability (citable Greenfield metric). The lite-first staging is the simplification; without it, this would score lower on complexity.

## Validation

**Acceptance Criteria:**
- [x] `benchmarks/commit0/` exists with `PROTOCOL.md`, runner script, and Docker orchestration *(2026-04-20)*
- [x] Single-shot Sonnet baseline is reproducibly run on the same lite subset for comparison *(B2 measured 2026-04-20: 50.75% — see Amendment 1)*
- [ ] commit0-lite runs end-to-end on a Kaizen-delta configuration and produces a `results.json` with per-library pass rates
- [ ] Audit log captures every LLM call for one full lite run
- [ ] At least one Kaizen-delta configuration **exceeds the measured B2 baseline of 50.75% pass rate** on commit0-lite **OR** a written post-mortem explains why and what changes before retrying

**Testing Approach:** First spike runs a single commit0-lite library (smallest spec — likely `wcwidth` or `deprecated`) to validate the harness wiring; full lite (16 libs) once that passes; full 54-library suite gated on lite SOTA.

## Next Steps

1. Create `benchmarks/commit0/` with `PROTOCOL.md` (companion to this ADR).
2. Pin commit0 dataset SHA and OpenHands/benchmarks runner SHA.
3. Spike: run one commit0-lite library through the OpenHands runner with a single-shot Sonnet baseline; confirm pass-rate matches published number within ±5pp. (Sanity check on the harness, not on Kaizen-delta yet.)
4. Wire Decomposer + Recomposer into the runner as the agent-under-test.
5. First end-to-end commit0-lite run on Kaizen-delta. Probable first-result range: 15–35% pass rate; iterate.
6. Gate decision: promote to commit0-full only on SOTA-exceeding lite result.

## References

- [OpenHands Index blog (Jan 2026)](https://openhands.dev/blog/openhands-index)
- [commit0 GitHub](https://github.com/commit-0/commit0)
- [commit0 project site](https://commit-0.github.io/)
- [commit0 paper (arXiv:2412.01769)](https://arxiv.org/abs/2412.01769)
- [OpenHands/benchmarks runner (MIT)](https://github.com/OpenHands/benchmarks)
- ADR-0001 (Charter) — spec-to-code is in scope for Kaizen-delta
- ADR-0002 (High-Confidence Short-Circuit) — expected to fire heavily on commit0
- ADR-0059 (RealWorld D/R Benchmark) — complementary axis; this ADR follows the same structure deliberately
- cdaor-benchmarks `paper/PUBLISH_POTENTIAL_ASSESSMENT.md` — establishes that we need an external Greenfield benchmark, not just internal synthetic specs

---

## Decisions & Sign-Off
**Decision Date:** 2026-04-20
**Decided By:** Project owner
**Status:** Proposed (amended once)

---

## Amendment 1 — B2 baseline measured; gate raised to 50.75%
**Date:** 2026-04-20
**Trigger:** Phase 0 B2 run completed.

### What changed

The original ADR set the lite-gate at "strictly greater than published SOTA of 29.30%". That number was the full-commit0 (54-lib) Sonnet aggregate from the OpenHands Index leaderboard. Before running any Kaizen-delta experiments, we measured B2 (single-shot Sonnet 4.6) on commit0-lite directly. Result:

| Metric | Value |
|---|---|
| Pass rate (attempted) | **50.75%** (1,019 / 2,008) |
| Libraries | 16 |
| Total tests passed | 1,019 |
| Total tests failed | 891 |
| Total tests errored | 98 |
| Total tests skipped | 12 |
| Input tokens | 1,385,608 |
| Output tokens | 209,924 |
| Wall clock | 46 min |
| API cost | $7.31 |

Full per-library breakdown in [`benchmarks/commit0/results/aggregate_lite_single_shot_sonnet.json`](../../benchmarks/commit0/results/aggregate_lite_single_shot_sonnet.json); each per-lib JSON records input/output tokens, elapsed seconds, files written, and the canonical pytest summary line.

### Why the old gate was wrong

The published 29.30% was measured on the *full* 54-library set, where many hard libraries (pytest, networkx, statsmodels, etc.) drag the aggregate down. The 16-library **lite** subset is biased toward smaller, mostly-logic libraries where single-shot Sonnet can near-solve several outright (`cachetools` 100%, `tinydb` 88%, `simpy` 83%). Using the full-set number as the lite gate makes the gate trivially passable by B2 alone, with no architectural win required.

### New gate

A paper-defensible Kaizen-delta result on commit0-lite must satisfy all of:

1. **Pass rate > 50.75%** (strict) on at least one Kaizen-delta configuration
2. Cost ≤ 3× B2 (i.e., ≤ $22 per lite run)
3. Audit log captures every LLM call

### Where the headroom is

The 6 libraries where B2 scored 0–1 passing tests are the concentration of remaining probability mass:

| Library | B2 pass | B2 fail | B2 err | Failure mode |
|---|---:|---:|---:|---|
| chardet | 1 | 375 | 0 | Sonnet emitted code that imports but fails ~all tests |
| voluptuous | 0 | 0 | 2 | Generated code raises at import |
| babel | 0 | 0 | 22 | Collection errors |
| minitorch | 0 | 0 | 10 | Collection errors (multi-module tensor lib, too complex) |
| jinja | 0 | 0 | 0 | Python `SyntaxError` in generated `nodes.py` — no collection |
| marshmallow | 0 | 0 | 0 | `AttributeError: module 'marshmallow.utils' has no attribute 'timestamp'` — missing helper function |

These are exactly the libraries where decomposition-before-generation (vs. one-shot) is architecturally expected to help. Kaizen-delta's value-add on lite is dominated by how much it improves these 6; the other 10 are already at 30–100% under B2 with limited headroom for Kaizen to differentiate.

### Scope of amendment

Changes only the numeric gate (29.30 → 50.75) and the acceptance criterion. All other design decisions (adopt commit0, complement ADR-0059, lite-first staging, baseline matrix B0–B5) stand.

**Amendment decided by:** Project owner, 2026-04-20.

---

## Amendment 2 — Full baseline grid measured; gate refined; B6 reproduction caveats
**Date:** 2026-04-21
**Trigger:** Full baseline campaign completed; AAR written. See [`benchmarks/commit0/AAR_2026-04-21.md`](../../benchmarks/commit0/AAR_2026-04-21.md).

### What changed

The full baseline grid is now measured across two providers (Sonnet 4.6, GPT-5.4) for B2 single-shot and B3 Reflexion, plus a partial B6 OpenHands V1 reproduction. This data refines the gate set in Amendment 1 and adds three new findings the original ADR didn't anticipate.

### Measured baselines (2026-04-21)

| Baseline | Aggregate | Cost | $/test | Notes |
|---|---:|---:|---:|---|
| B2 Sonnet 4.6 | 51% | $7.31 | $0.0072 | best aggregate |
| B2 GPT-5.4 | 40% | $2.88 | **$0.0038** | best $/test |
| B3 Sonnet (Reflexion) | 32% | $10.89 | $0.0219 | -19 pp vs B2 — Reflexion regresses Sonnet |
| B3 GPT-5.4 (Reflexion) | 45% | $4.12 | $0.0052 | +5 pp vs B2 — Reflexion helps GPT |
| B6 Sonnet (3/16 partial) | 2/3 resolved | $84.70 | $0.1409 | bandwidth + caching bottlenecks |
| B6 GPT-5.4 (3/16 same set) | 2/3 resolved | $11.66 | n/a | identical instance outcomes; 7× cheaper |

### Three new findings

**Finding 1 — Reflexion is model-dependent.** Same iteration loop, same benchmark: regresses Sonnet 4.6 by −19 pp aggregate, improves GPT-5.4 by +5 pp. Any future paper citing Reflexion results on this kind of task class must name the model. The cdaor-benchmarks §5.8a "Reflexion universally beats CD-AOR" claim is empirically refuted on multi-file Greenfield.

**Finding 2 — Architecture dominates model at the agent-loop level.** B6 Sonnet and B6 GPT-5.4 on the same 3 libs got *identical per-instance outcomes* — `tinydb` and `simpy` resolved, `pyjwt` unresolved, both at 601/603 tests passed. Model swap changed cost (7×) and time (2.5×) but not which problems were solvable. The OpenHands V1 agent's structure determines outcome more than the underlying LLM does at the 100-iteration scale.

**Finding 3 — Five "floor libs" fail in every baseline tested.** `chardet, marshmallow, babel, jinja, minitorch` produce 0% pass rate across all four B2/B3 configurations regardless of model. These are the **real signal-test for Kaizen-delta**: if decomposition cannot move ≥1 of these off the floor, decomposition's value claim on commit0 is hard to defend.

### B6 reproduction caveats

We could NOT cleanly reproduce OpenHands' published 7/16 number for Sonnet 4.6:

- **v1.11.5 SDK pin attempt failed** — Pydantic validator bug in `DockerDevWorkspace` rejects valid input. v1.11.5 was tested by OpenHands against their hosted RUNTIME_API_KEY service; the local-Docker code path was never exercised. We pivoted to latest SDK (v1.16.1).
- **`pip install commit0` saturated PyPI bandwidth** at `--num-workers 16` (default) — 13 of 16 instances timed out. Reducing to `--num-workers 3` or 4 fixes this. Default for local-Docker should be ≤4.
- **Per-instance cost was 15× their published $1.88/lib** — counterfactual cache analysis shows ~76% of the gap closes with prompt caching applied, which their internal litellm proxy does and our local agent server doesn't. Without their hosted runtime, full cost parity isn't reproducible.

### Refined gate

The Amendment 1 gate ("strictly >50.75% B2-Sonnet aggregate") stands as the **quality bar** but is supplemented by:

1. **Quality bar (unchanged):** beat 50.75% aggregate on commit0-lite OR write a post-mortem
2. **Cost bar (new):** $/test ≤ B2-GPT-5.4's $0.0038 (the cheapest baseline). Beating quality but at higher $/test means Kaizen-delta is buying quality with money, not architecture — weaker story.
3. **Floor-lib bar (new):** at least 1 of the 5 floor libs (`chardet, marshmallow, babel, jinja, minitorch`) must achieve > 0 instance pass under Kaizen-delta. These are where decomposition-from-spec should help most; if it doesn't, the "architecture matters" claim has nowhere to land.

A Kaizen-delta result that hits the quality bar but misses both supplementary bars is publishable but weakens the Kaizen-delta thesis. Hitting all three is the strong outcome.

### Caching is not optional

The B6 cost analysis makes prompt caching a Kaizen-delta architectural requirement, not a nice-to-have:

- **Anthropic:** `cache_control: {"type": "ephemeral"}` on the spec block + accumulated context.
- **OpenAI:** auto-cache via stable prompt prefixes; structure prompts so the spec block is at message[0].

Implemented in `benchmarks/commit0/baselines/_llm.py` and used by `kaizen_delta.py`.

### B6 GPT-5.4 partial finding

We ran B6-GPT-5.4 only on the 3 libs that completed for B6-Sonnet (`tinydb, pyjwt, simpy`) — defensive against the same bandwidth bottleneck. Results were identical at instance level (2 resolved, same one unresolved) at 7× lower cost. We did NOT run a full 16-lib B6-GPT-5.4. Defensible per-paper because:

> "On the libraries where workspace bootstrap succeeded for both models, B6-GPT-5.4 matched B6-Sonnet's instance outcomes at one-seventh the cost. Larger-scale B6 reproduction was bandwidth-limited by parallel `pip install commit0` saturating outbound network — a known reproducibility constraint of the local-Docker variant of OpenHands' harness, separate from agent or model behavior."

### Process improvements (from AAR)

Six action items in the AAR translate to repo-level changes:

1. ✅ Cost-monitor smoke test added: `benchmarks/commit0/baselines/openhands_latest/test_cost_monitor.py` — runs one tiny instance and asserts the cap parser reads a non-zero cost from the field name we expect (prevents the $85-incident class of bugs).
2. ✅ Provider abstraction: `benchmarks/commit0/baselines/_llm.py` — `LLMClient(provider, model)` + `cost(provider, usage)`. `kaizen_delta.py` uses it; future scripts should too.
3. ⏳ ADR-0060 Amendment 2 (this document).
4. ⏳ Kaizen-delta runner: `benchmarks/commit0/baselines/kaizen_delta.py` — per-file decompose → recompose with module-level pytest grounding (the signal Reflexion lacked).
5. (deferred) Upstream PR for the 3 commit0 Windows bugs documented in PROTOCOL.md §6.1.
6. (deferred) Refactor existing `single_shot_*.py` / `reflexion_*.py` scripts to use `_llm.py`. Data already collected; cleanup-only.

### Scope of amendment

Adds the cost bar and floor-lib bar to the gate. Refines the supplementary findings. Does NOT change the original adoption decision (commit0 stays as the Greenfield benchmark) or the lite-first staging.

**Amendment 2 decided by:** Project owner, 2026-04-21.
