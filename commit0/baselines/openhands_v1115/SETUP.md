# OpenHands V1 (v1.11.5) — B6 Baseline Setup

This directory holds the pinned-version reproduction of OpenHands' published Sonnet 4.6 commit0-lite result (**7/16 instances solved, $1.88/lib avg, 578 s/lib**), plus the cost-capped wrapper for running it ourselves.

## Why pin v1.11.5

OpenHands published their Sonnet 4.6 number using **agent-SDK v1.11.5** (released 2026-02-20, submitted 2026-02-24). The current SDK is v1.17+. Newer SDK = different prompts/tools/scaffolding = different score. Pinning v1.11.5 lets us claim "exact reproduction" rather than "approximate". After the reproduction lands, we can also run latest if interesting.

## Versions to install (inside a fresh WSL venv)

```bash
# Inside ~/openhands-v1115/ on WSL ext4
python3.12 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip uv

# Pin the OpenHands SDK + companions to v1.11.5 era
pip install \
  openhands-sdk==1.11.5 \
  openhands-tools==1.11.5 \
  openhands-agent-server==1.11.5 \
  openhands-workspace==1.11.5

# Clone benchmarks repo at the v1.11.5-era commit (2026-02-24, same day as Sonnet 4.6 submission)
git clone https://github.com/OpenHands/benchmarks.git
cd benchmarks
git checkout 62477b41
pip install -e .

# Verify versions
pip show openhands-sdk | grep Version
git -C . log -1 --pretty=%H

# Should show:
#   Version: 1.11.5
#   62477b41 ...
```

## Required env

```
ANTHROPIC_API_KEY     (from /mnt/c/RepoEx/Kaizen-delta/.env)
```

## Pinned config

| Pin | Value |
|---|---|
| openhands-sdk | `1.11.5` |
| openhands-tools | `1.11.5` |
| openhands-agent-server | `1.11.5` |
| openhands-workspace | `1.11.5` |
| OpenHands/benchmarks | commit `62477b41` (2026-02-24) |
| commit0 dataset | `wentingzhao/commit0_combined` rev `944c325cf7899ee75dcf3ec3c42a631a253c7737` (we already pinned this) |
| Model | `litellm_proxy/anthropic/claude-sonnet-4-6` |
| Temperature | 0.0 (deterministic-ish; reduces run-to-run noise) |
| max-iterations | 100 (matches their published config) |
| n_critic_runs | 1 (commit0 default per `benchmarks/commit0/config.py`) |
| Repo split | `lite` (16 libs) |
| Workers | `--num-workers 16` (matches their parallel config) |

## How the wrapper works

`run_openhands_lite.py` (sibling file) wraps the upstream `commit0-infer` runner with three additions:

1. **Hard total-spend cap** ($50 default). A sidecar thread reads the live `output.jsonl` every 60 s and aggregates per-instance cost. If total exceeds the cap, the wrapper sends SIGTERM to the runner subprocess.
2. **2-pass mode.** Each pass writes to its own output dir (`pass1/`, `pass2/`). Two passes lets us measure run-to-run variance — Sonnet at temperature=0 is *more* deterministic but not perfectly so, and OpenHands tool-use loops introduce additional non-determinism.
3. **Pinned-version verification.** Runs `pip show openhands-sdk` and benchmarks SHA at the start and aborts if either drifted.

## Cost expectation

- OpenHands published cost = $1.88/lib avg, 578 s/lib avg.
- 16 libs × $1.88 = **$30/pass**.
- 2 passes = **$60 total** (under the $50/pass hard cap).
- Wall: 16 libs × 578 s ÷ 16 workers = ~10 min/pass (with parallelism).

If you want a single-pass run for cost reasons: `--passes 1`. The variance question is worth ≥2 passes IMO.

## Output layout

```
~/openhands-v1115/
├── .venv/
├── benchmarks/                       (the cloned repo at 62477b41)
└── runs/
    └── claude-sonnet-4-6/
        ├── pass1/
        │   ├── output.jsonl          (one row per instance)
        │   └── repos/<repo_name>/    (per-instance artifacts)
        ├── pass2/...
        └── aggregate.json            (the wrapper's combined report)
```

## What we capture for the marginal-value analysis

The wrapper extracts per-lib metrics from each pass's `output.jsonl` and aggregates:

| Metric | Why we track it |
|---|---|
| Instances solved (% libs at 100% pytest) | OpenHands' published metric — direct comparison to 7/16 |
| Aggregate test pass rate | Same metric we used for B2/B3 — lets us compare across baselines |
| Total LLM calls per lib | Quantifies the "iteration tax" OpenHands pays |
| Total agent steps per lib | Tool-use cycles |
| Tokens (input / output / cache_read / cache_write) | Cache effectiveness during long agent loops |
| Wall time per lib | Speed |
| $ cost per lib | Direct $/instance comparison |

Fed into `compare_baselines.py` (sibling), this answers:

- **B2 vs B6**: does the OpenHands agent loop deliver value vs single-shot?
- **B3 vs B6**: does the agent's tool use deliver value vs simple iteration?
- **B6 variance**: how reliable is the comparison?
