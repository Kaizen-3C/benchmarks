# Round-Trip (Code→ADR→Code) Benchmark — Implementation Plan

**Governed by:** [ADR-0063](../../.architecture/decisions/ADR-0063-round-trip-fidelity-benchmark.md)
**Status:** Phase 1 (Scaffolding) complete 2026-04-21. Phase 2 next.
**Next session's job:** Phase 2 — implement the real Decompose prompt + Q1 test_parity metric. Smallest valuable next step (one prompt + one metric).
**Estimated to first publishable result:** 3–4 weeks of focused work.

## What this benchmark is for

commit0 (ADR-0060) tests **Recompose** alone. RealWorld (ADR-0059) tests **cross-stack translation**. Round-trip is the only benchmark that tests **the ADR intermediate format itself** — it answers: *"if our Decomposer reads working code, does it produce ADRs faithful enough that a fresh Recompose rebuilds functionally-equivalent code?"*

The translation analogy:

> ADR-0003 says *"the cache evicts least-recently-used entries"*.
> Original: `LRUCache(max_size=128)`.
> Recomposed: `OrderedDict.popitem(last=False)` with no size cap.
> **Not a true EN→FR translation** — the eviction policy was captured, the size constraint wasn't.

The campaign's job is to find every "not a true EN→FR" gap and ship tools that detect them early.

## Phases (matches ADR-0063 §Implementation roadmap)

### Phase 1 — Scaffolding (COMPLETE — 2026-04-21)
- [x] Directory layout under `benchmarks/round_trip/`
- [x] Stubs for the four metrics (Q1–Q4) and five gates
- [x] `decompose_from_reference.py` entry point (phase-1 stub: writes one placeholder ADR; no LLM calls)
- [x] `recompose_from_adrs.py` entry point (phase-1 stub: writes one placeholder `__init__.py`; no LLM calls)
- [x] `run_one.py` orchestrator — 5-line progress log, schema-matching result JSON
- [x] `remediation.py` stub
- [x] `PROTOCOL.md`, `README.md`
- [x] Pilot (wcwidth) round-tripped end-to-end with placeholder data
- **Delivered:** `python benchmarks/round_trip/run_one.py wcwidth` exits 0, writes `results/wcwidth_round_trip.json` matching the documented schema, costs $0 (zero LLM calls).
- **Actual time:** 1 session. **Actual cost:** $0 (vs. $2 budget — no Decompose ran, that's phase 2).

### Phase 2 — Real Decompose prompt + Q1 test_parity (NEXT SESSION)

Smallest-valuable-next-step per SESSION_PROMPT.md: one real prompt + one real metric, end-to-end on wcwidth, before branching further.

- Replace the phase-1 stub in `decompose_from_reference.py` with a real LLM call that walks the wcwidth source tree and emits actual ADRs/contracts/oracles under `spec/wcwidth/`. Use `_llm.LLMClient` with ephemeral caching on the source-tree block.
- Replace the phase-1 stub in `recompose_from_adrs.py` with a real LLM call that reads ONLY `spec/wcwidth/` (no source peeking) and emits a source tree to `recomposed/wcwidth/`.
- Implement `metrics/q1_test_parity.py` for real: run the canonical pytest suite against `recomposed_dir` (via commit0 or local pytest) and report passed/total.
- **Gate to pass:** wcwidth `q1_test_parity.value >= 0.9`. Budget: ~$3.
- Q2–Q4 follow in a subsequent session (per the table below).

### Phase 2b — Remaining metrics (Q2–Q4)
| Metric | What it measures | How to compute |
|---|---|---|
| **Q1 test parity** | % of canonical tests passing on recomposed code | run pytest, count passed/total |
| **Q2 behavioral parity** | (input, output) equivalence on a curated set | execute matched calls on both impls, compare returns |
| **Q3 structural parity** | AST/module-level diff size | `ast.parse` both, walk in parallel, count node-level differences |
| **Q4 ADR coverage / info loss** | % public symbols mentioned in ≥1 ADR; lines not derivable | static analysis of original + ADR text grep |

**Deliverable:** all four metrics computed for wcwidth pilot, persisted to `results/<lib>_round_trip.json`.
**Estimated time:** 2 working days.

### Phase 3 — The five gates + remediation engine
| Gate | Detects | Output |
|---|---|---|
| Coverage | Public symbols missing from any ADR/contract | List of missing symbols + suggested ADR section |
| Specificity | Vague ADRs ("we use a cache" — no params) | Per-ADR concreteness score + amendment suggestions |
| Consistency | Dangling cross-refs in contracts | List of broken references |
| Test-oracle alignment | Canonical tests without analog in `oracles/` | List of unaligned tests + suggested oracle |
| Implementation-leak audit | Code-shaped content in ADRs (cheating) | List of leaked snippets + refactor suggestion |

Each gate runs between Decompose and Recompose. Failed gates emit a structured "this WILL diverge" report.
**Deliverable:** all five gates + JSON-output remediation per failure type, validated against ≥1 known-failing canonical example each.
**Estimated time:** 1 week.

### Phase 4 — Corpus A run (16 commit0-lite libs)
Run the full pipeline on all 16 lite libs starting from each lib's `git checkout reference_commit`.
**Deliverable:** results/Q1–Q4 for all 16 libs + aggregate fidelity score + per-gate failure histogram.
**Estimated cost:** ~$30 with caching, ~$300 without. **Wall:** ~1 day.

### Phase 5 — Curated Corpus B (10 PyPI libs)
Pick small/medium PyPI libs with rich docs (`attrs`, `click`, `httpx` subset, `pydantic` subset). Author the harness adapter (test runner config) per lib.
**Deliverable:** results for 10 PyPI libs + prose comparison vs commit0.
**Estimated cost:** ~$50–100. **Wall:** ~2 days.

### Phase 6 — Methodology writeup
Public methodology paper / blog post; positions round-trip as a missing benchmark genre alongside HumanEval (single-function), SWE-Bench (bug fix), TerminalBench (agentic tools).
**Deliverable:** `docs/round_trip_methodology.md`, possibly a paper draft.
**Estimated time:** 1 week.

## Repo layout (proposed)

```
benchmarks/round_trip/
├── PLAN.md                          # this file
├── PROTOCOL.md                      # per-run procedure (mirrors commit0/PROTOCOL.md style)
├── SESSION_PROMPT.md                # self-contained prompt to start scaffolding
├── README.md                        # quickstart for reviewers
├── decompose_from_reference.py      # core: walk a working lib → emit spec/<lib>/
├── recompose_from_adrs.py           # core: emit code from spec/<lib>/ (no source peeking)
├── metrics/
│   ├── q1_test_parity.py            # canonical-pytest pass-rate
│   ├── q2_behavioral_parity.py      # (input, output) equivalence
│   ├── q3_structural_parity.py      # AST / module-level diff
│   └── q4_information_loss.py       # ADR coverage + derivability
├── gates/
│   ├── coverage.py                  # public-symbol coverage in ADRs
│   ├── specificity.py               # ADR concreteness score
│   ├── consistency.py               # contract cross-ref validation
│   ├── test_oracle_alignment.py     # canonical-test-to-oracle map
│   └── implementation_leak.py       # code-in-ADRs audit
├── remediation.py                   # gate-failure → suggested-fix mapper
├── run_one.py                       # full pipeline for one lib
├── run_corpus.py                    # sweep wrapper (Corpus A)
└── results/
    ├── <lib>_round_trip.json        # per-lib full result
    └── aggregate_corpus_a.json      # summary
```

## What's already in the repo we can reuse

| Existing | Use for |
|---|---|
| `benchmarks/commit0/baselines/_llm.py` | LLMClient + cost tracking — provider-agnostic, with caching |
| `benchmarks/commit0/baselines/single_shot_sonnet.py` helpers | PDF text extraction (not needed here), file discovery, write_files, run_pytest_via_commit0 |
| `benchmarks/commit0/baselines/kaizen_delta.py` | Per-file regen pattern; `recompose_from_adrs.py` will share its acceptance-rule learnings |
| `~/kaizen-commit0/repos/<lib>/` (WSL) | Already-cloned commit0 reference impls (`git checkout reference_commit` for the source) |
| `commit0` Python package | `commit0 test <lib> tests --backend local` for canonical pytest runs |
| Docker images | Already built per-lib for commit0; reusable verbatim |

**Net new code estimate:** ~800–1200 lines for Phase 1+2+3 across all 12 listed files. No new infrastructure.

## Risks called out in ADR-0063

1. **More work than commit0.** ~3× cost per lib (Decompose + Recompose + diff per round-trip).
2. **Test parity ≠ fidelity.** Same tests passing doesn't mean same code. Q3 (structural) and Q4 (info loss) are necessary supplements but harder to compute.
3. **"Kaizen-delta vs Kaizen-delta" theater.** Need at least one comparison architecture (e.g., Aider's spec extraction, OpenHands' planning step) producing ADRs we then evaluate. Otherwise the benchmark only proves we can grade our own homework.

## Decision points the next session needs to resolve

| Decision | Default if unresolved | Notes |
|---|---|---|
| Decomposer prompt template | "extract ADRs/contracts/oracles from this Python source, no implementation in spec" | Will likely need 2–3 iterations |
| ADR file format | Markdown with YAML frontmatter (matches existing `.architecture/decisions/`) | Reuses our ADR template |
| Contract file format | YAML or JSON? | YAML matches RealWorld; JSON easier for tools |
| Oracle file format | JSONL (one row per (input, expected_output)) | Same as `commit0` flow |
| Recomposer view of ADRs | "you only see ADRs+contracts, not the original code" — strict | Without strictness, the benchmark is rigged |
| What counts as "behavioral parity" | run a curated set of property-based tests; same input → same output | Phase 2 problem |

## Cost ceiling for Phase 1 scaffolding

**$5 hard cap.** The pilot Decompose on wcwidth should cost <$2 (small lib, ~6 source files); Recompose <$2; diff/metrics computation $0 (local). If we breach $5, something's wrong with the prompt or the pipeline.
