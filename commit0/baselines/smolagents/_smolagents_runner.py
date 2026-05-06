"""Shared smolagents runner — invoked by smolagents_sonnet.py and smolagents_openai.py.

Public surface:
  run_smolagents_on_lib(lib_name, repo_dir, model_id, out_path) -> dict

smolagents API references:
  - https://github.com/huggingface/smolagents/blob/main/docs/source/en/guided_tour.md
  - https://huggingface.co/docs/smolagents/en/index

CodeAgent constructor (verified from guided_tour.md):
  CodeAgent(
    tools: list[Tool],
    model: Model,
    add_base_tools: bool = False,
    additional_authorized_imports: list[str] = [],
    executor_type: str = "local",        # or "docker", "e2b", "blaxel"
    executor_kwargs: dict = {},
    max_steps: int = 6,                  # we override to 20
    final_answer_checks: list = [],
    managed_agents: list = [],
    verbose: int = 0,
  )

LiteLLMModel constructor:
  LiteLLMModel(model_id="anthropic/claude-sonnet-4-6", api_key=None)

Cost tracking:
  smolagents does NOT surface cost in a standard API. We register a litellm
  success_callback to capture per-call cost into a closure-local accumulator,
  then read back after agent.run() returns. This is the pattern AgentOps and
  MLflow both use under the hood.

  Reference: https://docs.litellm.ai/docs/completion/token_usage
"""

from __future__ import annotations

import bz2
import json
import os
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE = Path.home() / "kaizen-commit0"

# Reuse single_shot_sonnet.py helpers
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from single_shot_sonnet import (  # noqa: E402
    discover_stub_files,
    extract_pdf_text,
    load_dotenv,
)

# ---------- Hard caps (per PHASE1_COST_REVIEW.md §2.2) ----------
MAX_STEPS = 20                     # tighter than OH's 30
MAX_WALL_S = 30 * 60
MAX_COST_USD = 5.00

# Authorized imports: minimal so smolagents can edit files but not phone home.
AUTHORIZED_IMPORTS = [
    "pathlib", "os", "subprocess", "json", "re", "ast",
    "io", "sys", "math", "typing", "collections", "itertools", "functools",
]

DEFAULT_TEST_CMD = "pytest -x --tb=no -q"


def _materialize_spec_md(repo_dir: Path) -> str:
    """Decompress + extract spec.pdf.bz2 into plain text."""
    spec_pdf_bz2 = repo_dir / "spec.pdf.bz2"
    if not spec_pdf_bz2.exists():
        return ""
    try:
        raw_pdf = bz2.decompress(spec_pdf_bz2.read_bytes())
    except Exception as e:
        print(f"  [warn] spec.pdf.bz2 decompress failed: {e}", file=sys.stderr)
        return ""
    text = extract_pdf_text(raw_pdf)
    # Persist to disk so the agent can re-read if it wants
    if text:
        (repo_dir / "spec.md").write_text(text, encoding="utf-8")
    return text


def _final_pytest(repo_dir: Path) -> tuple[str, dict[str, int]]:
    proc = subprocess.run(
        DEFAULT_TEST_CMD.split(),
        cwd=repo_dir,
        capture_output=True,
        timeout=300,
    )
    output = proc.stdout.decode(errors="replace") + proc.stderr.decode(errors="replace")
    summary = ""
    for line in reversed(output.splitlines()):
        if "passed" in line or "failed" in line or "error" in line:
            summary = line.strip()
            break
    import re
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for n, kind in re.findall(r"(\d+)\s+(passed|failed|skipped|error[s]?)", summary):
        counts["errors" if kind.startswith("error") else kind] = int(n)
    return summary, counts


class _CostTracker:
    """Closure-bound accumulator wired to litellm.success_callback.

    Each LLM call litellm makes via smolagents' LiteLLMModel triggers this
    callback, which adds per-call cost to total_cost. After agent.run()
    returns, read .total_cost / .input_tokens / .output_tokens.
    """

    def __init__(self) -> None:
        self.total_cost: float = 0.0
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cache_read_tokens: int = 0
        self.calls: int = 0
        self.errors: list[str] = []

    def callback(self, kwargs, completion_response, start_time, end_time):  # noqa: ANN001
        # litellm 1.81+ returns Pydantic-style wrapper objects for usage and
        # prompt_tokens_details; older releases returned plain dicts. Use getattr
        # with a dict fallback so this works across litellm versions.
        def _get(obj, key, default=0):
            if obj is None:
                return default
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        try:
            usage = _get(completion_response, "usage") or {}
            self.input_tokens += int(_get(usage, "prompt_tokens", 0) or 0)
            self.output_tokens += int(_get(usage, "completion_tokens", 0) or 0)
            # litellm exposes cache_read in prompt_tokens_details.cached_tokens
            ptd = _get(usage, "prompt_tokens_details") or {}
            self.cache_read_tokens += int(_get(ptd, "cached_tokens", 0) or 0)
            # litellm computes cost via response_cost helper
            cost = kwargs.get("response_cost") or 0
            if not cost:
                try:
                    import litellm
                    cost = litellm.completion_cost(completion_response=completion_response) or 0
                except Exception:
                    cost = 0
            self.total_cost += float(cost or 0)
            self.calls += 1
        except Exception as e:
            self.errors.append(f"{type(e).__name__}: {e}")


def run_smolagents_on_lib(
    lib_name: str,
    repo_dir: Path,
    model_id: str,
    out_path: Path,
) -> dict:
    """Run smolagents.CodeAgent end-to-end on one commit0 library."""
    import litellm
    from smolagents import CodeAgent, LiteLLMModel

    spec_text = _materialize_spec_md(repo_dir)
    stub_files = discover_stub_files(repo_dir)
    if not stub_files:
        return {
            "repo": lib_name, "model": model_id, "branch": "smolagents",
            "error": "no stub files discovered",
            "final_counts": {"passed": 0, "failed": 0, "skipped": 0, "errors": 0},
        }

    # Wire cost tracking via litellm callback
    tracker = _CostTracker()
    litellm.success_callback = [tracker.callback]

    model = LiteLLMModel(model_id=model_id)
    agent = CodeAgent(
        tools=[],                                          # no web search; file-edit only
        model=model,
        add_base_tools=False,
        additional_authorized_imports=AUTHORIZED_IMPORTS,
        executor_type="local",                             # NOT docker — avoid Docker-in-Docker
        max_steps=MAX_STEPS,
        verbosity_level=0,                                 # smolagents >=1.20 (was `verbose`)
    )

    stub_paths_str = "\n".join(
        f"  - {p.relative_to(repo_dir).as_posix()}" for p in stub_files
    )
    prompt = (
        f"You are implementing the {lib_name} library by editing stub files in {repo_dir}.\n\n"
        f"## Specification\n"
        f"Read {repo_dir}/spec.md (or fall back to in-file docstrings).\n\n"
        f"## Tests (your oracle)\n"
        f"Read files under {repo_dir}/tests/ to understand expected behavior. Do NOT edit tests.\n\n"
        f"## Stub files to implement\n"
        f"{stub_paths_str}\n\n"
        f"## Procedure\n"
        f"1. Read the spec and tests to understand the contract.\n"
        f"2. Edit each stub file in place using `Path.write_text()`.\n"
        f"3. Run `subprocess.run(['pytest', '-x', '--tb=no', '-q'], cwd='{repo_dir}', "
        f"capture_output=True)` and check the output.\n"
        f"4. Iterate until pytest passes or you've used your step budget.\n\n"
        f"Use only the authorized imports. Do not create new files."
    )

    t0 = time.time()
    error = None
    try:
        agent.run(prompt)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        print(f"  [error] smolagents raised: {error}", file=sys.stderr)
    elapsed = time.time() - t0

    # Final authoritative pytest
    final_summary, final_counts = _final_pytest(repo_dir)

    result = {
        "repo": lib_name,
        "model": model_id,
        "branch": "smolagents",
        "elapsed_s": round(elapsed, 1),
        "final_summary": final_summary,
        "final_counts": final_counts,
        "totals": {
            "input_tokens": tracker.input_tokens,
            "output_tokens": tracker.output_tokens,
            "cache_read_tokens": tracker.cache_read_tokens,
            "cache_write_tokens": 0,           # smolagents/litellm don't expose write breakdown
            "cost_usd": round(tracker.total_cost, 4),
        },
        "smolagents_diagnostics": {
            "llm_calls": tracker.calls,
            "max_steps": MAX_STEPS,
            "executor_type": "local",
            "wall_clock_capped": elapsed >= MAX_WALL_S,
            "cost_capped": tracker.total_cost >= MAX_COST_USD,
            "callback_errors": tracker.errors,
        },
    }
    if error:
        result["smolagents_error"] = error

    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
