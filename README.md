# Kaizen-3C / benchmarks

**Architectural-weakness fingerprinting for AI software-engineering agents.**

This repo holds the methodology, data, and analysis scripts for evaluating coding-agent architectures on the dimensions that matter for production use: not just "did the test pass?" but *what did the architecture contribute beyond the LLM that powers it?*

We measure **value-add per dollar**, **LLM-leanness**, **architectural blockers**, and **cost-shape** across an 8-architecture × 16-library matrix on the [commit0](https://github.com/wentingzhao/commit0) lite split — and we publish the per-cell raw data, the analysis code, and the named architectural ceilings we hit.

> **3C lineage.** This work sits under the [Kaizen-3C](https://github.com/Kaizen-3C) org. The "3C" reframes the original Kaizen 3C method (*Concern · Cause · Countermeasure*) for the software industry as **Code · Compose · Compliance**. Benchmarks are how we measure the **Code** layer honestly.

---

## What's in this repo

| Benchmark | Status | Purpose |
|---|---|---|
| **[`commit0/`](commit0/)** | Complete (2026-04 campaign) — 8 archs × 16 libs × 2 models | Greenfield code generation against pinned golden tests. Produces the **value-add fingerprint** methodology. |
| **[`round_trip/`](round_trip/)** | Phase 1 scaffolded | Code → ADR → Code round-trip fidelity. Measures whether an architecture preserves semantics across decompose/recompose cycles. |
| **[`realworld/`](realworld/)** | Protocol only — no runs yet | Disaster-recovery / "real-world" rebuilds against production codebases. |

Each subdirectory is self-contained: PROTOCOL.md, run scripts, results, and analysis.

---

## Headline findings (commit0 lite, 2026-04)

8 architectures × 16 libraries × 2 model providers. Total spend: **$182.41**. Total wall: **~12 hours active**. See [`commit0/AAR_2026-04-22_FINAL.md`](commit0/AAR_2026-04-22_FINAL.md) for the full report.

| Architecture | Tests passed / attempted | Cost | Notes |
|---|---:|---:|---|
| B2 single-shot Sonnet | 1,019 / 2,008 | $7.31 | Fastest, cheapest, no architecture |
| B2 single-shot GPT-5.4 | 767 / 1,925 | $2.88 | — |
| B3 Reflexion Sonnet | 498 / 1,564 | $10.89 | 3-iter reflexion w/ retry |
| B3 Reflexion GPT-5.4 | 787 / 1,754 | $4.12 | — |
| KD Kaizen-delta Sonnet | 1,167 / 3,325¹ | $21.95 | Per-file decompose + module-level pytest grounding |
| KD Kaizen-delta GPT-5.4 | 969 / 1,583 | $10.57 | — |
| OH OpenHands V1 Sonnet (6 of 16) | 1,025 / 1,028 | $94.31 | Tool-use loop; high cost, high resolved-rate where it ran |
| OH OpenHands V1 GPT-5.4 (14 of 16) | 11,177 / 11,193 | $30.38 | — |

¹ KD-Sonnet's denominator inflated by the babel collection unlock (22 errors → 1,281 collected tests).

### What we proved

1. **The value-add fingerprint methodology works.** Each architecture has a measurable *contribution beyond its LLM* — and that contribution is per-library, not uniform.
2. **Floor libraries reveal architectural blockers.** Three libraries (voluptuous, marshmallow, jinja) collapse on every baseline at 0%. Pushing past them surfaces concrete, named architectural ceilings.
3. **One floor lib unlocked.** Kaizen-delta cracked voluptuous from 0% → 39% at $0.71 via three small fixes (test-import scanning, file exclusion, syntax-validated retry).
4. **Two architectural ceilings named.** Marshmallow → attribute-access patterns invisible to text-based import scanners. Jinja → relative-import resolution (`from .X import Y`). Both require either AST-level walking or runtime introspection. See [`commit0/AAR_2026-04-22_B3_ADDENDUM.md`](commit0/AAR_2026-04-22_B3_ADDENDUM.md).

---

## Reproduce

The full reproduction protocol is in **[`commit0/CAMPAIGN_README.md`](commit0/CAMPAIGN_README.md)** — pinned versions, WSL2 setup, run order, expected aggregate numbers. Below is the orientation.

### Prerequisites

- WSL2 Ubuntu-24.04 (Windows host has 3 documented commit0 0.1.8 bugs — use WSL)
- Python 3.12, Docker Desktop with Linux-container backend
- Anthropic API key, OpenAI API key (~$200 budget for the full sweep)

### Quick start

```bash
# Inside WSL2
git clone https://github.com/Kaizen-3C/benchmarks
cd benchmarks/commit0
# Follow CAMPAIGN_README.md from "One-time WSL setup" onward
```

### Just-the-analysis (no model spend)

If you want to inspect the methodology without re-running the whole sweep, all our raw `results/` JSONs are checked in. The four analysis scripts are self-contained:

```bash
python commit0/baselines/value_add_fingerprint.py   # 8 × 16 weakness matrix
python commit0/baselines/compare_baselines.py       # per-arch aggregates
python commit0/baselines/cache_analysis.py          # cache-effectiveness w/ counterfactual
python commit0/baselines/value_add_table.py         # us-vs-them per-lib table
```

---

## Methodology paper (forthcoming)

A whitepaper covering the value-add fingerprint methodology, the 8-architecture matrix, the named architectural blockers, and recommendations for next-generation composed architectures is in progress. Target: NeurIPS 2026 Datasets & Benchmarks Track.

Outline location (when ready): [`paper/OUTLINE.md`](paper/OUTLINE.md).

If you want to be notified when the preprint drops, watch this repo or follow [@Kaizen-3C](https://github.com/Kaizen-3C).

---

## Repository layout

```
benchmarks/
├── README.md                          (this file)
├── LICENSE                            (MIT)
├── commit0/                           (the 2026-04 campaign — 8 archs × 16 libs)
│   ├── PROTOCOL.md                    (per-architecture run procedure)
│   ├── PLAN_2026-04-21.md             (symmetric-coverage tiers + value-add framework)
│   ├── AAR_2026-04-21.md              (mid-campaign post-mortem)
│   ├── AAR_2026-04-22_FINAL.md        (final findings + architectural fingerprint)
│   ├── AAR_2026-04-22_B3_ADDENDUM.md  (8-blocker chain + voluptuous unlock)
│   ├── CAMPAIGN_README.md             (full reproduction protocol)
│   ├── baselines/                     (scripts: B2/B3/KD/OH runners + analysis)
│   └── results/                       (~80 per-lib result JSONs)
├── round_trip/                        (Code → ADR → Code fidelity benchmark)
│   ├── PROTOCOL.md
│   ├── PLAN.md                        (6-phase implementation roadmap)
│   ├── README.md
│   └── (metrics, gates, run_one.py — Phase 1 scaffolding)
├── realworld/                         (real-world disaster-recovery benchmark)
│   └── PROTOCOL.md
└── docs/
    └── architectural-context/         (mirrored ADRs from kaizen-delta)
        ├── ADR-0059-realworld-dr-benchmark.md
        ├── ADR-0060-commit0-greenfield-benchmark.md
        └── ADR-0063-round-trip-fidelity-benchmark.md
```

---

## Relationship to Kaizen-delta

Kaizen-delta (currently private) is the integrated dev monorepo where the Kaizen architecture-first AI platform is built. This benchmarks repo is **independent of any specific architecture** — the methodology is designed to evaluate any agent stack (Aider, smolagents, OpenHands, Cursor, custom in-house architectures). Kaizen-delta is the first reference architecture in the matrix; we welcome contributions adding others.

For Kaizen the product, see [`Kaizen-3C/kaizen-cli`](https://github.com/Kaizen-3C/kaizen-cli) (coming W2 2026-04).

---

## Contributing

We welcome:
- **New architectures** in the matrix. The simplest path: add a `commit0/baselines/<your_arch>.py` runner that produces the JSON schema documented in CAMPAIGN_README.md, then run the four analysis scripts.
- **New libraries** beyond the commit0 lite split. Same pipeline; lib-agnostic by design.
- **New metrics** that surface different architectural dimensions. Open an issue with the proposed metric and a sketch of how it would be computed from the existing JSON output.
- **Reproductions** of our published numbers. If your numbers diverge significantly from `CAMPAIGN_README.md`'s "Expected aggregate numbers" table, open an issue with your run details — we'll help debug and update the doc.

Open an issue or a PR. Tag `@Kaizen-3C/benchmarks-maintainers`.

---

## Citation

If you use this benchmark methodology in research:

```
@misc{kaizen3c2026benchmarks,
  title  = {Architectural-weakness fingerprinting for AI software-engineering agents:
            an 8-architecture {\texttimes} 16-library commit0 evaluation},
  author = {Adame, Anthony and {Kaizen-3C}},
  year   = {2026},
  url    = {https://github.com/Kaizen-3C/benchmarks}
}
```

The methodology paper (when published) will provide the canonical citation. Until then, please link to this repo.

---

## License

MIT (see [`LICENSE`](LICENSE)). Same as commit0 and OpenHands — chosen for maximum reuse and adoption.
