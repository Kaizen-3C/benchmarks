# Round-Trip (Code→ADR→Code) — Operational Protocol

**Governed by:** [ADR-0063](../../.architecture/decisions/ADR-0063-round-trip-fidelity-benchmark.md)
**Plan:** [`PLAN.md`](./PLAN.md) · **Scaffolding prompt:** [`SESSION_PROMPT.md`](./SESSION_PROMPT.md)
**Sister protocols:** [`../commit0/PROTOCOL.md`](../commit0/PROTOCOL.md), [`../realworld/PROTOCOL.md`](../realworld/PROTOCOL.md)

This doc is the per-run operational spec for the round-trip benchmark. Mirrors the structure of `commit0/PROTOCOL.md` so the two reports compose.

---

## 1. What the benchmark measures

> *If our Decomposer reads working code, does it produce ADRs faithful enough that a fresh Recompose rebuilds functionally-equivalent code?*

commit0 (ADR-0060) tests Recompose alone. RealWorld (ADR-0059) tests cross-stack translation. Round-trip is the only axis that tests **the ADR intermediate format itself**.

## 2. Corpus

- **Corpus A — commit0-lite (16 libs):** same list as `commit0/PROTOCOL.md §1.2`. Source: `~/kaizen-commit0/repos/<lib>/` at each lib's `reference_commit` SHA.
- **Corpus B — curated PyPI (10 libs):** `attrs`, `click`, `httpx` (subset), `pydantic` (subset), plus 6 TBD. Phase 5 only.

## 3. Pipeline (per-lib)

```
~/kaizen-commit0/repos/<lib>  ──(1)──▶  spec/<lib>/{adrs,contracts,oracles}
                                              │
                                            (2) 5 gates
                                              │
                                              ▼
                                     (3) recomposed/<lib>/
                                              │
                                            (4) 4 metrics
                                              │
                                              ▼
                                   results/<lib>_round_trip.json
```

| Step | Module | What it does |
|---|---|---|
| 1 | `decompose_from_reference.py` | Reads the working source, emits ADRs + contracts + oracles. MUST NOT copy code. |
| 2 | `gates/*.py` | Coverage, specificity, consistency, test-oracle alignment, implementation-leak. Each returns `{gate, pass, failures}`. |
| 3 | `recompose_from_adrs.py` | Reads ONLY `spec/<lib>/`. Emits a source tree. Seeing the original rigs the run. |
| 4 | `metrics/q[1-4]_*.py` | Q1 test parity, Q2 behavioral parity, Q3 structural parity, Q4 information loss. |
| 5 | `run_one.py` | Orchestrates 1–4, writes the JSON. |

## 4. Result schema

Every run writes `results/<lib>_round_trip.json`:

```json
{
  "lib": "wcwidth",
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "decompose": {"cost_usd": 0, "elapsed_s": 0, "files_in_spec": 0},
  "gates": {
    "coverage":             {"pass": null, "failures": []},
    "specificity":          {"pass": null, "failures": []},
    "consistency":          {"pass": null, "failures": []},
    "test_oracle_alignment":{"pass": null, "failures": []},
    "implementation_leak":  {"pass": null, "failures": []}
  },
  "recompose": {"cost_usd": 0, "elapsed_s": 0, "files_emitted": 0},
  "metrics": {
    "q1_test_parity":        {"value": null, "detail": {}},
    "q2_behavioral_parity":  {"value": null, "detail": {}},
    "q3_structural_parity":  {"value": null, "detail": {}},
    "q4_information_loss":   {"value": null, "detail": {}}
  },
  "totals": {"cost_usd": 0, "elapsed_s": 0}
}
```

`null` values are expected while phases 2–3 are still in progress.

## 5. Per-phase success criteria

| Phase | Deliverable | Success criterion |
|---|---|---|
| 1 (scaffolding, now) | all files in §3 exist as runnable skeletons | `python run_one.py wcwidth` exits 0, writes schema-matching JSON, costs $0 |
| 2 (real metrics) | Q1–Q4 compute real values | wcwidth Q1 ≥ 0.9 on a Kaizen-delta-generated recompose (sanity pilot) |
| 3 (real gates) | all 5 gates + remediation engine | each gate validated against ≥1 known-failing canonical example |
| 4 (Corpus A) | 16-lib sweep | aggregate Q1 ≥ 0.3 (commit0-lite SOTA floor), per-gate failure histogram |
| 5 (Corpus B) | 10 PyPI libs | prose comparison vs commit0; methodology writeup starts |
| 6 | `docs/round_trip_methodology.md` | external-facing paper draft |

## 6. Execution environment

- **Host:** WSL2 Ubuntu 24.04, same venv as commit0 (`~/kaizen-commit0/.venv`). See `commit0/PROTOCOL.md §6.1` for why not Windows-native.
- **Repo:** `/mnt/c/RepoEx/Kaizen-delta` (NTFS mount, read-only for the runner).
- **Source trees:** `~/kaizen-commit0/repos/<lib>/` at `git checkout reference_commit`.
- **Dockers:** reused verbatim from commit0 per-lib images (needed for Q1 canonical pytest runs).
- **Provider keys:** `.env` at repo root. Defaults: `ANTHROPIC_API_KEY` + `claude-sonnet-4-6`.

## 7. Cost accounting

| Phase | Rough ceiling |
|---|---|
| 1 scaffolding | $5 (expected $0 — stubs make no LLM calls) |
| 2 metrics (per pilot lib) | $2–3 |
| 3 gates (no LLM per gate; metadata only) | $0 |
| 4 Corpus A (16 libs, with caching) | $30 |
| 5 Corpus B (10 PyPI libs) | $50–100 |

Every LLM call uses `_llm.LLMClient` from `benchmarks/commit0/baselines/_llm.py` so caching + cost tracking are uniform with commit0 and realworld.

## 8. File-writing conventions

- `pathlib.Path` everywhere — no `os.path.join`.
- Write with `encoding="utf-8", newline=""`. Windows CRLF corrupts bash scripts inside the Linux-container pytest harness (see `commit0/PROTOCOL.md §6.1`).
- Result JSON is indented 2 spaces, trailing newline.

## 9. References

- [ADR-0063](../../.architecture/decisions/ADR-0063-round-trip-fidelity-benchmark.md) — governing ADR
- [ADR-0060](../../.architecture/decisions/ADR-0060-commit0-greenfield-benchmark.md) — sister benchmark (Recompose-only)
- [ADR-0059](../../.architecture/decisions/ADR-0059-realworld-dr-benchmark.md) — sister benchmark (cross-stack D/R)
- [`PLAN.md`](./PLAN.md) — phased roadmap
- [`SESSION_PROMPT.md`](./SESSION_PROMPT.md) — session-starter for the scaffolding pass
