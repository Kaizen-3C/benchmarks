# ADR-0059: RealWorld Rails→FastAPI as the Primary Decompose/Recompose Benchmark

- **Status:** Proposed
- **Date:** 2026-04-19
- **Deciders:** Project owner
- **Related:** ADR-0002 (High-Confidence Short-Circuit), cdaor-benchmarks paper §§5.7/5.8/5.8a

## Context

The session of 2026-04-19 (documented in `cdaor-benchmarks/paper/PUBLISH_POTENTIAL_ASSESSMENT.md` and `CROSS_PROVIDER_AGGREGATION_20260419.md`) established that on HumanEval and MBPP:

- CD-AOR does not produce aggregate pass-rate lift over single-shot Claude Sonnet 4.6 once prompting is matched (§5.7: −1.17 pp on HE; −13.6 pp on MBPP).
- A minimal Reflexion-style self-reflection loop on the same Sonnet 4.6 model beats CD-AOR on both benchmarks (§5.8a: 100.00% HE, 98.83% MBPP).

This refutes the paper's original pass-rate-superiority claim on standard function-completion benchmarks and pushes CD-AOR's remaining architectural claim onto harder task classes. One such class — capability recovery on oracle-readable decoy-distractor tasks — is supported by TerminalBench-2 data (prior session's `TERMINALBENCH_BYPASS_20260418.md`). The other — **cross-stack decomposition and recomposition** — was the Kaizen-delta charter claim (ADR-0001) and has been entirely untested end-to-end.

No established benchmark exists for "take a working application in source stack A, produce an equivalent in target stack B, pass the same test suite." We need to either adopt an existing corpus or build one. This ADR selects the adoption path.

## Decision

Adopt **RealWorld** ([gothinkster/realworld](https://github.com/gothinkster/realworld)) as the primary Decompose/Recompose benchmark for Kaizen-delta, with the Rails → FastAPI stack pair as the initial concrete pilot.

RealWorld is "the mother of all demo apps": a complete Medium.com clone with authentication, article CRUD, comments, user profiles, favorites, tagging, and following. It has:

1. **A canonical OpenAPI specification** (`realworld/api/openapi.yml`) — a fixed public contract that every implementation must satisfy. This IS the architectural contract for Decompose/Recompose.
2. **A canonical test suite** (`realworld/api/Conduit.postman_collection.json`) — ~90 API-level integration tests that run against any live implementation. The oracle is identical across stacks.
3. **~100 peer-implementations** across ~50 frontend frameworks × ~50 backend stacks, each independently built to satisfy the same spec + tests. This provides multiple reference points per stack.
4. **Docker-compose setup per implementation** — every impl ships a runnable stack. Reproducibility is built in.
5. **Wide community recognition** — reviewers will know the corpus. No benchmark-familiarity cost.

## Why Rails → FastAPI as the initial pair

- **Rails source advantage:** The reference Rails implementation ([gothinkster/rails-realworld-example-app](https://github.com/gothinkster/rails-realworld-example-app)) is well-structured, follows conventions, and has visible architecture (ActiveRecord models, Rails controllers, concerns).
- **FastAPI target advantage:** FastAPI + SQLAlchemy async is a well-documented target stack with a peer implementation ([nsidnev/fastapi-realworld-example-app](https://github.com/nsidnev/fastapi-realworld-example-app)) that gives us a human-reference upper bound to compare against.
- **Cross-paradigm:** Rails is convention-over-configuration + synchronous Ruby; FastAPI is explicit-configuration + async Python. The translation tests whether CD-AOR can bridge a real paradigm gap, not just syntactic differences.
- **Documented community migrations:** several Rails → Python (Flask or FastAPI) migration blog posts exist in the industry, providing external pattern references.

## Scope

**In scope for this ADR:**
- Adopting RealWorld as the corpus
- Selecting Rails → FastAPI as the initial pair
- Defining the evaluation protocol (see companion doc `benchmarks/realworld/PROTOCOL.md`)
- Defining the scoring rubric
- Defining the baselines to compare against

**Not in scope (separate ADRs if pursued):**
- Other stack pairs (Rails → Go-Fiber, Django → Phoenix, etc.) — ADR-0060 candidate
- Frontend recomposition — ADR-0061 candidate
- Alternative benchmarks (microservices-demo, TodoMVC, etc.) — separate pilots if RealWorld doesn't land

## Consequences

### Positive

- **Defensible benchmark choice.** RealWorld is community-recognized and already has peer implementations; reviewers cannot dismiss it as cherry-picked.
- **Paper alignment.** The paper's revised §6.1 claims "CD-AOR's value is on harder tasks" — RealWorld is exactly such a task (cross-stack translation of ~2000 LOC with integration tests).
- **Head-to-head competitor comparison.** Reflexion cannot natively do cross-stack translation (the reflection loop needs executable tests in the target stack, which is what we're generating). Adapting Reflexion to this benchmark is itself evidence that CD-AOR's architecture was designed for this class of problem.
- **Path to a second benchmark.** Once Rails → FastAPI is running, extending to Rails → Go-Fiber or Django → FastAPI adds data points at low marginal cost.

### Negative

- **Large first-run cost.** A full RealWorld translation is ~2000 LOC with tests; getting to ≥80% oracle pass rate likely requires multiple CD-AOR steps per module and significant prompt engineering. Budget an experiment at ~$100-300, 1-2 weeks of iteration.
- **Failure is costly.** If CD-AOR cannot produce a RealWorld implementation that passes ≥50% of the Postman tests on the first experiment, the paper has no headline result and needs to fall back to case-study methodology.
- **Test infrastructure complexity.** The Postman collection requires a running server + database; that's more infrastructure than HumanEval/MBPP's subprocess-based scoring.
- **Not representative of all D/R tasks.** RealWorld is a specific genre (REST API + SQL + JWT); success here does not prove D/R works on e.g., a CLI tool, a distributed system, or a compiler.

### Neutral

- **Orthogonal to model choice.** The benchmark is independent of which LLM/provider powers CD-AOR. Sonnet, Opus, GPT-5.4, qwen3-coder can all be tested on the same corpus.

## Evaluation Protocol Summary

Full detail lives in `benchmarks/realworld/PROTOCOL.md`. High-level:

1. **Input:** Rails RealWorld implementation (checked-in reference, specific git SHA)
2. **Decompose step:** produce `spec/` directory containing:
   - `graph.json` (decomposition graph)
   - `adrs/*.md` (extracted architectural decisions)
   - `contracts/*.yaml` (per-module interface contracts)
   - `oracles/tests.jsonl` (the Postman collection translated to per-endpoint assertions)
3. **Recompose step:** given `spec/` + `target.yaml` (FastAPI + SQLAlchemy async + uv packaging) → produce `out/` directory with runnable FastAPI app
4. **Score step:** `docker-compose up` the generated app; run the Postman collection against it; record pass rate per endpoint category
5. **Report:** oracle pass rate (aggregate + per-category), per-module generation success, baseline comparisons

### Baselines to compare against

1. **Human-reference upper bound:** [nsidnev/fastapi-realworld-example-app](https://github.com/nsidnev/fastapi-realworld-example-app) — the community's hand-written FastAPI implementation. Establishes "what's achievable."
2. **Single-shot Claude:** feed the entire Rails codebase into a single Sonnet call asking for the FastAPI equivalent. Likely fails on context limits; reports that failure honestly.
3. **Reflexion adapted:** Reflexion needs executable tests in the target stack to reflect. We'd either (a) generate a minimal FastAPI scaffold first so Reflexion has something to iterate on, or (b) report that Reflexion-as-published cannot do this task.
4. **CD-AOR without short-circuit** (ADR-0002 off): measures the marginal value of the test-aware bypass on D/R.
5. **CD-AOR with short-circuit** (ADR-0002 on): the headline configuration.

## Scoring Rubric

| Metric | How measured |
|---|---|
| **Primary: Oracle pass rate** | % of Postman collection requests that produce the expected HTTP status + response shape |
| Per-category pass rate | Same, broken down by endpoint category (auth, articles, comments, profiles, tags, favorites) |
| Module completion rate | % of decomposition-graph modules that produce valid output code (compiles + imports without error) |
| Time-to-first-pass | wall-clock from `decompose --out spec/` to first Postman test passing |
| Cost | $USD spend on LLM APIs |
| Short-circuit firing rate | % of artifacts emitted via ADR-0002 short-circuit vs. the LLM generator |

A paper-defensible result is **≥80% primary pass rate** (73 of 90 Postman tests), matching or exceeding the ratio achievable by a heavily-prompted single-shot baseline.

## Reproducibility Requirements

- Pinned git SHAs for the Rails source implementation and the FastAPI reference
- Docker images for both stacks with pinned tags
- Exact Postman collection version (path + SHA)
- Runner script: `scripts/run_realworld_rails_to_fastapi.sh`
- Per-run audit: every LLM call logged with prompt + response + model version

## Next Steps

1. Create `benchmarks/realworld/` directory with the protocol doc, scoring scripts, and Docker orchestration. (Draft lives in `benchmarks/realworld/PROTOCOL.md` alongside this ADR.)
2. Pin specific git SHAs for the Rails source and FastAPI reference.
3. Spike: run the Rails implementation locally, run the Postman collection, confirm expected pass rate on reference (should be 100%).
4. Spike: run the human-written FastAPI reference, run the Postman collection, confirm a ≥95% pass rate (small diffs in error message formatting are expected).
5. Design the Decomposer's ADR-extraction rules for Rails (ActiveRecord → data model; Rails routes → API spec; concerns → shared middleware; etc.)
6. First CD-AOR run end-to-end. Probable first-result range: 20-50% pass rate; iterate.

## References

- [RealWorld GitHub](https://github.com/gothinkster/realworld)
- [RealWorld OpenAPI spec](https://github.com/gothinkster/realworld/blob/main/api/openapi.yml)
- [RealWorld Postman collection](https://github.com/gothinkster/realworld/blob/main/api/Conduit.postman_collection.json)
- [Rails reference](https://github.com/gothinkster/rails-realworld-example-app)
- [FastAPI reference](https://github.com/nsidnev/fastapi-realworld-example-app)
- Kaizen-delta ADR-0001 (Charter) — scope for D/R work
- Kaizen-delta ADR-0002 (High-Confidence Short-Circuit) — the primary architecture being tested
- cdaor-benchmarks `paper/PUBLISH_POTENTIAL_ASSESSMENT.md` — the gap this benchmark closes
