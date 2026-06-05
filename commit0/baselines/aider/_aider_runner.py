"""Shared Aider runner — invoked by aider_sonnet.py and aider_openai.py.

Public surface:
  run_aider_on_lib(lib_name, repo_dir, model_id, results_dir) -> dict

The result dict matches the schema produced by single_shot_sonnet.py so that
value_add_fingerprint.py picks it up without modification.

Aider Python API references:
  - https://aider.chat/docs/scripting.html
  - https://github.com/Aider-AI/aider/blob/main/aider/coders/base_coder.py
  Coder.create() accepts (verified from base_coder.py:652):
    main_model, io, fnames, read_only_fnames,
    auto_test, test_cmd, cache_prompts, stream,
    auto_commits, dirty_commits, dry_run, verbose, edit_format
  Cost attributes (verified from base_coder.py:785-790):
    coder.total_cost
    coder.total_tokens_sent
    coder.total_tokens_received
    coder.message_tokens_sent / message_tokens_received (per-message)
    coder.num_exhausted_context_windows
    coder.num_malformed_responses

The Aider Python API is not officially supported. Pin the version in
SETUP.md so a future Aider release that changes this surface doesn't
silently break the harness.
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
from io import BytesIO
from pathlib import Path

# Lazy imports so the module loads even before pip-installing aider.
# Engineering verifies on Day 14 that these imports resolve.

WORKSPACE = Path.home() / "kaizen-commit0"

# Reuse single_shot_sonnet.py helpers — they live in the parent dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from single_shot_sonnet import (  # noqa: E402
    EXCLUDE_DIRS,
    _candidate_package_dirs,
    discover_stub_files,
    extract_pdf_text,
    git,
    load_dotenv,
    run_pytest_via_commit0,
)

# ---------- Hard caps (per PHASE1_COST_REVIEW.md §2.1) ----------
MAX_WALL_S = 30 * 60               # 30 min wall-clock per library
MAX_COST_USD = 5.00                # abort if accumulated cost exceeds
MAX_INPUT_TOKENS = 200_000         # secondary safety cap

# ---------- Default test command (overridable per lib) ----------
# Aider's --auto-test runs this after each edit. `-x` here is only the agent's
# internal convergence heuristic (stop iterating at the first failure) — it must
# NOT be used for the authoritative score (see SCORING_TEST_CMD below).
DEFAULT_TEST_CMD = "pytest -x --tb=no -q"

# ---------- Authoritative scoring (full suite, never -x) ----------
# The recorded pass/fail counts MUST come from the full suite. We score through
# `commit0 test --branch` — the SAME path single_shot/reflexion/KD use — so the
# cell is byte-for-byte comparable (same Docker image, same test_dir). Scoring
# with `-x` truncates the denominator at the first failure; see ../../RE-VALIDATION.md.
CODE_BRANCH = "aider"                 # git branch the generated code is committed to
SCORING_VIA_COMMIT0 = "commit0-test-full-suite"
SCORING_VIA_LOCAL = "full-suite-local-pytest"   # fallback if commit0 emits no summary
SCORING_TEST_CMD = "pytest --tb=no -q"          # fallback command (still full suite)

# Per-lib overrides (empty by default; populate on Day 14 if needed)
PER_LIB_TEST_CMD: dict[str, str] = {
    # "minitorch": "pytest -x --tb=no -q tests/",      # example override
}


def _read_only_files(repo_dir: Path) -> list[Path]:
    """Test files + spec — Aider sees these but does not edit them."""
    out: list[Path] = []
    for parent in ("tests", "test", "testing"):
        p = repo_dir / parent
        if p.is_dir():
            out.extend(sorted(p.rglob("*.py")))
    spec_md = repo_dir / "spec.md"
    if spec_md.exists():
        out.append(spec_md)
    return out


def _materialize_spec_md(repo_dir: Path) -> Path | None:
    """Aider can read PDF directly, but a stable spec.md is cache-friendly.

    Decompress spec.pdf.bz2, extract text via pypdf, write spec.md to repo root.
    Returns the path to spec.md if successful, else None.
    """
    spec_pdf_bz2 = repo_dir / "spec.pdf.bz2"
    if not spec_pdf_bz2.exists():
        return None
    try:
        raw_pdf = bz2.decompress(spec_pdf_bz2.read_bytes())
    except Exception as e:
        print(f"  [warn] could not decompress spec.pdf.bz2: {e}", file=sys.stderr)
        return None
    text = extract_pdf_text(raw_pdf)
    if not text:
        return None
    spec_md = repo_dir / "spec.md"
    spec_md.write_text(text, encoding="utf-8")
    return spec_md


def _counts_from_summary(summary: str) -> dict[str, int]:
    """Parse a pytest summary line into {passed, failed, skipped, errors}.

    Case-insensitive (matching _is_pytest_summary) and lower-cases the matched kind,
    so an upper/mixed-case token can't pass the gate yet record all-zero counts.
    """
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for n, kind in re.findall(r"(\d+)\s+(passed|failed|skipped|error[s]?)", summary or "", re.I):
        k = kind.lower()
        counts["errors" if k.startswith("error") else k] = int(n)
    return counts


def _is_pytest_summary(summary: str) -> bool:
    """True only if `summary` is a real pytest result line (contains a
    pass/fail/error/skip count).

    `run_pytest_via_commit0` returns the last 500 bytes of stdout/stderr when it
    finds no summary line — non-empty but unparseable junk. Gating on mere
    truthiness would mis-stamp such a cell as `commit0-test-full-suite` with
    all-zero counts (a silent baseline-style mis-score). Gate on parseability.
    """
    return bool(re.search(r"\d+\s+(passed|failed|skipped|error)", summary or "", re.I))


def _start_branch(repo_dir: Path, branch: str) -> None:
    """Reset to the pinned commit0 starter and open a fresh arch branch.

    Mirrors kaizen_delta.py: the agent then edits the working tree, and we commit
    those edits onto `branch` so the generated code is recoverable and scoreable
    via `commit0 test --branch`.
    """
    git(repo_dir, "checkout", "commit0", check=True)
    git(repo_dir, "clean", "-fd", check=True)  # drop prior-run artifacts; a failed clean would leave noise in the patch
    git(repo_dir, "branch", "-D", branch)   # no-op if it doesn't exist (check=False)
    git(repo_dir, "checkout", "-b", branch, check=True)


def _strip_agent_noise(repo_dir: Path) -> None:
    """Remove non-code agent artifacts before committing the branch.

    `.aider.tags.cache.v4/*` are sqlite BINARIES; committing them makes commit0's
    container-side `git apply` of the branch patch fail, which silently falls back
    to the baseline score. spec.md / __pycache__ are also non-code noise.
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
    #    Strip agent noise FIRST so the branch — and thus commit0's patch.diff — is
    #    clean code only. Binary caches (.aider.tags.cache/*) make the container's
    #    patch application fail, silently scoring the baseline. See ../../RE-VALIDATION.md.
    _strip_agent_noise(repo_dir)
    git(repo_dir, "add", "-A", check=True)
    git(repo_dir, "commit", "--allow-empty", "-m", f"{branch} generated output ({lib_name})", check=True)

    # 2. Authoritative full-suite score via the same path as every other arch.
    exit_code, summary = run_pytest_via_commit0(lib_name, branch)
    counts = _counts_from_summary(summary)
    collected = counts["passed"] + counts["failed"] + counts["errors"]
    if _is_pytest_summary(summary) and collected > 0:
        scoring = SCORING_VIA_COMMIT0
    else:
        # Fallback: commit0 produced no PARSEABLE, non-zero summary. It returns the
        # last 500 bytes of stdout/stderr when it finds no summary line, and an
        # import/collection crash yields a traceback that parses to 0/0/0/0 — never
        # stamp full-suite on zero collected. Score locally, full suite, stamp LOCAL.
        print(f"  [warn] {lib_name}: commit0 test emitted no parseable/non-zero summary; local pytest fallback",
              file=sys.stderr)
        summary, counts = _final_pytest(repo_dir, SCORING_TEST_CMD)
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


def _final_pytest(repo_dir: Path, test_cmd: str = SCORING_TEST_CMD) -> tuple[str, dict[str, int]]:
    """Run pytest one final time to capture authoritative pass/fail counts.

    Defaults to SCORING_TEST_CMD (full suite, no -x). Do NOT pass the agent's
    `-x` loop command here — that truncates the denominator at the first failure
    and makes the cell non-comparable to the full-suite architectures.
    """
    proc = subprocess.run(
        test_cmd.split(),
        cwd=repo_dir,
        capture_output=True,
        timeout=300,  # 5 min cap on the final pytest run itself
    )
    output = proc.stdout.decode(errors="replace") + proc.stderr.decode(errors="replace")
    # Parse pytest summary from the last few lines
    summary_line = ""
    for line in reversed(output.splitlines()):
        low = line.lower()  # collection failures emit upper-case "ERROR"/"Interrupted: N errors"
        if "passed" in low or "failed" in low or "error" in low:
            summary_line = line.strip()
            break
    counts = _counts_from_summary(summary_line)
    return summary_line, counts


def run_aider_on_lib(
    lib_name: str,
    repo_dir: Path,
    model_id: str,
    out_path: Path,
) -> dict:
    """Run Aider end-to-end on one commit0 library.

    Args:
        lib_name: e.g. "wcwidth"
        repo_dir: absolute path to the commit0 starter repo
        model_id: litellm-style model id, e.g. "anthropic/claude-sonnet-4-6"
                  or "openai/gpt-5.4"
        out_path: where to write the result JSON
    """
    from aider.coders import Coder
    from aider.io import InputOutput
    from aider.models import Model

    # #3 (sane retries): fail fast on a stalled provider call — litellm's default is
    # 600s, which turned a degraded-Anthropic window into multi-hour thrash. 180s is
    # ample for large generations but cuts a hung call to ~3min; bounded retries +
    # the repeat_runner valid-rep gate then move on instead of hanging.
    import litellm
    litellm.request_timeout = 180
    litellm.num_retries = 4

    # Open a fresh branch off the pinned commit0 starter BEFORE any edits, so the
    # agent's changes land on a clean tree and can be committed + scored + exported.
    _start_branch(repo_dir, CODE_BRANCH)

    # Materialize spec as markdown for caching stability
    spec_md = _materialize_spec_md(repo_dir)
    if spec_md is None:
        print(f"  [warn] {lib_name}: no spec.md materialized; relying on docstrings",
              file=sys.stderr)

    # Discover stub files (reuse single_shot logic)
    stub_files = discover_stub_files(repo_dir)
    if not stub_files:
        return {
            "repo": lib_name, "model": model_id, "branch": "aider",
            "error": "no stub files discovered",
            "final_counts": {"passed": 0, "failed": 0, "skipped": 0, "errors": 0},
        }

    read_only = _read_only_files(repo_dir)
    test_cmd = PER_LIB_TEST_CMD.get(lib_name, DEFAULT_TEST_CMD)

    # Aider configuration
    io = InputOutput(yes=True, pretty=False)
    model = Model(model_id)

    coder = Coder.create(
        main_model=model,
        io=io,
        fnames=[str(p) for p in stub_files],
        read_only_fnames=[str(p) for p in read_only],
        auto_test=True,
        test_cmd=test_cmd,
        cache_prompts=True,         # native Anthropic prompt cache
        stream=False,
        auto_commits=False,         # don't pollute the starter repo with commits
        dirty_commits=False,
        verbose=False,
    )

    # Initial prompt — terse, since spec is in read-only context
    initial = (
        f"Implement all stubs in the {lib_name} library so the test suite passes.\n"
        f"Read spec.md for the contract. Read tests/ for the expected behavior.\n"
        f"Edit each stub file completely. Do not create new files. "
        f"Stop when '{test_cmd}' exits 0."
    )

    t0 = time.time()
    error = None
    try:
        coder.run(initial)
        # Aider's auto_test loop will iterate internally; coder.run returns when
        # the model declares done OR the test passes OR context exhausts.
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        print(f"  [error] aider raised: {error}", file=sys.stderr)
    elapsed = time.time() - t0

    # Persist the generated code onto the arch branch, score the FULL suite via
    # commit0 test --branch (parity with every other arch), and export a patch.
    final_summary, final_counts, scoring, patch_file, patch_sha = _persist_and_score(
        lib_name, repo_dir, CODE_BRANCH, out_path,
    )

    # Cost / token totals from the Coder instance
    total_cost = float(getattr(coder, "total_cost", 0.0) or 0.0)
    tokens_sent = int(getattr(coder, "total_tokens_sent", 0) or 0)
    tokens_received = int(getattr(coder, "total_tokens_received", 0) or 0)
    exhausted = int(getattr(coder, "num_exhausted_context_windows", 0) or 0)
    malformed = int(getattr(coder, "num_malformed_responses", 0) or 0)

    result = {
        "repo": lib_name,
        "model": model_id,
        "branch": "aider",
        "scoring": scoring,              # commit0 full-suite (or local fallback) — see ../../RE-VALIDATION.md
        "code_branch": CODE_BRANCH,      # git branch the generated code is committed to
        "patch_file": patch_file,        # committed diff artifact (workspace-independent)
        "patch_sha256": patch_sha,
        "elapsed_s": round(elapsed, 1),
        "final_summary": final_summary,
        "final_counts": final_counts,
        "totals": {
            "input_tokens": tokens_sent,
            "output_tokens": tokens_received,
            "cache_read_tokens": 0,        # aider tracks these in messages list, not totals
            "cache_write_tokens": 0,       # populate from coder.partial_response_content if needed
            "cost_usd": round(total_cost, 4),
        },
        "aider_diagnostics": {
            "exhausted_context_windows": exhausted,
            "malformed_responses": malformed,
            "test_cmd": test_cmd,
            "wall_clock_capped": elapsed >= MAX_WALL_S,
            "cost_capped": total_cost >= MAX_COST_USD,
        },
    }
    if error:
        result["aider_error"] = error

    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
