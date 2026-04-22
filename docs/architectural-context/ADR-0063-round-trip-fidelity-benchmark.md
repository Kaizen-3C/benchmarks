# ADR-0063: Round-Trip (Code→ADR→Code) Fidelity Benchmark

- **Status:** Proposed
- **Date:** 2026-04-21
- **Deciders:** Project owner
- **Related:** ADR-0001 (Charter), ADR-0023 (Decomposition Engine), ADR-0056 (ADR Quality Gate), ADR-0059 (RealWorld D/R), ADR-0060 (commit0 Greenfield), `benchmarks/commit0/PLAN_2026-04-21.md` §Future Goals

## Context

The commit0 benchmark (ADR-0060) tests **half** of Kaizen-delta's pipeline:

> Spec (human-written) → **Recompose** → code → tests

It validates the Recomposer's ability to follow a specification. It says nothing about the Decomposer's ability to **produce** specifications faithful enough that a downstream Recomposer can rebuild the code.

The RealWorld D/R benchmark (ADR-0059) tests cross-stack translation (Rails→FastAPI), but treats the source code as the input — there's no measurement of whether the Decomposer's intermediate ADRs+contracts are themselves a sufficient representation. If the Recomposer happens to also see the Rails source (or a paraphrase of it), the ADR bottleneck isn't actually being tested.

**The question neither benchmark answers:** when our Decomposer reads a working library and produces ADR(s) + contracts + oracles, are those artifacts a **lossless** representation of the library — or do they leak information about the implementation that wasn't captured?

This matters because:

1. **It's the literal claim Kaizen-delta makes** (ADR-0001 charter). The pipeline is `code ↔ ADR ↔ code`. If the round-trip diverges, the architecture is making promises it can't keep.
2. **Reviewers will ask.** Any paper claiming "decomposition produces an architectural intermediate" will face: "what's the round-trip fidelity?"
3. **Early failure detection is high-value.** If we can flag "this decomposition will produce divergent code" before Recompose runs, we save the user money and time.

## Decision

Adopt a **round-trip fidelity benchmark** as the third pillar of Kaizen-delta evaluation, alongside commit0 (Spec→Code) and RealWorld (Code→Code-on-different-stack).

The benchmark answers four questions per library:

| Q | Metric |
|---|---|
| Q1 | **Test parity** — % of canonical tests that pass against the recomposed code, given the original passed all of them |
| Q2 | **Behavioral parity** — for a curated set of (input, expected output) pairs, % producing the same output across original and recomposed |
| Q3 | **Structural parity** — diff size between original and recomposed (AST nodes, module count, public-API surface) |
| Q4 | **ADR coverage / information loss** — % of public symbols in original that appear in ≥1 ADR or contract; % of code lines derivable from ADRs+contracts |

Plus an **early-detection layer** (gates that run between Decompose and Recompose to flag predictable lossiness) and a **remediation engine** (suggests specific ADR/contract amendments when gates fail).

## Why round-trip-on-existing-libs vs. greenfield-from-spec

| Property | Greenfield from spec | Round-trip on existing lib |
|---|---|---|
| What's being tested | Recompose alone | Decompose + Recompose + intermediate format |
| Reference for "correct" | hidden test suite | original code AND test suite |
| Information-loss detectable | no — we never had the "right answer" beyond tests | yes — original code IS the reference |
| Decomposer claim tested | none | the central claim |
| Failure mode caught | bad code generation | bad spec extraction OR bad code generation |

Both benchmarks are valuable. They test different things. **Round-trip is the more rigorous test of the Kaizen-delta thesis** — which is precisely why the original ADR-0060 commit0 work doesn't substitute for it.

## Corpus

Three concentric corpora, each cheaper than the next:

### Corpus A — commit0 reference implementations (cheap, immediate)

Reuse our existing infrastructure: the **reference impl** (NOT the stub) for each commit0 lib has all the properties we want — well-tested, modular, runnable in Docker, has a canonical test suite. The 16 lite libs already cover small (wcwidth) to medium (jinja, marshmallow). Estimated marginal cost: ~$30 per full pass with caching.

### Corpus B — curated PyPI libs (medium, controlled)

Pick 10–20 small/medium PyPI libs that are well-tested and well-documented. Examples: `attrs`, `requests` subset, `httpx`, `pydantic` (small subset), `click`. These have prose specs (real docs), not just stubs+pytest.

### Corpus C — real-world business code (expensive, eventually)

In-house or partner code with complex domain logic. The hardest case: domain knowledge embedded in the code that no ADR will capture without explicit elicitation.

Start with A. Promote to B after A's methodology is validated. C is for paid/contracted evaluations.

## The early-detection layer (gates)

Between Decompose and Recompose, run automatic gates:

| Gate | What it checks | If it fails |
|---|---|---|
| **Coverage** | Every public symbol in original code appears in ≥1 ADR or contract | List missing symbols. Recompose will likely omit or hallucinate them. |
| **Specificity** | Each ADR has ≥1 concrete decision (numbers, library names, algorithms) — not just "we use a cache" but "LRU, max 128" | List vague ADRs. Recompose has too much freedom; will diverge from original. |
| **Consistency** | Contract cross-references resolve. If Contract A says "use Schema B", Schema B exists. | List dangling refs. Recompose will fail or invent. |
| **Test-oracle alignment** | Every test in the canonical suite has an analog in `oracles/` (extracted from spec) | List unaligned tests. Recompose will pass extracted oracles but fail canonical tests. |
| **Implementation-leak audit** | ADRs don't include code (only decisions). Contracts have signatures, not bodies. | Refactor ADRs. Implementation-in-spec means we're cheating. |

Each gate is binary at first; later quantitative. Failed gates mean "this decomposition WILL diverge in N ways" — and the report names which N.

## The remediation engine

For each gate failure, the engine emits a structured suggestion:

```
Gate: Coverage
Missing: TinyDB.purge_table(), TinyDB.tables()
Suggestion: Add ADR-0007 "Table lifecycle management" covering creation,
            iteration, and removal of named tables. Reference: original
            tinydb/database.py:142-167.
```

```
Gate: Specificity
ADR-0003 "Caching policy" is too vague: says "cache results" without
specifying eviction or size.
Suggestion: Add concrete decisions:
  - eviction strategy: ?  (original uses LRU)
  - max size: ?           (original: 128 entries)
  - TTL: ?                (original: none, manual purge)
```

These become first-class Decomposer tools — the user can run `kaizen decompose --check-fidelity` and get a report before paying for Recompose.

## Scope

**In scope for this ADR:**
- Adopting the round-trip framework as a third evaluation pillar
- Defining the four fidelity metrics (Q1–Q4) and how to compute them
- Specifying the gate set and remediation engine surface
- Selecting Corpus A (commit0 reference impls) as the initial harness

**Not in scope:**
- Implementing the gates (separate engineering ADR after this one)
- Curating Corpus B or C (separate ADR per corpus)
- Cross-language round-trip (different ADR; the ADR format itself may need extension)

## Consequences

### Positive

- **Tests the literal Kaizen-delta claim.** No more "we extract specs from code" without measurable fidelity.
- **Cheap to start.** Corpus A reuses commit0 infra — we already have the reference impls, the test suites, the Docker images.
- **The early-detection layer is a deliverable on its own.** Even without recompose, "kaizen decompose --check-fidelity" is a useful product feature.
- **Differentiates from commit0.** Two benchmarks, two architectural claims, two metrics — clean separation in the eventual paper.

### Negative

- **More work.** Implementing the gates is real engineering — probably 2–3 weeks for v1 across all five gates.
- **Round-trip on a 54-lib corpus is expensive.** Each lib runs Decompose ($X) AND Recompose ($Y) AND test diff ($Z). Budget multiplier vs commit0-only: ~3×.
- **Test parity isn't fidelity.** Code that passes the same tests can still be structurally very different (e.g., O(n²) vs O(n log n) implementations). Q1 is necessary but not sufficient. Q3 (structural) and Q4 (information loss) are harder to compute and more contestable.
- **Risk of becoming "Kaizen-delta vs Kaizen-delta" theater.** If only WE can produce ADRs that round-trip well, the benchmark proves nothing about ADR as a general intermediate. We'd want at least one comparison architecture (e.g., Aider's spec extraction, OpenHands' planning step) producing ADRs that we then evaluate.

### Neutral

- **Methodology generalizes.** The same gates and metrics apply to any Decomposer/Recomposer pair. If a competitor publishes their own decomposition framework, this benchmark can compare them directly.

## Implementation roadmap (sketch)

| Phase | Deliverable | Estimated cost |
|---|---|---|
| 1 | Decompose-from-reference-code wired up for commit0 lib (1 lib pilot) | engineering only, ~3 days |
| 2 | All four metrics (Q1–Q4) computed for the pilot | engineering, ~2 days |
| 3 | All five gates implemented + remediation engine v1 | engineering, ~1 week |
| 4 | Corpus A (16 lite libs) round-trip + report | ~$30 per pass, ~1 day wall |
| 5 | Curated Corpus B (10 PyPI libs) | ~$50–100, ~2 days wall |
| 6 | Public methodology writeup | ~1 week writing |

Total: ~3–4 weeks of focused work to first publishable result, plus ongoing data collection.

## Alternatives considered

### Skip — commit0 + RealWorld are enough
**Pros:** less work, can ship the current campaign sooner.
**Cons:** doesn't test the central Kaizen-delta claim. Reviewers will press on this.

### Use only structural diff (skip semantic round-trip)
**Pros:** much cheaper — no Recompose needed.
**Cons:** structural similarity isn't fidelity. Two implementations of the same spec can diverge structurally and both be correct.

### Crowdsource / use existing benchmarks
**Pros:** less work for us.
**Cons:** no existing benchmark measures decompose+recompose fidelity. We'd be proposing a new methodology in parallel; might as well own it.

## Validation

**Acceptance criteria:**
- [ ] At least one commit0 lib decomposed-from-reference + recomposed end-to-end with all four metrics reported
- [ ] All five gates implemented with at least one canonical "this fails" example per gate
- [ ] Remediation engine produces actionable output for each gate-failure type
- [ ] Methodology doc published in `benchmarks/round_trip/PROTOCOL.md`
- [ ] Corpus A baseline numbers committed to repo

## References

- [`benchmarks/commit0/PLAN_2026-04-21.md`](../../benchmarks/commit0/PLAN_2026-04-21.md) §Future Goals — where this idea originated
- [`benchmarks/commit0/AAR_2026-04-21.md`](../../benchmarks/commit0/AAR_2026-04-21.md) — commit0 campaign post-mortem
- ADR-0001 (Kaizen-delta charter) — the round-trip claim being tested
- ADR-0023 (Decomposition Engine) — the component being evaluated
- ADR-0056 (ADR Quality Gate) — related but different (this gates ADR quality from spec; that gates from anywhere)
- ADR-0059 (RealWorld D/R) — sister benchmark, tests cross-stack translation not round-trip fidelity
- ADR-0060 (commit0 Greenfield) — sister benchmark, tests Recompose only

---

## Decisions & Sign-Off
**Decision Date:** 2026-04-21
**Decided By:** Project owner
**Status:** Proposed
