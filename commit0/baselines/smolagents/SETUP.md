# smolagents harness — setup notes

**Goal:** integrate HuggingFace smolagents (https://github.com/huggingface/smolagents) into the commit0-lite baseline matrix, paired across Anthropic Sonnet 4.6 and OpenAI GPT-5.4. Per [`benchmarks/paper/PHASE1_COST_REVIEW.md`](../../../paper/PHASE1_COST_REVIEW.md), budget ~$30–60 + ~2 days engineering.

## One-time setup

Inside the WSL2 workspace where commit0 already runs (`~/kaizen-commit0/`):

```bash
. .venv/bin/activate
pip install smolagents litellm
python -c "from smolagents import CodeAgent; print('ok')"  # smoke test
```

## Architectural notes

- **CodeAct-style.** smolagents writes Python code as actions and executes in a sandbox. Different paradigm from Aider's edit-blocks.
- **No native Anthropic prompt cache.** Per [`AAR_2026-04-22_FINAL.md`](../../AAR_2026-04-22_FINAL.md) action item #3, would require litellm-proxy injection. **Decision for Phase 1: run without cache injection.** Document the cost overhead transparently — the 0%-cache cell is itself diagnostic.
- **Sandbox conflict with commit0 Docker.** smolagents runs Python actions in an executor sandbox. commit0 also runs each library in a Docker container. To avoid Docker-in-Docker:
  - Run smolagents **outside** commit0 Docker, in the WSL workspace
  - Capture the resulting file diffs from smolagents' workspace
  - Hand the diffs to `commit0 test <lib>` for grading inside commit0 Docker

## Invocation pattern (per library)

```python
from smolagents import CodeAgent, LiteLLMModel
from pathlib import Path

model = LiteLLMModel(model_id="anthropic/claude-sonnet-4-6")
agent = CodeAgent(
    tools=[],                                # commit0 task is file-edit, not web/search
    model=model,
    additional_authorized_imports=["pathlib", "os", "subprocess"],
    max_iterations=20,                       # tighter than OH's 30
)

prompt = (
    f"You are implementing the {lib_name} library from a specification. "
    f"Read spec.md and the test files. Edit the stub Python files in this repo "
    f"so all tests pass. The repo root is {repo_dir}. "
    f"Use only Python built-in tools and file I/O — no external packages."
)
agent.run(prompt)
```

Cost + token tracking from `agent.token_counts` (after `agent.run` returns).

## Resolved (2026-04-25, before engineering)

| # | Question | Resolution |
|---|---|---|
| 1 | Iteration cap | `MAX_STEPS = 20` (between B3's 3 and OH's 30). If pass-rate is poor on Day 23 sample runs, retry with 30 in a follow-up sweep. |
| 2 | Cost cap | `MAX_COST_USD = 5.00` checked post-hoc; `cost_capped` flag in result JSON. smolagents has no per-step interrupt hook — the cap is documentary, not enforced mid-run. |
| 3 | Sandbox | `executor_type="local"` (NOT docker — avoids Docker-in-Docker conflict with commit0). `additional_authorized_imports` whitelisted to `pathlib, os, subprocess, json, re, ast, io, sys, math, typing, collections, itertools, functools` — enough to edit files and run pytest, not enough to phone home. |
| 4 | Diff handoff | Resolved by running smolagents in-place on the commit0 starter repo. The agent's edits ARE the deliverable; the final pytest run inside `_final_pytest()` is the authoritative scoring. |
| 5 | Cost tracking | smolagents does NOT expose cost in its API. We register `litellm.success_callback = [tracker.callback]` and capture per-call cost from `litellm.completion_cost(completion_response)`. The `_CostTracker` class in `_smolagents_runner.py` is the closure-bound accumulator. Cross-check: if `tracker.calls == 0` after `agent.run`, the callback didn't fire — debug litellm version. |

## Files in this directory

| File | Status |
|---|---|
| `_smolagents_runner.py` | **Implemented.** CodeAgent + LiteLLMModel + cost-tracking callback. |
| `smolagents_sonnet.py` | **Promoted 2026-05-05** (was `.SKELETON.py`). Anthropic single-cell wrapper. |
| `smolagents_openai.py` | **Promoted 2026-05-05.** OpenAI single-cell wrapper. |
| `run_lite_smolagents.py` | **Promoted 2026-05-05.** 16-lib sweep with `--provider` flag. |

`py_compile` clean on Windows side 2026-05-05. WSL-side smoke test (Day 22 verification checklist below) still required before launching the full sweep.

## Smoke test results — 2026-05-05 (Day 13, ahead of schedule)

`python baselines/smolagents/smolagents_sonnet.py wcwidth` (Sonnet 4.6) on smolagents 1.24.0:

| Metric | Value |
|---|---:|
| passed / attempted | 39 / 39 |
| elapsed | 34.0 s |
| llm_calls | 11 |
| input_tokens | 226,675 |
| output_tokens | 1,064 |
| cost | $0.70 |
| callback_errors | 0 |

**Fixes applied during smoke test (record for reproducibility):**

1. **`verbose` → `verbosity_level`.** smolagents ≥1.20 renamed the `CodeAgent.__init__` kwarg. `_smolagents_runner.py` updated.

2. **Cost callback object-vs-dict handling.** litellm 1.81 returns Pydantic-style `PromptTokensDetailsWrapper` for `usage` and `prompt_tokens_details`; older releases returned plain dicts. The original `usage.get(...)` failed on every call. `_smolagents_runner.py` `_CostTracker.callback` now uses a `_get(obj, key, default)` helper that handles both shapes via `getattr` fallback. Token totals were captured even before the fix; cost was not.

3. **First-run variance note.** Initial post-fix run hit `max_steps=20` because the agent attempted `from wcwidth.table_vs16 import ...` (the lib being implemented isn't in `AUTHORIZED_IMPORTS`). It recovered without the import. Second run completed in 11 calls. **Don't whitelist the target package** — blocking self-imports is correct; the agent should write the file, not import-test it.

## Day 22 verification checklist

Before launching the full sweep, confirm:

1. `pip install smolagents litellm` succeeds in the workspace `.venv`
2. `python -c "from smolagents import CodeAgent, LiteLLMModel"` succeeds
3. `python baselines/smolagents/smolagents_sonnet.py wcwidth` produces a result JSON
4. The wcwidth result has `smolagents_diagnostics.llm_calls > 0` (callback fired)
5. The wcwidth result has `totals.cost_usd > 0` (litellm computed cost)
6. The wcwidth result loads into `value_add_fingerprint.py` and shows a `Sm-S` cell
7. If `llm_calls == 0`, debug: `litellm.success_callback` may need to be set as `litellm.callbacks = [...]` in newer litellm versions — check the pinned version's docs

## Hard-ceiling rule

Per [`PHASE1_COST_REVIEW.md`](../../../paper/PHASE1_COST_REVIEW.md) §4: if Day 24 (2026-05-17) arrives and the Aider harness isn't producing clean per-library JSONs, **drop smolagents entirely** and ship draft v1 with 3 architectures. Do not let smolagents block Aider from landing.
