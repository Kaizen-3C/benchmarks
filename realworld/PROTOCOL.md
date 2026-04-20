# RealWorld Rails → FastAPI — Evaluation Protocol

**Governed by:** [ADR-0059](../../.architecture/decisions/ADR-0059-realworld-dr-benchmark.md)
**Pilot target:** first CD-AOR decompose/recompose pilot on a real, non-toy codebase
**Size:** ~2000 LOC Rails source → ~1500-2500 LOC FastAPI target, ~90 Postman API tests
**Projected cost:** $100-300 for a full pilot (iterative, 1-2 weeks)

This document is the **operational specification** for running the RealWorld benchmark under Kaizen-delta. It is intended to be detailed enough that another engineer could execute the benchmark end-to-end without further context.

---

## 1. Corpus

### 1.1 Source implementation (frozen)

- **Repository:** `https://github.com/gothinkster/rails-realworld-example-app`
- **Git SHA:** pin once the pilot begins; record here and in every result JSON
- **Ruby version:** 3.2+ (check repo for pin)
- **Database:** PostgreSQL 14+ (matching repo's docker-compose)

### 1.2 Target stack (fixed)

- **Language:** Python 3.12
- **Framework:** FastAPI (latest stable, pin at pilot start)
- **ORM:** SQLAlchemy 2.x with asyncio
- **Auth:** JWT via `python-jose[cryptography]`
- **Packaging:** `uv` (modern Python packaging)
- **Testing:** `pytest` + the RealWorld Postman collection (via Newman CLI)

### 1.3 Oracle (fixed)

- **Primary:** [RealWorld Postman collection](https://github.com/gothinkster/realworld/blob/main/api/Conduit.postman_collection.json), executed via Newman
- **Secondary:** [OpenAPI spec](https://github.com/gothinkster/realworld/blob/main/api/openapi.yml) for contract validation (every response must validate against the schema)

### 1.4 Human-reference upper bound

- **Repository:** `https://github.com/nsidnev/fastapi-realworld-example-app`
- **Role:** Establishes what a hand-written FastAPI-RealWorld looks like. Used as a *ceiling* reference, NEVER as a model input. CD-AOR must not see this code.

---

## 2. Protocol

### 2.1 Phase 0 — Reference validation (once, before any CD-AOR runs)

Goal: confirm the oracle is trustworthy by running it against the canonical reference implementations.

| Step | Command | Expected |
|---|---|---|
| 1 | `docker-compose up -d` (in rails source repo at pinned SHA) | Rails server listening on :3000 |
| 2 | `newman run Conduit.postman_collection.json --env-var "APIURL=http://localhost:3000/api"` | **≥95% pass rate** (small flakiness on timing-sensitive tests is acceptable) |
| 3 | Same for `nsidnev/fastapi-realworld-example-app` | **≥95% pass rate** |
| 4 | Record both pass rates in `results/phase0_reference_validation.json` |

If either reference fails step 2/3, stop and debug the oracle. Do NOT proceed to decompose/recompose until the oracle is stable.

### 2.2 Phase 1 — Decompose the Rails source

Goal: produce a target-stack-agnostic spec from the Rails source code.

**Inputs:**
- `rails-source/` at pinned SHA
- `decompose/` pipeline from `kaizen-delta`

**Outputs (in `spec/`):**
```
spec/
  manifest.json             # run metadata, source SHA, decomposer version
  graph.json                # decomposition graph (see shared/schemas/)
  adrs/
    ADR-0001-jwt-auth.md       # inferred from Rails config/initializers
    ADR-0002-activerecord-orm.md
    ADR-0003-rest-api-versioning.md
    ...
  contracts/
    users.yaml                 # extracted from user routes + model
    articles.yaml
    comments.yaml
    profiles.yaml
    tags.yaml
    favorites.yaml
  oracles/
    tests.jsonl                # each row: {endpoint, method, expected_status, schema_ref}
    postman_collection.json    # preserved verbatim
    openapi.yml                # preserved verbatim
  gaps.json                    # things Decompose couldn't extract
```

**Success criterion for Phase 1:**
- `spec/` validates against `shared/schemas/`
- Every Rails route (rake routes output) appears in `oracles/tests.jsonl`
- `gaps.json` has ≤ 20 entries

### 2.3 Phase 2 — Recompose into FastAPI

Goal: produce a runnable FastAPI application that satisfies `spec/`.

**Inputs:**
- `spec/` from Phase 1
- `target.yaml`:
  ```yaml
  target:
    language: python-3.12
    framework: fastapi
    orm: sqlalchemy-async
    auth: python-jose-jwt
    packaging: uv
    http_server: uvicorn
    database: postgresql-14
  direct_synthesis_max_lines: 60
  ```

**Outputs (in `out/`):**
```
out/
  pyproject.toml             # uv-managed, locked dependencies
  alembic.ini                # database migration config
  alembic/
    versions/                # generated migrations from contracts
  app/
    __init__.py
    main.py                  # FastAPI app factory
    core/
      config.py              # env-based settings (JWT secret, DB URL)
      security.py            # JWT encode/decode
    db/
      base.py                # SQLAlchemy async engine
      session.py             # request-scoped session dependency
    models/
      user.py
      article.py
      comment.py
      tag.py
    schemas/                 # Pydantic request/response shapes
      user.py
      article.py
      ...
    routers/                 # FastAPI APIRouter per resource
      users.py
      articles.py
      comments.py
      profiles.py
      tags.py
    crud/                    # data-access functions
      users.py
      articles.py
      ...
  Dockerfile
  docker-compose.yml         # fastapi + postgres
  recompose_report.json      # per-module: ADR-0002-short-circuit vs LLM generator; oracle coverage
```

**Two-tier strategy per ADR-0002:**

For each `spec/contracts/<module>.yaml`:
- Test if the contract shape matches a registered recipe's `translatable_shapes`
  - If match + prior-pass-rate gate clears + output size estimate OK: use `recompose.src.short_circuit.short_circuit_or_defer()` to emit directly
  - Otherwise: defer to the generator agent pipeline
- `recompose_report.json` records which path each module took

### 2.4 Phase 3 — Score against the oracle

**Steps:**

1. `cd out/ && docker-compose up -d`
2. Wait for readiness: health check on `GET /api/health` returning 200 within 60 seconds, or fail with `BUILD_FAILED` result
3. `newman run spec/oracles/postman_collection.json --env-var "APIURL=http://localhost:8000/api" --reporters json --reporter-json-export results/newman.json`
4. Parse `results/newman.json` → count passed / failed / errored per category
5. Optional: run OpenAPI contract validation on responses (`spec/oracles/openapi.yml` vs actual response shapes) for schema-compliance score
6. `docker-compose down`

**Result artifact (`results/realworld_rails_to_fastapi_<timestamp>.json`):**
```json
{
  "source_sha": "...",
  "target_stack": "...",
  "timestamp": "...",
  "build_status": "passed | partial | failed",
  "newman_summary": {
    "total": 90,
    "passed": 73,
    "failed": 14,
    "errored": 3
  },
  "per_category": {
    "auth":       {"total": 10, "passed": 10},
    "articles":   {"total": 32, "passed": 28},
    "comments":   {"total": 12, "passed": 10},
    "profiles":   {"total":  8, "passed":  7},
    "tags":       {"total":  4, "passed":  4},
    "favorites":  {"total":  8, "passed":  6},
    "misc":       {"total": 16, "passed":  8}
  },
  "contract_validation": {
    "total_responses": 73,
    "schema_compliant": 68,
    "compliance_rate": 0.932
  },
  "recompose_report_summary": {
    "modules_total": 12,
    "short_circuit_adopted": 4,
    "generator_adopted": 7,
    "failed": 1
  },
  "cost_usd": 47.83,
  "wall_clock_seconds": 2840,
  "llm_call_count": 147
}
```

---

## 3. Baselines

Every CD-AOR result is reported alongside at least the first three baselines.

### 3.1 B1: Human-reference upper bound

- **What:** `nsidnev/fastapi-realworld-example-app`
- **How:** `docker-compose up` + Postman run
- **Purpose:** "What's achievable with unlimited engineering effort." Expected ≥95% pass rate; treated as the ceiling.

### 3.2 B2: Single-shot Claude (Sonnet 4.6)

- **What:** feed the entire Rails source tree (concatenated with `files2prompt` or similar) plus the OpenAPI spec into one Sonnet call, ask for a complete FastAPI implementation.
- **Expected failure mode:** context window overflow; if not, the single-shot output typically lacks scaffolding (migrations, Dockerfile, settings.py).
- **Purpose:** establishes whether D/R benefits from the decomposition step at all.

### 3.3 B3: Reflexion-style adapted

- **What:** apply our `--reflexion-style` mode to the whole-app task. Reflection requires executable tests; since target stack tests don't yet exist, we seed iteration 1 with an empty FastAPI scaffold + the OpenAPI spec + the full Rails source, then iterate.
- **Expected failure mode:** Reflexion's reflection-on-prior-code loop assumes the app is small enough to regenerate wholesale per iteration. For a 2000-LOC app, it will likely fail on context limits or produce regressions.
- **Purpose:** establishes whether "simple iteration wins" (as it did on HumanEval/MBPP) extends to app-level D/R. If yes, CD-AOR's architecture is redundant; if no, CD-AOR's structural decomposition is load-bearing.

### 3.4 B4: CD-AOR without ADR-0002 short-circuit

- **What:** disable the high-confidence bypass; route every artifact through the full 5-agent pipeline.
- **Purpose:** measures the marginal value of the test-aware adoption path introduced in ADR-0002.

### 3.5 B5: CD-AOR with ADR-0002 short-circuit (primary)

- **What:** full Kaizen-delta pipeline as designed.
- **Purpose:** the headline configuration.

---

## 4. Iteration budget

Realistic timeline for a first pilot:

| Week | Activity | Deliverable |
|---|---|---|
| 1 day | Phase 0 reference validation | `phase0_reference_validation.json`; both references pass ≥95% |
| 2-3 days | Implement Decompose for Rails (ADR extraction, contract distillation, oracle translation) | `decompose/src/` extended with Rails-specific extractors |
| 2-3 days | Implement Recompose recipes: `flask_to_fastapi` (existing) plus new `rails_to_fastapi` | `recompose/src/recipes/rails_to_fastapi.py` |
| 1 day | End-to-end dry run; fix crashes, not quality | one runnable FastAPI output, any pass rate |
| 3-5 days | Iterate on decompose granularity + recipe fidelity until pass rate ≥50% | `results/dry_run_*.json` showing progress |
| 2 days | Run all 5 baselines; collect numbers | `results/baselines_*.json` |
| 2 days | Paper section writeup + figure generation | new §5.9 in `cdaor-benchmarks/paper/cdaor.md` |

**Total:** ~2 weeks at 1 engineer full-time, or ~3-4 weeks part-time.

**Cost budget:** $100-300 primarily on iteration, plus ~$30-50 for Opus-4.6 runs if we include a tier-amplified variant.

---

## 5. Success criteria for paper-worthy result

### Minimum viable result

- CD-AOR (with short-circuit) produces a runnable FastAPI app
- Oracle pass rate ≥50% (45+ of 90 Postman tests pass)
- At least one full endpoint category at 100% (e.g., auth or tags)
- Written as a positive result: "Decompose/Recompose is feasible; here are the cases where it works"

### Strong result

- Oracle pass rate ≥80% (72+ of 90)
- CD-AOR with short-circuit outperforms Reflexion-adapted by ≥20 pp (Reflexion struggles on app-level D/R)
- Short-circuit fires on ≥30% of artifacts with 100% oracle pass rate on those artifacts
- Written as: "CD-AOR's test-aware bypass is load-bearing for D/R; architecture matters here even though it didn't on HumanEval/MBPP"

### Paper-redefining result

- Oracle pass rate ≥90%
- Shorter time-to-runnable than a manual porting effort (publishable productivity claim)
- Generalizes to a second pair (e.g., Rails → Flask) without retuning recipes
- Written as: "CD-AOR is a general D/R framework; RealWorld is the first of N demonstrations"

---

## 6. Threats to validity

| Threat | Mitigation |
|---|---|
| Model training-data contamination — Sonnet may have seen RealWorld during pretraining, directly writing the FastAPI answer rather than going through Decompose/Recompose | Compare with cross-provider (Opus, GPT-5.4, Ollama) — if all succeed at similar rates, contamination is less likely; if Claude-only succeeds, flag it |
| Prompt leakage between Decompose and Recompose — the spec may over-encode Rails-specific details | Recipe unit tests: generate spec from Rails, compare generated FastAPI to spec's stated contracts (not Rails source) |
| Oracle drift — the Postman collection may pass on Rails but fail on FastAPI for legitimate reasons (error message formats, etc.) | Run both reference implementations against the oracle (Phase 0); treat Rails reference pass rate as the real ceiling, not 100% |
| Recipe overfitting to RealWorld | The recipe (`rails_to_fastapi`) should not have RealWorld-specific logic; test on a second Rails app (e.g., a small sample like `mastodon-api`) to confirm generalization |
| Short-circuit false positives — ADR-0002's gate may fire incorrectly on modules where the recipe's output doesn't actually satisfy tests | Monitor `recompose_report.json` short-circuit adoption rate vs per-artifact oracle pass rate; a gap indicates calibration problems |

---

## 7. File structure proposed for implementation

```
Kaizen-delta/
  benchmarks/realworld/
    PROTOCOL.md                      # this file
    docker/
      rails/Dockerfile.source         # pinned Rails reference
      fastapi/Dockerfile.target       # evaluation runner for generated output
    scripts/
      run_realworld_rails_to_fastapi.sh    # the full-pipeline one-liner
      phase0_validate_references.sh        # oracle sanity check
      score_newman.py                      # parses newman JSON → our result schema
    recipes/                          # CD-AOR-specific
      # (symlink to recompose/src/recipes/rails_to_fastapi.py)
    results/
      phase0_reference_validation.json
      realworld_*.json                # one per CD-AOR run
  recompose/src/recipes/
    rails_to_fastapi.py               # new recipe implementation
  decompose/src/extractors/
    rails_adrs.py                     # new Rails-specific ADR miner
    rails_contracts.py                # new Rails-specific contract distiller
```

---

## 8. Specific first deliverables (pre-pilot spike)

A 2-day spike before the full pilot commits is worth doing to confirm feasibility:

1. **Day 1:** Phase 0 reference validation — spin up both Rails and FastAPI references, confirm oracle works.
2. **Day 2:** Decompose skeleton — run existing `kaizen-delta/decompose/` on the Rails source with placeholder extractors, confirm `spec/` structure is sound.

If either spike fails (oracle flaky, or Decompose can't handle Rails at all), stop and reassess. If both succeed, commit the full 2-week pilot.

---

## 9. Open questions (to resolve during pilot)

- Should Decompose output the Postman collection verbatim, or synthesize per-endpoint test assertions from it? The former is simpler; the latter lets the Recomposer use the assertions as the test-aware evidence in ADR-0002's short-circuit path.
- Should the Recomposer generate Alembic migrations from the `contracts/*.yaml` directly, or use `sqlalchemy-utils` create_all as a dev-shortcut? Real-world deployments need migrations; dev-shortcut is faster for the pilot.
- Where does session/request-scoped DB isolation for Postman tests happen? The Rails reference uses transactional DB fixtures; FastAPI typically uses per-test transactions with rollback. Our Recomposer may need a recipe hint.

These are not blocking; each can be resolved during the pilot with a short follow-up ADR if the decision affects the architecture.

---

## 10. Why this is the right first D/R benchmark

Reviewing against the kaizen-delta ADR-0001 charter criteria:

- **Re-design over fork:** ✅ We're NOT forking the FastAPI reference; we generate from spec.
- **Test-oracle-driven:** ✅ The Postman collection is the ground-truth oracle.
- **Stack pairs, not one-shots:** ✅ Rails → FastAPI is the named pair; the recipe is versioned.
- **Fail loudly on lossy extraction:** ✅ `spec/gaps.json` enumerates what the Decomposer couldn't capture.

If this pilot succeeds, it establishes the D/R methodology. If it fails, we learn precisely where — and the failure mode itself is publishable.
