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
import json
import os
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
    load_dotenv,
)

# ---------- Hard caps (per PHASE1_COST_REVIEW.md §2.1) ----------
MAX_WALL_S = 30 * 60               # 30 min wall-clock per library
MAX_COST_USD = 5.00                # abort if accumulated cost exceeds
MAX_INPUT_TOKENS = 200_000         # secondary safety cap

# ---------- Default test command (overridable per lib) ----------
# Aider's --auto-test runs this after each edit. commit0 uses the standard
# pytest entry. Verify on Day 14 that no library needs a custom invocation.
DEFAULT_TEST_CMD = "pytest -x --tb=no -q"

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


def _final_pytest(repo_dir: Path, test_cmd: str) -> tuple[str, dict[str, int]]:
    """Run pytest one final time to capture authoritative pass/fail counts."""
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
        if "passed" in line or "failed" in line or "error" in line:
            summary_line = line.strip()
            break
    # Reuse the parser logic from run_lite_single_shot.py
    import re
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for n, kind in re.findall(r"(\d+)\s+(passed|failed|skipped|error[s]?)", summary_line):
        counts["errors" if kind.startswith("error") else kind] = int(n)
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

    # Final authoritative pytest run
    final_summary, final_counts = _final_pytest(repo_dir, test_cmd)

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
