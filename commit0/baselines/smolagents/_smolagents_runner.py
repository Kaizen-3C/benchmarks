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
import hashlib
import json
import os
import re
import shutil
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
    git,
    load_dotenv,
    run_pytest_via_commit0,
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

DEFAULT_TEST_CMD = "pytest -x --tb=no -q"   # agent's in-loop convergence heuristic only

# ---------- Authoritative scoring (full suite, never -x) ----------
# The recorded pass/fail counts MUST come from the full suite. We score through
# `commit0 test --branch` — the SAME path single_shot/reflexion/KD use — so the
# cell is byte-for-byte comparable (same Docker image, same test_dir). Scoring
# with `-x` truncates the denominator at the first failure; see ../../RE-VALIDATION.md.
CODE_BRANCH = "smolagents"            # git branch the generated code is committed to
SCORING_VIA_COMMIT0 = "commit0-test-full-suite"
SCORING_VIA_LOCAL = "full-suite-local-pytest"   # fallback if commit0 emits no summary
SCORING_TEST_CMD = "pytest --tb=no -q"          # fallback command (still full suite)


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


def _counts_from_summary(summary: str) -> dict[str, int]:
    """Parse a pytest summary line into {passed, failed, skipped, errors}."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for n, kind in re.findall(r"(\d+)\s+(passed|failed|skipped|error[s]?)", summary or ""):
        counts["errors" if kind.startswith("error") else kind] = int(n)
    return counts


def _start_branch(repo_dir: Path, branch: str) -> None:
    """Reset to the pinned commit0 starter and open a fresh arch branch.

    The agent then edits the working tree, and we commit those edits onto `branch`
    so the generated code is recoverable and scoreable via `commit0 test --branch`.
    """
    git(repo_dir, "checkout", "commit0")
    git(repo_dir, "clean", "-fd")           # drop prior-run artifacts (spec.md, agent caches)
    git(repo_dir, "branch", "-D", branch)   # no-op if it doesn't exist (check=False)
    git(repo_dir, "checkout", "-b", branch)


def _final_pytest(repo_dir: Path) -> tuple[str, dict[str, int]]:
    # FULL SUITE (SCORING_TEST_CMD, no -x) — local fallback when commit0 emits no
    # summary. Not the agent's -x loop command. See ../../RE-VALIDATION.md.
    proc = subprocess.run(
        SCORING_TEST_CMD.split(),
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
    return summary, _counts_from_summary(summary)


def _strip_agent_noise(repo_dir: Path) -> None:
    """Remove non-code agent artifacts before committing the branch.

    Committing binary/noise files (e.g. .aider.tags.cache, spec.md) makes commit0's
    container-side patch application fail, silently scoring the baseline. Strip them
    so the branch — and thus commit0's patch.diff — is clean code only.
    """
    for n in list(repo_dir.glob(".aider*")) + [repo_dir / "spec.md"]:
        if n.is_dir():
            shutil.rmtree(n, ignore_errors=True)
        elif n.exists():
            n.unlink()
    for pyc in repo_dir.rglob("__pycache__"):
        shutil.rmtree(pyc, ignore_errors=True)


def _persist_and_score(
    lib_name: str, repo_dir: Path, branch: str, out_path: Path,
) -> tuple[str, dict[str, int], str, str | None, str | None]:
    """Commit the agent's edits, score the FULL suite via commit0, export a patch.

    Returns (summary, counts, scoring_provenance, patch_rel_path, patch_sha256).
    """
    # 1. Persist generated code onto the arch branch (recoverable in the workspace).
    #    Strip agent noise FIRST (see _strip_agent_noise) so commit0's patch.diff is
    #    clean code only — committing binaries silently scores the baseline.
    _strip_agent_noise(repo_dir)
    git(repo_dir, "add", "-A")
    git(repo_dir, "commit", "--allow-empty", "-m", f"{branch} generated output ({lib_name})")

    # 2. Authoritative full-suite score via the same path as every other arch.
    exit_code, summary = run_pytest_via_commit0(lib_name, branch)
    if summary:
        counts = _counts_from_summary(summary)
        scoring = SCORING_VIA_COMMIT0
    else:
        print(f"  [warn] {lib_name}: commit0 test emitted no summary; local pytest fallback",
              file=sys.stderr)
        summary, counts = _final_pytest(repo_dir)
        scoring = SCORING_VIA_LOCAL

    # 3. Export the generated diff into THIS repo (workspace-independent artifact).
    patch_rel = patch_sha = None
    try:
        # exclude non-code noise so the saved patch is pure generated code
        diff = git(repo_dir, "diff", "commit0", branch, "--", ".",
                   ":(exclude)spec.md",
                   ":(exclude,glob).aider**",
                   ":(exclude,glob)**/__pycache__/**")
        patch_dir = out_path.parent / "patches"
        patch_dir.mkdir(parents=True, exist_ok=True)
        patch_path = patch_dir / f"{out_path.stem}.patch"
        patch_path.write_text(diff, encoding="utf-8")
        patch_rel = f"patches/{patch_path.name}"
        patch_sha = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    except Exception as e:
        print(f"  [warn] {lib_name}: patch export failed: {e}", file=sys.stderr)
    return summary, counts, scoring, patch_rel, patch_sha


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
    # #3 (sane retries): fail fast on a stalled provider call (litellm default 600s ->
    # multi-hour thrash on a degraded window). 180s + bounded retries; the gate moves on.
    litellm.request_timeout = 180
    litellm.num_retries = 4

    # Open a fresh branch off the pinned commit0 starter BEFORE any edits, so the
    # agent's changes land on a clean tree and can be committed + scored + exported.
    _start_branch(repo_dir, CODE_BRANCH)

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

    # Persist the generated code onto the arch branch, score the FULL suite via
    # commit0 test --branch (parity with every other arch), and export a patch.
    final_summary, final_counts, scoring, patch_file, patch_sha = _persist_and_score(
        lib_name, repo_dir, CODE_BRANCH, out_path,
    )

    result = {
        "repo": lib_name,
        "model": model_id,
        "branch": "smolagents",
        "scoring": scoring,              # commit0 full-suite (or local fallback) — see ../../RE-VALIDATION.md
        "code_branch": CODE_BRANCH,      # git branch the generated code is committed to
        "patch_file": patch_file,        # committed diff artifact (workspace-independent)
        "patch_sha256": patch_sha,
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
