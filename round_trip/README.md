# Round-Trip Fidelity Benchmark

**Axis:** *working code → ADRs → new code.* Does the Decomposer produce ADRs faithful enough that a blind Recompose rebuilds functionally-equivalent code?

Governed by [ADR-0063](../../.architecture/decisions/ADR-0063-round-trip-fidelity-benchmark.md). Full protocol in [`PROTOCOL.md`](./PROTOCOL.md). Roadmap in [`PLAN.md`](./PLAN.md).

## Quickstart

```bash
# From repo root. Runs the full pipeline on one lib and writes JSON.
python benchmarks/round_trip/run_one.py wcwidth
```

Phase 1 (current): stubs only. The command above exits 0, costs $0, and emits a schema-matching JSON with `null` values. See [`PROTOCOL.md §4`](./PROTOCOL.md#4-result-schema).

## Layout

```
benchmarks/round_trip/
├── PLAN.md                       roadmap (phases 1–6)
├── PROTOCOL.md                   per-run operational spec
├── SESSION_PROMPT.md             starter prompt for the scaffolding session
├── README.md                     this file
├── decompose_from_reference.py   code → spec/<lib>/{adrs,contracts,oracles}
├── recompose_from_adrs.py        spec/<lib>/ → recomposed/<lib>/  (no source peeking)
├── gates/                        5 spec-quality gates (run between D and R)
├── metrics/                      Q1–Q4 fidelity metrics
├── remediation.py                gate-failure → suggested-fix mapper
├── run_one.py                    orchestrates one full round-trip
└── results/<lib>_round_trip.json one file per lib
```

## The four metrics

| ID | Name | What it measures |
|----|------|------------------|
| Q1 | test parity | canonical pytest pass-rate on recomposed code |
| Q2 | behavioral parity | (input, output) equivalence on a curated set |
| Q3 | structural parity | AST / module-level diff size |
| Q4 | information loss | % of public symbols mentioned in ≥1 ADR |

## The five gates

| Gate | Detects |
|------|---------|
| coverage | public symbols missing from any ADR |
| specificity | vague ADRs ("we use a cache" — no params) |
| consistency | dangling cross-refs in contracts |
| test-oracle alignment | canonical tests without analog in `oracles/` |
| implementation-leak | code-shaped content in ADRs (cheating) |

## Status

Phase 1 (scaffolding) — see `PLAN.md` for what lands next.
