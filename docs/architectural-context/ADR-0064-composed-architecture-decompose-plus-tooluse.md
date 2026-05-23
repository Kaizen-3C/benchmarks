# ADR-0064: Composed Architecture — Decompose + Tool-Use for Named Architectural Ceilings

- **Status:** Proposed — design sketch only; validating experiment scoped, not run
- **Date:** 2026-05-08
- **Deciders:** Project owner
- **Related:** ADR-0052 (Adaptive Convergence via Thompson Sampling), ADR-0058 (Opportunistic Memory Consolidation), ADR-0063 (Round-Trip Fidelity Benchmark)

## Context

The Phase-1 fingerprinting paper identifies **two named architectural ceilings** on
per-file structured decompose (KD), described in §5.4 of the paper:

1. **Attribute-access invisibility** to import-statement scanners — `obj.method()`
   chains are invisible to AST scanners that only follow `import` statements; the
   decompose stage misses transitive dependencies introduced by attribute access.
2. **Relative-import resolution failure** — KD's per-file scanner does not resolve
   `from .submodule import X` correctly across nested package boundaries.

Both are properties of **text-based scanning generally**, not bugs in any specific
implementation. The fingerprint matrix (§5.2 of the paper) showed the cells in question
were uniformly negative across both providers on KD and on B2/B3, pointing to a
shared architectural ceiling rather than scanner-specific defects.

The paper claims (in §6 and §9) that these ceilings recommend a **composition** with
a tool-using agent — one that can resolve attribute access via runtime introspection
or AST walking, and resolve relative imports via the actual Python import machinery
rather than text parsing. The paper references this ADR in §6 (the composability
proposal) and §9 (future work), citing it in supplementary as the design sketch. This
ADR is that sketch.

## Decision

We will validate a **two-stage composed architecture**:

```
Stage 1 (KD per-file decompose)         — emits candidate library, gated by Q1
   ↓ if Q1 < confidence_threshold
Stage 2 (tool-using agent, bounded)     — given Stage 1 candidate + test failures,
                                          edit-on-failure with import/AST tools
```

**Stage 1** is the existing KD pipeline (`benchmarks/round_trip/recompose_from_adrs.py`),
unchanged. It produces a candidate library and reports Q1 (test parity).

**Stage 2** is a tool-using agent (the Aider/OH/smolagents shape) that receives:
- The Stage 1 candidate (already mostly correct)
- The failing tests (the ground truth)
- A bounded toolkit: AST walker, import resolver, file reader, file editor

Stage 2 runs only on libraries where Stage 1's Q1 is below a confidence threshold —
the gating decision is the entire point of the composition. Libraries Stage 1
already nails (Q1 → 1.0) skip Stage 2 entirely; the cost gap (31×) we measured
between KD and OH is precisely because OH iterates uniformly while KD does not.

The composition addresses all four complementarities surfaced in §6.1:

1. **Test-side visibility** — Stage 2 sees tests, Stage 1 doesn't.
2. **Bounded cost** — Stage 2 is gated; doesn't fire when Stage 1 is sufficient.
3. **No damage to working code** — Stage 1's candidate is the seed; Stage 2 edits
   it rather than regenerating from scratch.
4. **Cache hit rate preserved** — Stage 1's prefix (the manifest + ADRs) is
   unchanged; Stage 2 prompts add to the cache, don't invalidate it.

## Validating Experiment

**Scope**: the four "floor" libraries from §5.4 that uniformly fail Stage 1 across
both providers on KD and B2/B3 — `chardet`, `marshmallow`, `babel`, `jinja`.
(Skip `minitorch` because §7.8 documents a smolagents sandbox quirk that confounds
the result.)

**Procedure**:
1. Run Stage 1 (KD) on each floor library, baseline Q1 = 0 expected.
2. Run Stage 2 (tool-using agent, bounded ≤ 10 iterations) on the Stage 1 output.
3. Report ΔQ1 per library and total cost. Compare against:
   - OH-only baseline (full multi-turn loop, no Stage 1 candidate)
   - Stage 1 + Stage 2 cost vs OH cost on the same libraries

**Predicted outcome** (this is a falsifiable hypothesis):
- Stage 1 + Stage 2 reaches Q1 > 0.5 on at least 2 of 4 floor libraries
- Total cost stays under 2× the Stage 1 cost (i.e., Stage 2 doesn't dominate)
- Compared to OH-only on the same libraries: ≥ 5× cheaper at comparable Q1

**Cost estimate**: ~$30 total ($5–8 per library, 4 libraries, with budget headroom).

**Falsification conditions**:
- If Stage 2 over-iterates (avg > 8 iterations per library), the composition
  fails the "bounded cost" complementarity → revisit gating.
- If Stage 2 damages Stage 1's correct parts (Q1 regresses on libraries where
  Stage 1 had partial success), the composition fails the "no damage" property
  → revisit the editor's permission scope.

## Relationship to Other ADRs

- **ADR-0052** (Adaptive Convergence via Thompson Sampling): the gating decision
  ("run Stage 2 on this library?") is a Thompson-sampling problem; the prior is
  Stage 1's Q1 distribution.
- **ADR-0058** (Opportunistic Memory Consolidation): Stage 2's per-iteration
  context grows; Level 1 batch consolidation should fire at end-of-Stage-2.
- **ADR-0063** (Round-Trip Fidelity Benchmark): Q1 from §5.4 is the exact metric
  used to gate Stage 2.

## Out of Scope for This ADR

- The exact tool-using agent to use as Stage 2 (Aider, OH, smolagents, custom).
  The validating experiment will run with at least two to disambiguate.
- Multi-language Stage 2. The Phase-1 paper is Python-only (§7.6). The
  multi-language ceiling taxonomy (TS generic-variance, Rust trait-system, see
  paper §7.6 multi-lang note) may need a different Stage 2 design — that is a
  separate ADR if and when the experiment validates the Python case.
- The follow-up paper that defines and reports the composed architecture (the
  paper's §9 notes a planned follow-up). This ADR is the design sketch; the paper
  is the validating publication.

---

## Decisions & Sign-Off
**Decision Date:** 2026-05-08
**Decided By:** Project owner
**Status:** Proposed (sketch only — validating experiment not yet run)
