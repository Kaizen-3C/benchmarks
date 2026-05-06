# Campaign README — How to Reproduce This Benchmark Matrix

**Goal of this doc:** anyone with a fresh machine, an Anthropic API key, an OpenAI API key, and ~$200 of budget can re-run the entire 8-architecture × 16-library campaign and get numbers within sampling noise of ours.

**Total runtime budget:** ~$182 (measured this campaign), ~12–15 hours of wall time, ~3 days of attention.

## Quick links

| Document | Purpose |
|---|---|
| [`PROTOCOL.md`](PROTOCOL.md) | Per-architecture run procedure (mirrored across baselines) |
| [`PLAN_2026-04-21.md`](PLAN_2026-04-21.md) | Symmetric-coverage tiers + value-add framework |
| [`AAR_2026-04-21.md`](AAR_2026-04-21.md) | Mid-campaign post-mortem (after B2/B3/B6-partial) |
| [`AAR_2026-04-22_FINAL.md`](AAR_2026-04-22_FINAL.md) | Final findings + architectural fingerprint |
| [`baselines/value_add_fingerprint.py`](baselines/value_add_fingerprint.py) | Re-runnable analysis: value-add per cell, llm-lean ratio, weakness signatures |
| [ADR-0060](../../.architecture/decisions/ADR-0060-commit0-greenfield-benchmark.md) | Why we chose commit0; gate criteria |

## Pinned versions (do not deviate without a reason)

```
WSL2:                Ubuntu-24.04
Python:              3.12 (per-architecture .venv)
Docker Desktop:      29.x with Linux-container backend
commit0 CLI:         0.1.8                (pip install commit0==0.1.8)
HuggingFace dataset: wentingzhao/commit0_combined  rev 944c325cf7899ee75dcf3ec3c42a631a253c7737
Anthropic SDK:       per .venv requirements (matches Sonnet 4.6 API)
OpenHands SDK:       1.16.1                (pip install openhands-sdk==1.16.1 + companions)
OpenHands benchmarks: github.com/OpenHands/benchmarks @ HEAD with vendor submodule
Models:              claude-sonnet-4-6, gpt-5.4
```

If your numbers diverge significantly: check provider model strings (litellm slugs differ from raw API), Anthropic ephemeral-cache headers, OpenAI auto-cache TTL, and per-lib `--max-iterations` caps.

## One-time WSL setup

```bash
# Inside WSL2 Ubuntu-24.04
mkdir ~/kaizen-commit0 && cd ~/kaizen-commit0
python3.12 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip uv
pip install commit0==0.1.8 anthropic openai pypdf

# Clone commit0 lite split (16 libs)
commit0 setup lite

# Build per-lib Docker images (~40 sec, 16 images)
commit0 build --num-workers 4
```

For OpenHands V1 (a separate workspace):

```bash
mkdir ~/openhands-latest && cd ~/openhands-latest
python3.12 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip uv
git clone https://github.com/OpenHands/benchmarks.git
cd benchmarks
git submodule update --init --recursive --quiet  # pulls vendor/software-agent-sdk
uv sync                                          # creates benchmarks/.venv with all deps

# Install uv globally for the agent-server build (sets ~/.local/bin/uv)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

⚠️ **Windows host gotcha (documented in PROTOCOL.md §6.1):** commit0 0.1.8's local backend has 3 bugs on Windows-host paths. Run inside WSL2 only. The OpenHands SDK has a strict workspace-root check that requires patching one line in `openhands/agent_server/docker/build.py` (see `OH_SDK_PROJECT_ROOT` env-var workaround in `openhands_latest/SETUP.md`).

## Required environment

A `.env` file at the repo root with:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

All scripts source `.env` automatically.

## Campaign run order (matches the PLAN tiers)

### B2 single-shot baselines (do first; all other baselines reference these)

```bash
# Inside ~/kaizen-commit0, with .venv activated, .env sourced
python baselines/run_lite_single_shot.py 2>&1                              # B2-Sonnet
python baselines/run_lite_single_shot_openai.py 2>&1                       # B2-GPT-5.4
```

Expected: ~$10 combined, ~75 min wall, 16 result JSONs each in `baselines/results/`.

### B3 Reflexion baselines (3-iter cap, retry on failed pytest)

```bash
python baselines/run_lite_reflexion.py --max-iters 3 --sleep 30 2>&1       # B3-Sonnet
python baselines/run_lite_reflexion_openai.py --max-iters 3 --sleep 20 2>&1 # B3-GPT-5.4
```

Expected: ~$15 combined, ~120 min wall.

### KD Kaizen-delta baselines (per-file decompose + module-level grounding)

```bash
python baselines/run_lite_kaizen_delta.py --provider anthropic --sleep 10 2>&1  # KD-Sonnet
python baselines/run_lite_kaizen_delta.py --provider openai --sleep 10 2>&1     # KD-GPT-5.4
```

Expected: ~$32 combined, ~7.5 hr wall (chardet + babel are the slow libs at 35–93 min each).

### Aider baselines (Phase 1, added 2026-05-05)

```bash
pip install aider-chat pytest-cov
pip install --upgrade litellm

# One-time compat patch for aider 0.86.2 + litellm ≥1.81 (see baselines/aider/SETUP.md):
# Add ExInfo("PermissionDeniedError", False, "...") to EXCEPTIONS list in
# .venv/lib/python3.12/site-packages/aider/exceptions.py

python baselines/aider/run_lite_aider.py --provider anthropic 2>&1   # Aider-Sonnet
python baselines/aider/run_lite_aider.py --provider openai 2>&1      # Aider-GPT-5.4
```

Expected: ~$26 combined (this campaign: $16.80 + $9.63), Aider-Anthropic ~7 hr (auto-test loop iterates until pytest passes; marshmallow/voluptuous/babel exceed 30-min wall flag), Aider-OpenAI ~55 min.

### smolagents baselines (Phase 1, added 2026-05-05)

```bash
pip install smolagents

python baselines/smolagents/run_lite_smolagents.py --provider anthropic 2>&1   # Sm-Sonnet
python baselines/smolagents/run_lite_smolagents.py --provider openai 2>&1      # Sm-GPT-5.4
```

Expected: ~$39 combined ($29.25 + $9.44), 25 min + 71 min wall. Note: `minitorch` errors uniformly because smolagents' interpreter blocks `posixpath` (used internally by `os.walk`) even though `os` is in `AUTHORIZED_IMPORTS`. This is documented as a sandbox quirk, not a harness bug — the result is a legitimate diagnostic finding for the methodology paper.

### OH OpenHands V1 baselines (full run requires their hosted runtime; local-Docker is bandwidth-bound)

For local Docker runtime (what we used):

```bash
# Inside ~/openhands-latest, with the proper env from .env
./launch_oh_gpt_10missing.sh   # requires populating instances_oh_gpt_10missing.txt
./launch_b6.sh                 # see openhands_latest/ for full setup
```

⚠️ Use `--num-workers 4 --max-iterations 30` to stay within budget. The default `--num-workers 16` saturates outbound PyPI bandwidth and 13/16 instances time out (documented in AAR-1).

For each OH run, after completion run `eval_infer` to extract resolved/unresolved counts:

```bash
python -m benchmarks.commit0.eval_infer path/to/output.jsonl
```

Then archive the output dir to `results/b6_<run-name>/` for the value-add fingerprint to find.

## Analysis

After all baselines complete, run:

```bash
# Value-add fingerprint table (8 architectures × 16 libs)
py -3.12 benchmarks/commit0/baselines/value_add_fingerprint.py

# Per-baseline comparison aggregates
py -3.12 benchmarks/commit0/baselines/compare_baselines.py

# Cache effectiveness analysis with counterfactual
py -3.12 benchmarks/commit0/baselines/cache_analysis.py

# Per-lib us-vs-them table (the table from the campaign reports)
py -3.12 benchmarks/commit0/baselines/value_add_table.py
```

All four scripts read from `benchmarks/commit0/results/` and print to stdout. Each is self-contained; safe to re-run as new data lands.

## Expected aggregate numbers (within sampling noise)

Per the [final AAR](AAR_2026-04-22_FINAL.md):

| Architecture | Tests passed / attempted | Cost | Wall |
|---|---:|---:|---:|
| B2 single-shot Sonnet | 1,019 / 2,008 | $7.31 | 46 min |
| B2 single-shot GPT-5.4 | 767 / 1,925 | $2.88 | 31 min |
| B3 Reflexion Sonnet | 498 / 1,564 | $10.89 | 68 min |
| B3 Reflexion GPT-5.4 | 787 / 1,754 | $4.12 | 52 min |
| KD-Sonnet | 1,167 / 3,325¹ | $21.95 | 267 min |
| KD-GPT-5.4 | 969 / 1,583 | $10.57 | 194 min |
| OH-Sonnet (6 of 16 covered) | 1,025 / 1,028 | $94.31 | n/a |
| OH-GPT-5.4 (14 of 16 covered) | 11,177 / 11,193 | $30.38 | n/a |
| Aider-Sonnet | 493 / 506 | $16.80 | 439 min |
| Aider-GPT-5.4 | 385 / 398 | $9.63 | 55 min |
| smolagents-Sonnet | 639 / 650 | $29.25 | 25 min |
| smolagents-GPT-5.4 | 830 / 843 | $9.44 | 71 min |

¹ KD-Sonnet's denominator inflated by babel collection unlock (22 errors → 1,281 collected).

**Total: $247.53** ($182.41 original + $65.12 Phase 1).

## Result schema

Per-lib JSONs in `results/<lib>_<architecture>.json`:

```json
{
  "repo": "wcwidth",
  "model": "claude-sonnet-4-6",
  "branch": "kaizen_delta",
  "files_total": 6,
  "files_accepted": 5,
  "elapsed_s": 308.7,
  "final_summary": "============= 28 passed, 10 failed in 0.61s ==============",
  "final_counts": {"passed": 28, "failed": 10, "skipped": 0, "errors": 0},
  "totals": {
    "input_tokens": 31810,
    "output_tokens": 38051,
    "cache_read_tokens": 68716,
    "cache_write_tokens": 16253,
    "cost_usd": 0.74
  },
  "per_file": [...]
}
```

Aggregate JSONs in `results/aggregate_lite_<architecture>.json` follow the schema in `compare_baselines.py:load_b3()`.

OH partial result dirs in `results/b6_<run-name>/` contain three files:
- `output.jsonl` — per-instance conversation history + token usage
- `output.report.json` — schema: `{total_instances, completed_instances, resolved_instances, completed_ids, resolved_ids, ...}`
- `cost_report.jsonl` — total + per-instance cost breakdown

## Cost-monitor smoke test

⚠️ Before running any expensive sweep, run the smoke test (added after the $85 silent-failure incident in AAR-1):

```bash
py -3.12 benchmarks/commit0/baselines/openhands_latest/test_cost_monitor.py
```

It runs one tiny instance through the OH harness and asserts the cost monitor reads a non-zero cost from the field name we expect. **Run before any new sweep that uses the cost cap.**

## Known limitations

1. **OH-Sonnet on 6 of 16 libs** (vs OH-GPT-5.4 on 14 of 16) — Sonnet hit `--max-iterations 30` more often. To complete OH-Sonnet to full coverage, raise to `--max-iterations 100` and budget another ~$60–150.
2. **Per-test identity not tracked in KD** — KD's acceptance rule uses pass-COUNTS not IDENTITY, allowing destructive net-zero swaps on libs like pyjwt/simpy. Action item #2 in AAR-2.
3. **Test-import-aware Decompose missing** — KD has no visibility into test files, blocks 3 of 5 floor libs (voluptuous, marshmallow, jinja). Action item #1 in AAR-2.
4. **OH cache-control headers absent** — local-Docker OH costs 9.8× more than published. Action item #3 in AAR-2 proposes a litellm-proxy fix.

## How to extend

| To add | Files to create | Reuse |
|---|---|---|
| New architecture | `baselines/<arch_name>.py`, `baselines/run_lite_<arch_name>.py` | `_llm.py` (provider abstraction), `single_shot_sonnet.py` helpers |
| New provider | swap `--provider` flag | `_llm.LLMClient(provider, model)` already supports `anthropic` and `openai`; add new branch for new providers |
| New library set | new sweep `--only` lib list, or modify `LITE_ORDER` | full pipeline already lib-agnostic |
| New metric | `baselines/<metric>_analysis.py` | output schema is JSON-stable, easy to extend |

## Citation

If you use this benchmark methodology, please cite:

```
Kaizen-delta commit0-lite Architectural Weakness Campaign (2026-04).
8 baselines × 16 libraries × 2 providers. Value-add fingerprint methodology.
https://github.com/anthonyadame/kaizen-delta
```

The campaign data + scripts are MIT-licensed (see top-level LICENSE).
