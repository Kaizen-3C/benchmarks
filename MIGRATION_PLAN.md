# Migration Plan — Move Benchmarks to `Kaizen-3C/benchmarks`

**Date:** 2026-04-22
**Scope:** Carve out the commit0 + round-trip + RealWorld benchmark work into a standalone public repo. Keep Kaizen-delta agent code where it is.
**Author:** plan; awaiting decision on the three open questions at the bottom.

## Why split

| Pro of splitting | Con of staying coupled |
|---|---|
| Benchmark methodology is a product on its own — usable by Aider, smolagents, Cline, etc. | Currently buried in a repo whose primary purpose is the Kaizen-delta agent |
| Different release cadence (benchmarks change with new models; agent changes with feature work) | Single-repo CI runs everything every time |
| Independent contributor pool (eval-curious folks may not care about Kaizen-delta) | Permission/access coupling — every benchmark contributor needs commit access to the agent code |
| Methodology paper can cite benchmark repo independently | Hard to license benchmarks separately if Kaizen-delta ever changes license |
| Smaller, cleaner README → easier on first impression | Discoverability is poor — `benchmarks/commit0/` hides 30+ files |

**Decision driver:** the value-add fingerprint methodology is a contribution that stands on its own. Other architectures can use it without adopting Kaizen-delta. That's the test for "deserves its own repo."

## What moves

```
benchmarks/                           → new repo root
├── commit0/                          → commit0/ (untouched)
│   ├── PROTOCOL.md
│   ├── PLAN_2026-04-21.md
│   ├── AAR_2026-04-21.md
│   ├── AAR_2026-04-22_FINAL.md
│   ├── AAR_2026-04-22_B3_ADDENDUM.md
│   ├── CAMPAIGN_README.md
│   ├── baselines/                    (8 baselines, fingerprint scripts)
│   └── results/                      (~80 result JSONs, 6 OH partial dirs)
├── round_trip/                       → round_trip/ (Phase 1 scaffolded)
│   ├── PLAN.md
│   ├── PROTOCOL.md
│   ├── SESSION_PROMPT.md
│   ├── README.md
│   └── (all the metrics/, gates/, run_one.py, etc.)
└── realworld/                        → realworld/ (PROTOCOL only, no runs yet)
    └── PROTOCOL.md
```

Plus these ADRs need to either move or stub-link:
- `ADR-0059-realworld-dr-benchmark.md`
- `ADR-0060-commit0-greenfield-benchmark.md` (incl. Amendments 1+2)
- `ADR-0063-round-trip-fidelity-benchmark.md`

**Recommendation:** keep ADRs in Kaizen-delta as the *architectural* record (these decisions affect the agent's roadmap), but **mirror them as `docs/architectural-context/` in the benchmarks repo** so the benchmarks repo is self-explanatory.

## What stays in Kaizen-delta

- All agent code (`agents/`, `cli/`, `core/`, `decompose/`, `recompose/`, `cost_tracking/`, etc.)
- All ADRs (0001–0063), including the three benchmark ADRs as architectural context
- Other benchmark workspaces that aren't "the public matrix" (e.g., the cdaor-benchmarks paper work — different audience)

## The dependency question

`benchmarks/commit0/baselines/_llm.py` is shared infrastructure: provider-agnostic LLM client + cost helper, used by every baseline. Three options:

| Option | Pros | Cons |
|---|---|---|
| **A. Duplicate `_llm.py` in both repos** | Trivial migration; no cross-repo coupling | Two copies to maintain; bug fixes have to land in both |
| **B. Publish `kaizen-llm` as a small PyPI package** both repos depend on | One source of truth; clean import | Extra release process; benchmarks wait on PyPI for fixes |
| **C. Benchmarks repo vendors a copy** (committed, not pip-installed) and Kaizen-delta sources it from `vendor/` | No extra release; both repos at known state | Requires explicit vendor refresh; people forget |

**Recommendation: A (duplicate).** `_llm.py` is ~110 lines. Bug fixes are rare (we touched it twice in the entire campaign). Optimize for low-friction over abstract purity. If the file grows past ~500 lines or sees frequent churn, escalate to B.

## Migration steps

| # | Step | Effort | Owner |
|---|---|---|---|
| 1 | Create `Kaizen-3C/benchmarks` repo with MIT license + README + CI skeleton | 30 min | @aadame |
| 2 | `git subtree split --prefix=benchmarks main` from Kaizen-delta to extract history | 15 min | @aadame |
| 3 | Push split branch as `Kaizen-3C/benchmarks` `main` | 5 min | @aadame |
| 4 | Add top-level `benchmarks/README.md` (rewritten to be the new repo's front door) | 1 hr | @aadame |
| 5 | Mirror ADR-0059, 0060, 0063 to `docs/architectural-context/` in new repo | 15 min | @aadame |
| 6 | Update Kaizen-delta's `benchmarks/` directory to a `README.md` pointer + git submodule (optional) OR delete entirely with a forwarding note | 30 min | @aadame |
| 7 | Update `_llm.py` duplicates with a header comment: *"duplicated from `Kaizen-3C/benchmarks/commit0/baselines/_llm.py`; sync manually on changes"* | 10 min | @aadame |
| 8 | Update all internal links + AAR cross-references to use absolute GitHub URLs to the new repo | 30 min | @aadame |
| 9 | Re-run all analysis scripts in the new repo to validate nothing broke | 15 min | @aadame |

**Total: ~3.5 hours of focused work.** No code changes; just git surgery + doc cleanup.

## Roadmap for the new repo

### Phase 1 — Migration (week 1)
- Steps 1-9 above
- README explains: methodology, the 16-lib commit0 matrix, the value-add fingerprint, how to reproduce
- Public announcement: short blog post or X thread linking the repo

### Phase 2 — Methodology paper (weeks 2-4)
- Whitepaper (10-15 pages) covering:
  - Why "agent benchmarks" hide architectural value-add
  - The value-add-pp / llm-lean / coverage metric set
  - Reproducible methodology
  - 8-architecture × 16-library results
  - Floor-lib unlocks as the architectural-strength signal
- Publish as ArXiv preprint + repo `paper/` directory

### Phase 3 — Ecosystem (weeks 4-12)
- Round-trip benchmark Phases 2-6 (per `round_trip/PLAN.md`)
- Add 1-2 more architectures from the wider community (Aider, smolagents) for cross-architecture validation
- Submit to NeurIPS Datasets & Benchmarks track OR MLSys workshop OR ICSE eval track
- HuggingFace dataset publication for the result matrix
- Public leaderboard (small — just the matrix, not real-time submissions yet)

## "Aim higher" — three publication tiers

| Tier | Effort | Output | When |
|---|---|---|---|
| **1. Whitepaper + repo** | 1-2 weeks | ArXiv preprint, GitHub README | Phase 2 |
| **2. Workshop / D&B paper** | 4-6 weeks | NeurIPS D&B Track or MLSys Datasets workshop | Phase 3 (Q3 2026) |
| **3. Full benchmark project** | 3-6 months | Leaderboard, real submissions, multi-architecture coverage, conference paper at ICSE/FSE | 2026 H2 + 2027 |

**My recommendation: Tier 2.** The data we have (8 architectures × 16 libs, value-add fingerprint, 4 floor-lib unlocks, 8 named architectural blockers) is sufficient signal for a workshop-grade D&B paper. Tier 3 requires sustained ecosystem attention that competes with Kaizen-delta development — defer until we have Phase 2 reception.

## CLI integration — Kaizen-delta CLI gains a `bench` subcommand

The CLI is in flight (per the user). Adding benchmark features makes the methodology accessible without leaving the agent's mental model. Three integration depths:

| Depth | Surface | Cost | Value |
|---|---|---|---|
| **Thin** | `kaizen bench` is a wrapper that shells out to the `Kaizen-3C/benchmarks` runner | 1-2 days | Discoverability + frictionless start |
| **Medium** | `kaizen bench` includes the value-add fingerprint analysis as a first-class command (`kaizen bench fingerprint --results <dir>`) but delegates running to the benchmarks repo | 3-5 days | Above + makes "evaluate my workload" a 1-liner |
| **Deep** | CLI bundles the entire benchmark harness (commit0 setup, OH SDK install, etc.) | 2-3 weeks | Single tool experience, but huge dep footprint |

**Recommendation: Medium.** Three concrete commands:

```bash
# Run a benchmark on the user's local Kaizen-delta config
kaizen bench commit0 --provider anthropic --model claude-sonnet-4-6 --libs wcwidth,deprecated

# Compute the value-add fingerprint from any results dir
kaizen bench fingerprint --results ./my-results/

# Compare two architectures' results head-to-head
kaizen bench compare --a my-results --b ./reference/kaizen-sonnet-4-6
```

Implementation:
- `kaizen-cli` adds an optional extra `bench` (`pip install kaizen[bench]`) that pulls `Kaizen-3C/benchmarks` as a dependency
- Without the extra: commands print "install with `pip install kaizen[bench]` to enable"
- The bench subcommands import from the benchmarks repo's installed package
- Keeps the core CLI dep-light; users opt in

## The three open questions for the user

1. **License:** the campaign's results + scripts are currently under the Kaizen-delta repo's license. The new repo should be permissive (MIT or Apache-2.0) so others can adopt the methodology. **Recommend: MIT.** Same as commit0 + OpenHands.

2. **Brand:** `Kaizen-3C` is a separate org/identity from `kaizen-delta`. What's the framing — "the benchmarks team that produced Kaizen-delta's eval campaigns" or "an independent eval methodology"? Affects README tone, contributor docs, and how aggressively to court contributions from non-Kaizen-delta architectures. **Recommend: position as independent methodology with Kaizen-delta as the first reference architecture.** Maximizes credibility and contributor pool.

3. **Tier 2 commitment:** Tier 2 (workshop paper) is 4-6 weeks of writing time. Worth committing to NOW, or wait until Phase 2 reception? **Recommend: commit now and target NeurIPS 2026 D&B track (deadline typically May/June 2026).** The data is fresh, the methodology is sharp, and a hard deadline forces the writing to happen.

## Specific next-action checklist

If decisions land yes-yes-yes on the recommendations above:

- [ ] Create `Kaizen-3C` GitHub org (5 min)
- [ ] Create `Kaizen-3C/benchmarks` empty repo with MIT license (10 min)
- [ ] Run migration steps 1-9 (3.5 hrs)
- [ ] Write the new top-level README (1 hr; can reuse most of `CAMPAIGN_README.md`)
- [ ] Announce: short blog post or X thread (1 hr)
- [ ] Start whitepaper outline in `Kaizen-3C/benchmarks/paper/OUTLINE.md` (1 hr)
- [ ] Add `kaizen bench` subcommand stub to the CLI (2 hrs)
- [ ] Schedule NeurIPS D&B paper writing in the calendar

**Total to public launch: ~1 working day. Total to whitepaper draft: 2-3 weeks. Total to NeurIPS submission: 4-6 weeks.**
