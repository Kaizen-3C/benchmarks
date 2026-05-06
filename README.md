# Kaizen-3C / benchmarks

**Architectural-weakness fingerprinting for AI software-engineering agents.**

This repo holds the methodology, data, and analysis scripts for evaluating coding-agent architectures on the dimensions that matter for production use: not just "did the test pass?" but *what did the architecture contribute beyond the LLM that powers it?*

We measure **value-add per dollar**, **LLM-leanness**, **architectural blockers**, and **cost-shape** across a 10-architecture × 16-library matrix on the [commit0](https://github.com/wentingzhao/commit0) lite split — and we publish the per-cell raw data, the analysis code, and the named architectural ceilings we hit.

> **3C lineage.** This work sits under the [Kaizen-3C](https://github.com/Kaizen-3C) org. The "3C" reframes the original Kaizen 3C method (*Concern · Cause · Countermeasure*) for the software industry as **Code · Compose · Compliance**. Benchmarks are how we measure the **Code** layer honestly.

---

## What's in this repo

| Benchmark | Status | Purpose |
|---|---|---|
| **[`commit0/`](commit0/)** | Complete (2026-04 campaign + 2026-05 Phase 1) — 10 archs × 16 libs × 2 models | Greenfield code generation against pinned golden tests. Produces the **value-add fingerprint** methodology. |
| **[`round_trip/`](round_trip/)** | Phase 1 scaffolded | Code → ADR → Code round-trip fidelity. Measures whether an architecture preserves semantics across decompose/recompose cycles. |
| **[`realworld/`](realworld/)** | Protocol only — no runs yet | Disaster-recovery / "real-world" rebuilds against production codebases. |

Each subdirectory is self-contained: PROTOCOL.md, run scripts, results, and analysis.

### Harness scaffolding (contributor invitations)

Beyond the three benchmarks above, this repo includes a **generic harness** shared across all current and future benchmarks (`runner.py`, `base_adapter.py`, `calibration.py`, `compare_results.py`, `download_datasets.py`) plus **stub adapters** ready to extend:

| Stub | Status |
|---|---|
| [`humaneval/`](humaneval/) | Adapter stub — implementation welcome via PR |
| [`mbpp/`](mbpp/) | Adapter stub — implementation welcome via PR |
| [`swebench/`](swebench/) | Adapter stub — implementation welcome via PR |
| [`terminalbench/`](terminalbench/) | Adapter stub — implementation welcome via PR |

The harness is benchmark-agnostic by design; adding a new benchmark is a matter of writing the adapter, not modifying the harness. See [`CONTRIBUTING.md`](CONTRIBUTING.md#new-sub-benchmarks) for the path.

---

## Headline findings (commit0 lite, 2026-04 base + 2026-05 Phase 1)

10 (architecture × provider) cells × 16 libraries. Total spend: **$247.53** ($182.41 base + $65.12 Phase 1). Total wall: **~12 h active + 10 h Phase 1 (parallel)**. See [`commit0/AAR_2026-04-22_FINAL.md`](commit0/AAR_2026-04-22_FINAL.md) and [`commit0/AAR_2026-05-05_PHASE1_ADDENDUM.md`](commit0/AAR_2026-05-05_PHASE1_ADDENDUM.md) for the full reports.

| Architecture | Tests passed / attempted | Cost | Notes |
|---|---:|---:|---|
| B2 single-shot Sonnet | 1,019 / 2,008 | $7.31 | Fastest, cheapest, no architecture |
| B2 single-shot GPT-5.4 | 767 / 1,925 | $2.88 | — |
| B3 Reflexion Sonnet | 498 / 1,564 | $10.89 | 3-iter reflexion w/ retry |
| B3 Reflexion GPT-5.4 | 787 / 1,754 | $4.12 | — |
| KD Kaizen-delta Sonnet | 1,167 / 3,325¹ | $21.95 | Per-file decompose + module-level pytest grounding |
| KD Kaizen-delta GPT-5.4 | 969 / 1,583 | $10.57 | — |
| **Aider Sonnet** *(Phase 1)* | **493 / 506** | **$16.80** | Search/replace edit blocks; native Anthropic prompt cache (92% hit) |
| **Aider GPT-5.4** *(Phase 1)* | **385 / 398** | **$9.63** | 8–15× faster wall than Sonnet on auto-test loop |
| **smolagents Sonnet** *(Phase 1)* | **639 / 650** | **$29.25** | CodeAct-style; 25 min wall on 15 libs (skipped wcwidth — smoke-tested earlier) |
| **smolagents GPT-5.4** *(Phase 1)* | **830 / 843** | **$9.44** | 11–14 LLM calls/library on average |
| OH OpenHands V1 Sonnet (6 of 16) | 1,025 / 1,028 | $94.31 | Tool-use loop; high cost, high resolved-rate where it ran |
| OH OpenHands V1 GPT-5.4 (14 of 16) | 11,177 / 11,193 | $30.38 | — |

¹ KD-Sonnet's denominator inflated by the babel collection unlock (22 errors → 1,281 collected tests).

### What we proved

1. **The value-add fingerprint methodology works.** Each architecture has a measurable *contribution beyond its LLM* — and that contribution is per-library, not uniform.
2. **No best architecture across the matrix.** 5 of 6 architectures show *both* +90 pp wins and ≤−50 pp regressions on different libraries. Aggregate pass-rate hides architecture-shaped failures.
3. **Floor libraries reveal architectural blockers.** Three libraries (voluptuous, marshmallow, jinja) collapse on every legacy baseline at 0%. Phase 1 architectures (Aider, smolagents) unlock most of them.
4. **One floor lib unlocked by KD.** Kaizen-delta cracked voluptuous from 0% → 39% at $0.71 via three small fixes (test-import scanning, file exclusion, syntax-validated retry).
5. **Two architectural ceilings named.** Marshmallow → attribute-access patterns invisible to text-based import scanners. Jinja → relative-import resolution (`from .X import Y`). Both require either AST-level walking or runtime introspection. See [`commit0/AAR_2026-04-22_B3_ADDENDUM.md`](commit0/AAR_2026-04-22_B3_ADDENDUM.md).
6. **9.8× cache-configuration cost gap.** Cached architectures (KD, Aider) show 92% Anthropic ephemeral cache hit; uncached (OH local-Docker, smolagents) show 0%. Same libraries, same model — config, not quality.

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

If you want to inspect the methodology without re-running the whole sweep, all our raw `results/` JSONs are checked in. The analysis scripts are self-contained:

```bash
python commit0/baselines/value_add_fingerprint.py   # 10 × 16 weakness matrix (10 = 5 archs × 2 providers)
python commit0/baselines/phase1_summary.py          # Phase 1 (Aider + smolagents) aggregate table
python commit0/baselines/compare_baselines.py       # per-arch aggregates
python commit0/baselines/cache_analysis.py          # cache-effectiveness w/ counterfactual
python commit0/baselines/value_add_table.py         # us-vs-them per-lib table
```

The fingerprint heatmap (Figure 1 in the methodology paper) regenerates from the same JSONs:

```bash
python paper/figures/figure1_fingerprint_heatmap.py   # → paper/figures/figure1.{pdf,png}
```

---

## Methodology paper (forthcoming)

A whitepaper covering the value-add fingerprint methodology, the 10-cell (architecture × provider) reference matrix, the named architectural ceilings (attribute-access invisibility, relative-import resolution), and a concrete decompose-then-tool-use composability proposal is in late draft. Target: arXiv preprint 2026-05-22; ICLR 2027 Datasets & Benchmarks Track when the CFP opens (Sep–Oct 2026).

Figure 1 (the fingerprint heatmap) is already rendered at [`paper/figures/figure1.pdf`](paper/figures/figure1.pdf).

If you want to be notified when the preprint drops, watch this repo or follow [@Kaizen-3C](https://github.com/Kaizen-3C).

---

## Repository layout

```
benchmarks/
├── README.md                          (this file)
├── LICENSE                            (MIT)
├── commit0/                           (the 2026-04 campaign + 2026-05 Phase 1 — 10 archs × 16 libs)
│   ├── PROTOCOL.md                    (per-architecture run procedure)
│   ├── PLAN_2026-04-21.md             (symmetric-coverage tiers + value-add framework)
│   ├── AAR_2026-04-21.md              (mid-campaign post-mortem)
│   ├── AAR_2026-04-22_FINAL.md        (final findings + architectural fingerprint)
│   ├── AAR_2026-04-22_B3_ADDENDUM.md  (8-blocker chain + voluptuous unlock)
│   ├── AAR_2026-05-05_PHASE1_ADDENDUM.md  (Aider + smolagents matrix extension)
│   ├── CAMPAIGN_README.md             (full reproduction protocol; updated for Phase 1)
│   ├── baselines/                     (scripts: B2/B3/KD/Aider/smolagents/OH runners + analysis)
│   │   ├── aider/                     (Phase 1 — search/replace agent runner + SETUP)
│   │   ├── smolagents/                (Phase 1 — CodeAct-style agent runner + SETUP)
│   │   └── ...                        (B2, B3, KD, OH, _llm, fingerprint, summary)
│   └── results/                       (~144 per-lib result JSONs + 6 aggregates)
├── round_trip/                        (Code → ADR → Code fidelity benchmark)
│   ├── PROTOCOL.md
│   ├── PLAN.md                        (6-phase implementation roadmap)
│   ├── README.md
│   └── (metrics, gates, run_one.py — Phase 1 scaffolding)
├── realworld/                         (real-world disaster-recovery benchmark)
│   └── PROTOCOL.md
├── paper/                             (methodology paper companion artifacts)
│   └── figures/                       (Figure 1 — value-add fingerprint heatmap)
└── docs/
    └── architectural-context/         (mirrored ADRs from kaizen-delta)
        ├── ADR-0059-realworld-dr-benchmark.md
        ├── ADR-0060-commit0-greenfield-benchmark.md
        └── ADR-0063-round-trip-fidelity-benchmark.md
```

---

## Relationship to Kaizen-delta

Kaizen-delta (currently private) is the integrated dev monorepo where the Kaizen architecture-first AI platform is built. This benchmarks repo is **independent of any specific architecture** — the methodology is designed to evaluate any agent stack (Aider, smolagents, OpenHands, Cursor, custom in-house architectures). Kaizen-delta is the first reference architecture in the matrix; we welcome contributions adding others.

For Kaizen the product, see [`Kaizen-3C/kaizen-cli`](https://github.com/Kaizen-3C/kaizen-cli) — `pip install kaizen-3c-cli` (Apache-2.0, [PyPI](https://pypi.org/project/kaizen-3c-cli/)).

---

## Contributing

We welcome:
- **New architectures** in the matrix. The simplest path: add a `commit0/baselines/<your_arch>.py` runner that produces the JSON schema documented in CAMPAIGN_README.md, then run the four analysis scripts.
- **New libraries** beyond the commit0 lite split. Same pipeline; lib-agnostic by design.
- **New metrics** that surface different architectural dimensions. Open an issue with the proposed metric and a sketch of how it would be computed from the existing JSON output.
- **Reproductions** of our published numbers. If your numbers diverge significantly from `CAMPAIGN_README.md`'s "Expected aggregate numbers" table, open an issue with your run details — we'll help debug and update the doc.

Open an issue or a PR. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full contributor guide, including the DCO sign-off requirement. Security disclosures: see [`SECURITY.md`](SECURITY.md). General contact: hello@kaizen-3c.dev.

---

## Citation

If you use this benchmark methodology in research:

```
@misc{adame2026kaizen3cbenchmarks,
  title        = {Architectural-weakness fingerprinting for AI software-engineering agents:
                  a 10-cell {(}architecture {\texttimes} provider{)} {\texttimes} 16-library commit0 evaluation},
  author       = {Adame, Anthony},
  year         = {2026},
  howpublished = {Kaizen-3C project, \url{https://kaizen-3c.dev}},
  url          = {https://github.com/Kaizen-3C/benchmarks}
}
```

The methodology paper (when published) will provide the canonical citation. Until then, please link to this repo.

---

## License

MIT (see [`LICENSE`](LICENSE)). Same as commit0 and OpenHands — chosen for maximum reuse and adoption.
