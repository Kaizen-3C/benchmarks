# AAR-2 Addendum — B3 Test-Import-Aware Decompose: Nested-Blockers Finding

**Date:** 2026-04-22
**Predecessor:** [`AAR_2026-04-22_FINAL.md`](AAR_2026-04-22_FINAL.md) §"Action items" #1 — *test-import-aware Decompose, "HIGH priority — unblocks 3 of 5 floor libs"*
**Outcome:** **1 of 3 floor libs fully unlocked (voluptuous: 0% → 39%).** Marshmallow + jinja exposed 4 additional nested blockers, only 6 of which were fixable in this session. The unlock-attempt methodology validated; the architectural ceiling on text-based import scanning surfaced.

## TL;DR

The "test-import-aware Decompose" fix proposed in AAR-2 was **necessary but not sufficient** to unlock all three cross-import floor libs. Implementation revealed **a chain of 7+ nested blockers**, each visible only after the prior one was fixed. We fixed 6, unlocked 1 lib (voluptuous) cleanly, and pushed marshmallow through 4 layers before hitting an architectural ceiling that requires genuine Python name resolution to break.

## The seven-blocker chain (in order of discovery)

| # | Discovered on | Blocker | Fix deployed | Lib status after fix |
|---|---|---|---|---|
| 1 | voluptuous v1 | KD has no test-side visibility | `discover_test_imports()`: scan tests/, parse `from <X> import (a, b)` lines (incl. multi-line parens) | Still 0% — exposes #2 |
| 2 | voluptuous v2 | KD regenerates the test files themselves | `discover_files()`: exclude `tests/`, `test/`, `testing/` at any depth + skip `test_*.py` and `conftest.py` | Still 0% — exposes #3 |
| 3 | voluptuous v3 | Long files truncate mid-string → SyntaxError | `_llm.py`: `MAX_TOKENS` 16K→32K. `kaizen_delta.py`: `ast.parse()` validation pre-write; reject + retry with grounded feedback ("your previous output had SyntaxError at line N") | **VOLUPTUOUS UNLOCKED — 0% → 39%** ✅ |
| 4 | marshmallow v1 | Production-internal `from X import Y` invisible to test-only scan | `discover_test_imports()` extended to walk ALL `.py` files in repo | Still 0% — exposes #5 |
| 5 | marshmallow v2 | `relevant_test_imports()` matcher off-by-one for `src/` layouts | Compare `rel_parts[-len(mod_parts):] == mod_parts` (was `mod_parts[-len(rel_parts):] == rel_parts`) | Still 0% — exposes #6 |
| 6 | marshmallow v3 | Largest files (40KB+) still truncate at 32K output cap | `MAX_TOKENS` 32K→48K + prompt hint *"file >15KB: PRIORITIZE FUNCTION BODIES over verbose docstrings"* | Still 0% — exposes #7 |
| 7 | marshmallow v4 | **`utils.to_timestamp` attribute-access invisible to `from X import Y` scanner** | NOT YET FIXED — requires AST `Attribute` walk or runtime introspection | **0% — architectural ceiling** |
| 8 | jinja v4 | **Relative imports (`from .async_utils import async_variant`) invisible to scanner** — `.async_utils` parses to `['', 'async_utils']`, never matches `['src', 'jinja2', 'async_utils']` | NOT YET FIXED — requires per-file relative-import resolution to absolute path | **0% — second architectural ceiling** |

## Final state per lib

| Lib | After all 6 fixes | Cost | Wall | Files accepted | Architectural verdict |
|---|---|---|---|---|---|
| **voluptuous** | **39% (58/149 passed)** | $0.71 | 9 min | 6/6 | ✅ **B3 fix worked. Cheaper than OH-GPT's $1.21 for this lib.** |
| marshmallow | 0% — `AttributeError: utils.to_timestamp` | $1.43 latest | 8 min latest | 13/13 latest | Hits 7th blocker — attribute-access invisible to `from X import Y` scanner |
| jinja | 0% — `cannot import name 'async_variant' from 'jinja2.async_utils'` | $2.65 v4 | 39 min v4 | 24/25 v4 | Hits 8th blocker — relative imports (`from .X import Y`) invisible to scanner |

## What this means for AAR-2 action item #1

Original framing: *"unblocks 3 of 5 floor libs"*. Honest revised framing:

- **Voluptuous: clean unlock, 39% pass rate, $0.71.** First and only baseline of any architecture to crack voluptuous from 0% via decompose-only (OH-GPT cracked it via tool use at $1.21). Action item #1 is **partially closed** — the test-import idea works.
- **Marshmallow: blocked at the 7th layer (attribute-access).** Six fixes peeled the import-graph problem progressively. The remaining blocker is fundamentally different — it's not "what's missing from the contract?" but "how do we extract the contract from non-import-statement Python?" Solving this needs `ast.Attribute` walking or runtime introspection. Estimated: another 1–2 days of engineering.
- **Jinja: blocked at the 8th layer (relative imports).** Same fix-class as marshmallow — needs deeper Python parsing. Jinja extensively uses relative imports (`from .async_utils import async_variant`); my scanner sees `.async_utils` as an empty-package import and never resolves it to `jinja2.async_utils`. Fix is per-file relative-to-absolute resolution. Estimated: 30 min, but with diminishing return — a lib like marshmallow would still fail at attribute-access.

## The architectural-ceiling finding

Each blocker fix had **diminishing return on per-architecture effort**:

| Layer | Engineering cost | Value | Return ratio |
|---|---|---|---|
| 1–3 (voluptuous unlock) | ~2 hrs (3 small fixes) | +39 pp on 1 floor lib | **High** — clear architectural win |
| 4 (production-code scan) | ~30 min | 0 pp gained, error message changed | Neutral — investigation cost |
| 5 (matcher off-by-one) | ~10 min (one-line bug) | 0 pp gained, error message changed again | Neutral |
| 6 (max_tokens + terse hint) | ~15 min | 0 pp gained, fields.py succeeded but downstream failed | Diminishing |
| 7 (attribute-access scanner) | **NOT YET — estimated 1–2 days** | Unknown — may unlock marshmallow OR may expose layer 8 | **Asymptotic** |

After layer 6, each additional fix takes more engineering for less guaranteed payoff. Layers 1–3 are necessary first steps for any contract-aware decompose. Layer 7+ approaches the structural limits of regex/text-based scanning and starts requiring real Python semantics.

**The right architectural step at layer 7+ is NOT "another regex" but "compose with OH-style tool-use."** This is exactly the v2-architecture suggestion in [AAR-2 §6 "What we learned" #2](AAR_2026-04-22_FINAL.md#what-we-learned): *each architecture's weakness IS the other's strength*.

## What KD did well, what we'd do differently

### What worked

- **Diagnostic methodology.** Each fix surfaced exactly one blocker. The iteration was forced toward the next concrete failure, not toward the imagined one. Six fixes in ~3 hours of LLM time + ~$15 in API spend produced a documentable architectural-weakness chain.
- **`ast.parse()` reject-and-retry with grounded feedback.** When the LLM produced syntactically-broken code, the explicit retry message *"your previous output had SyntaxError at line N: <msg>"* let the model self-correct. This is the same per-attempt grounding pattern that KD applies for pytest results, generalized to the syntax level.
- **Prompt-side hint for large files.** "Be terse with docstrings" cost $0 and reduced fields.py truncation rate. Cheaper than bumping max_tokens.

### What we'd do differently next campaign

- **Test the matcher logic with a unit test before deploying.** The off-by-one in `relevant_test_imports()` cost us a full marshmallow re-run (~$1.50, ~15 min) that would have been caught by `assert relevant_test_imports(Path("src/marshmallow/utils.py"), repo, {'marshmallow.utils': {'is_aware'}})` returning the right result.
- **Run the scanner against ALL libs upfront, not just the failing ones.** We could have known the matcher would fail on src/-layout libs (cachetools, marshmallow, simpy all use src/) without running the full pipeline.
- **Stop iterating once the per-blocker engineering cost exceeds expected payoff.** After layer 6, we knew the next layer was attribute-access — the engineering cost would be 1–2 days. The right call at that point is to either (a) accept the architectural ceiling and focus on layer-7+ via compose-with-OH, or (b) commit to the deeper investment and carve out a week.

## Spend update

| Phase | Cost | Wall |
|---|---|---|
| Voluptuous unlock (v3) | $0.71 | 9 min |
| Marshmallow v1 (test-only scan, blocked at #4) | $1.55 | 14 min |
| Marshmallow v2 (production scan, blocked at #5) | $1.56 | 14 min |
| Marshmallow v3 (matcher fix, blocked at #6) | $1.71 | 17 min |
| Marshmallow v4 (terse + 48K, blocked at #7) | $1.43 | 8 min |
| Jinja v1 (blocked at #5 = matcher bug) | $2.79 | 53 min |
| Jinja v4 (in flight) | TBD | TBD |
| **Cumulative B3 spend** | **~$10** + jinja v4 | ~2 hr active |

Well within action item #1's "3–5 days" budget allocation.

## Recommendation for next session

1. **Wait for jinja v4 to land**, archive result, decide whether 2-of-3 or 1-of-3 is the campaign's final B3 unlock count.
2. **Don't pursue layer 7+ as more contract-scanner engineering.** The diminishing return is documented; further investment goes to compose-with-OH (the v2-architecture).
3. **Update [AAR-2 §Action items #1](AAR_2026-04-22_FINAL.md#action-items)** to reflect partial closure: voluptuous unlocked, marshmallow architecturally bounded, jinja status TBD.
4. **Position layer 7+ as a future ADR** (probably ADR-0064): *"Compose KD's per-file decompose with OH's test-driven tool use to address attribute-access and dynamic-introspection patterns."*

## Closing

The B3 work validated AAR-2's design hint: each architecture's weakness IS the other's strength. KD made real progress on cross-import floor libs (voluptuous unlocked) AND surfaced its own architectural ceilings (attribute-access patterns AND relative imports) by trying to push past them. **Both findings are publishable.** The first proves the methodology; the second prevents over-investment in the wrong direction.

### Final B3 score

| Floor lib | Pre-campaign (every baseline) | After B3 fixes | Verdict |
|---|---|---|---|
| voluptuous | 0% (collection broken on every architecture) | **39%** at $0.71 | ✅ Unlocked |
| marshmallow | 0% (collection broken) | 0% (peeled 4 layers, ceiling at #7 attribute-access) | Architectural ceiling |
| jinja | 0% (collection broken) | 0% (peeled 4 layers, ceiling at #8 relative imports) | Architectural ceiling |

**1 of 3 cleanly unlocked. Both ceilings are discrete, named, and recommend a specific compose-with-OH next step rather than further regex iteration.**

The campaign is complete. Eight blockers identified, six fixed, two named for the next architectural campaign. **Total session spend: ~$15.** Diagnostic methodology validated end-to-end.
