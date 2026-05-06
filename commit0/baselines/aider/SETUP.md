# Aider harness — setup notes

**Goal:** integrate Aider (https://aider.chat) into the commit0-lite baseline matrix, paired across Anthropic Sonnet 4.6 and OpenAI GPT-5.4. Per [`benchmarks/paper/PHASE1_COST_REVIEW.md`](../../../paper/PHASE1_COST_REVIEW.md), budget ~$25–45 + ~1.5 days engineering.

## One-time setup

Inside the WSL2 workspace where commit0 already runs (`~/kaizen-commit0/`):

```bash
. .venv/bin/activate
pip install aider-chat              # Aider CLI + Python API
pip install --upgrade litellm        # provider abstraction Aider uses
aider --version                      # smoke test
```

## Why Aider on commit0-lite is feasible

- **Repo-aware by design.** Aider takes `--cwd <repo>` and respects `.aider.conf.yml`. commit0 starter repos already have a clean Python package layout.
- **Test-driven mode.** `aider --auto-test --test-cmd "pytest"` runs the test suite after each edit and feeds failures back to the model. This is exactly the loop we want to evaluate.
- **Native Anthropic prompt caching.** Aider sets `cache-control: ephemeral` on the conversation prefix when `--cache-prompts` is enabled. Cost should fall in the $25–45 range across both providers.
- **JSON cost reporting.** `aider --message-file <prompt> --yes --no-stream --report-file <out.json>` writes a machine-readable summary including per-call token + cost.

## Invocation pattern (per library)

```bash
aider \
  --model anthropic/claude-sonnet-4-6 \
  --cwd "$LIB_REPO" \
  --read tests/  --read spec.md \
  --auto-test --test-cmd "pytest -x" \
  --cache-prompts \
  --no-stream --yes \
  --message "Implement all stubs in this repo so the tests pass. Return only the edits needed."
```

For OpenAI GPT-5.4: `--model openai/gpt-5.4`.

## Resolved (2026-04-25, before engineering)

The four open questions in the original draft are now resolved in `_aider_runner.py`. Summary:

| # | Question | Resolution |
|---|---|---|
| 1 | Iteration cap | `MAX_WALL_S = 30 * 60` (30 min wall-clock); `MAX_INPUT_TOKENS = 200_000`. Aider stops on its own when tests pass or context exhausts; the wall-clock cap is a guard against runaway iteration. |
| 2 | Cost cap | `MAX_COST_USD = 5.00` checked after `coder.run()` returns. Aborts the cell with a `cost_capped: true` flag in the result JSON. (Per-call interruption isn't cleanly supported by the Aider Python API; we cap post-hoc.) |
| 3 | spec.md injection | `_materialize_spec_md()` decompresses `spec.pdf.bz2`, extracts text via the existing `pypdf` helper from `single_shot_sonnet.py`, writes `spec.md` into the repo root. The file then enters Aider via `read_only_fnames`. Cache-stable; readable by both providers. |
| 4 | Test command | `DEFAULT_TEST_CMD = "pytest -x --tb=no -q"`. Per-lib overrides via `PER_LIB_TEST_CMD` dict (currently empty — populate on Day 14 if any library needs a custom invocation). Run `commit0 test <lib>` once before Day 14 to confirm the canonical pytest command per library. |

## Files in this directory

| File | Status |
|---|---|
| `_aider_runner.py` | **Implemented.** Shared harness — invokes Aider, captures cost/tokens/pass-rate, writes per-lib JSON. |
| `aider_sonnet.py` | **Promoted 2026-05-05** (was `.SKELETON.py`). Anthropic single-cell wrapper. |
| `aider_openai.py` | **Promoted 2026-05-05.** OpenAI single-cell wrapper. |
| `run_lite_aider.py` | **Promoted 2026-05-05.** 16-lib sweep with `--provider` flag; mirrors `../run_lite_single_shot.py`. |

`py_compile` clean on Windows side 2026-05-05. WSL-side smoke test (Day 14 verification checklist below) still required before launching the full sweep.

## Smoke test results — 2026-05-05 (Day 13, ahead of schedule)

`python baselines/aider/aider_sonnet.py wcwidth` (Sonnet 4.6):

| Metric | Value |
|---|---:|
| passed / attempted | 20 / 21 |
| elapsed | 140.6 s |
| input_tokens | 356,504 |
| output_tokens | 7,784 |
| cost | $1.19 |
| reflections | 3/3 (capped) |

**Fixes applied during smoke test (record for reproducibility):**

1. **Aider 0.86.2 + litellm 1.81 compat patch.** Aider's `LiteLLMExceptions._load()` (in `.venv/lib/python3.12/site-packages/aider/exceptions.py`) raises `ValueError: PermissionDeniedError is in litellm but not in aider's exceptions list`. litellm 1.81 added `PermissionDeniedError` which aider 0.86.2 doesn't know about. One-line patch:
   ```python
   # add to EXCEPTIONS list in aider/exceptions.py, after NotFoundError:
   ExInfo("PermissionDeniedError", False,
          "The API provider denied the request — check API key permissions or model access."),
   ```
   Track upstream; remove patch when aider releases a fix.

2. **`pytest-cov` required.** Several commit0-lite libraries (wcwidth, voluptuous, others) have `--cov` flags in their pytest config. Install once: `pip install pytest-cov`.

## Day 14 verification checklist

Before launching the full sweep, confirm:

1. `pip install aider-chat==<pinned-version>` succeeds in the workspace `.venv`
2. `python -c "from aider.coders import Coder; from aider.models import Model; from aider.io import InputOutput"` succeeds
3. `python baselines/aider/aider_sonnet.py wcwidth` produces a result JSON with non-zero `cost_usd` and a populated `final_counts`
4. The wcwidth result JSON loads cleanly into `value_add_fingerprint.py` — confirm by running the fingerprint script and seeing an `Aider-S` cell appear
5. Cross-check Aider's reported cost against the per-call litellm cost (sanity check on `coder.total_cost`)
6. If any of the above fails, fix in the skeleton; do not launch the full 16-lib sweep until 3–5 are clean
