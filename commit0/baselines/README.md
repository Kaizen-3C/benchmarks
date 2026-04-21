# commit0 baselines

This directory holds the runners for every commit0-lite baseline used in the Kaizen-delta evaluation, plus shared utilities. All scripts run inside the WSL workspace (`~/kaizen-commit0/`) per [PROTOCOL.md §2.1](../PROTOCOL.md). Results land in [`../results/`](../results/).

## What's here

| File | Purpose |
|---|---|
| `_llm.py` | **Provider-agnostic LLM client + pricing.** Use this from any new baseline. `LLMClient(provider, model)` with unified `.call(instructions, cached_block) -> (text, usage)`. Anthropic uses explicit `cache_control`; OpenAI auto-caches identical prefixes. |
| `single_shot_sonnet.py` / `single_shot_openai.py` | **B2** baselines. One LLM call per library; spec PDF text + all stub files in the prompt; parse fenced code blocks back. *(legacy fork pattern — predates `_llm.py`)* |
| `reflexion_sonnet.py` / `reflexion_openai.py` | **B3** baselines. Same shape as B2 but with up to 3 reflection iterations grounded by sanitized pytest output. *(also legacy fork pattern)* |
| `kaizen_delta.py` | **The Kaizen-delta runner.** Per-file decompose → recompose with module-level pytest grounding. Uses `_llm.py`. Provider via `--provider {anthropic,openai}`. |
| `run_lite_*.py` | Sweep wrappers. Loop over the 16 lite libs, write per-lib JSONs + an aggregate. |
| `cache_analysis.py` | Reports cache hit rate, $/test, $/resolved-instance, and counterfactual savings if missing prompt caching were added. |
| `compare_baselines.py` | Cross-baseline table: aggregate pass rates, costs, marginal-value deltas. Auto-discovers B2/B3 (both providers) and B6 partials. |
| `openhands_v1115/` | First B6 attempt — pinned to OpenHands SDK v1.11.5. **Failed** due to validator bug in v1.11.5's local-Docker code path. See [PROTOCOL.md §6.1](../PROTOCOL.md). |
| `openhands_latest/` | B6 reproduction with latest SDK (v1.16.1). Wrapper enforces a hard $/pass cost cap. **Run `test_cost_monitor.py` first** to verify the cap actually fires. |

## Adding a new baseline

1. Create `<name>_<provider>.py` (or better: parameterize via `--provider`, see kaizen_delta.py for the pattern).
2. Import the LLM client: `from _llm import LLMClient, cost, DEFAULT_MODELS`.
3. Reuse helpers from `single_shot_sonnet.py`: `extract_pdf_text`, `discover_stub_files`, `parse_response`, `write_files`, `git`, `run_pytest_via_commit0`, `TEST_DIR_OVERRIDES`. *(These predate `_llm.py`; refactor candidate.)*
4. Write per-lib JSON to `RESULTS_DIR / f"{lib}_<your_name>.json"` with these canonical fields:
   - `repo`, `model`, `branch`
   - `input_tokens`, `cached_input_tokens`, `output_tokens`, `elapsed_s`
   - `pytest_summary` (the canonical pytest final line) and `counts` (parsed dict with `passed`, `failed`, `skipped`, `errors`)
   - `files_written` or `iterations` if applicable
5. Add an aggregator step that re-parses each per-lib JSON's pytest output from on-disk `test_output.txt` (the authoritative source — *not* the runner's stdout, which interleaves docker noise). See any existing `run_lite_*.py` for the pattern.

## Canonical metrics schema

Every per-lib JSON should be loadable by `compare_baselines.py`. The shape:

```jsonc
{
  "repo": "wcwidth",
  "model": "claude-sonnet-4-6",
  "branch": "kaizen_delta",
  "input_tokens": 110808,
  "cached_input_tokens": 0,        // OpenAI auto-cache; 0 if absent
  "output_tokens": 3339,
  "elapsed_s": 49.0,
  "pytest_summary": "9 failed, 29 passed, 1 skipped in 0.61s",
  "counts": {"passed": 29, "failed": 9, "skipped": 1, "errors": 0},
  "files_written": ["wcwidth/wcwidth.py"]
}
```

Aggregate JSON:

```jsonc
{
  "model": "claude-sonnet-4-6",
  "split": "lite",
  "completed": ["wcwidth", "deprecated", ...],
  "per_library": { "wcwidth": {...}, ... },
  "aggregate": {
    "libraries_total": 16,
    "tests_passed": 1019,
    "tests_failed": 891,
    "tests_skipped": 12,
    "tests_errored": 98,
    "tests_attempted_total": 2008,
    "pass_rate_attempted": 0.5075,
    "input_tokens_total": 1385608,
    "output_tokens_total": 209924,
    "wall_seconds_total": 2771.1,
    "cost_usd_estimate": 7.31         // PROVIDER-CORRECT pricing
  }
}
```

## Hard-won operational rules

These are encoded in the AAR ([`../AAR_2026-04-21.md`](../AAR_2026-04-21.md)) and worth surfacing here:

1. **Test the cost monitor before you trust it.** Run `openhands_latest/test_cost_monitor.py` before any expensive sweep. The $85 incident was a single field-name mismatch (`total_cost` vs `accumulated_cost`) that fired never.

2. **Re-parse pytest summaries from on-disk `test_output.txt`.** Subprocess stdout interleaves docker setup logs, httpx requests, and pytest output. The `commit0/logs/pytest/<repo>/<branch>/<runid>/test_output.txt` file is authoritative.

3. **Don't run B6 (OpenHands V1) at `--num-workers 16`.** 16 parallel `pip install commit0` saturates outbound bandwidth → 13/16 timeouts. Use `--num-workers 4` (or 3 for safety) on local Docker.

4. **For Sonnet, use prompt caching aggressively.** B3 Sonnet without caching would have cost ~$60 instead of $11. See `_llm.py` — the `LLMClient.call(instructions, cached_block)` signature exists exactly to make this easy.

5. **For OpenAI, structure prompts so the static block is at message[0].** Auto-cache matches identical prefixes. Putting the spec at the start of one big user message gets ~55–80% hit rates without any explicit cache annotations.

## Sweeps that exist as ready-to-run

| Wrapper | Cost (est) | Wall (est) |
|---|---|---|
| `run_lite_single_shot.py` | $7 | 30 min |
| `run_lite_single_shot_openai.py` | $3 | 30 min |
| `run_lite_reflexion.py` | $11 | 60 min |
| `run_lite_reflexion_openai.py` | $4 | 50 min |

Kaizen-delta sweep wrapper not yet written — `kaizen_delta.py` runs one library at a time. Sweep wrapper is the next addition.

## Running

From the WSL workspace, with `.env` sourced:

```bash
cd ~/kaizen-commit0
. .venv/bin/activate
set -a && . /mnt/c/RepoEx/Kaizen-delta/.env && set +a
python baselines/<wrapper>.py [--only <lib>] [--skip <lib> ...] [--max-iters N]
```

For OpenHands V1 (different workspace):

```bash
cd ~/openhands-latest
./launch_b6.sh        # full sweep, $50 cost cap per pass
```
