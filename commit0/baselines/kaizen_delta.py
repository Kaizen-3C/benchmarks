"""Kaizen-delta runner for commit0.

Architecture (revised after sanity test)
----------------------------------------
Per-FILE decompose → per-file recompose with module-level pytest grounding.

Earlier attempt used per-function AST stub detection but missed partial
stubs (functions with real logic ending in `pass`) and oversized data
table files. Per-file is simpler, more robust, and gives every file the
iteration grounding that B3 Reflexion lacked at aggregate level.

The AAR's three design constraints, satisfied:
  1. Caching from day one (Anthropic ephemeral on the spec block,
     OpenAI auto-cache on identical prefixes).
  2. Per-file iteration with grounded signal (vs B3 Reflexion's
     regenerate-all-on-aggregate-failure which regressed Sonnet -19pp).
  3. Provider abstraction surface (--provider anthropic|openai).

Phases
------
1. Decompose: list every .py file under the package source dir. Each is
   one "unit" to regenerate.
2. Recompose, per-file:
     a. Generate full file contents with prompt = spec (cached) + file
        path + current contents + spec instructions.
     b. Write file in place; commit on the kaizen branch.
     c. Run pytest. Track which tests pass after this file's update.
     d. If pytest progress was made (more tests pass than before, no new
        errors): accept this file. Else: retry ONCE with the specific
        failure tracebacks scoped to this file's tests.
3. Final eval: run full commit0 test.

Run
---
    python baselines/kaizen_delta.py <repo_name> [--provider anthropic|openai]
"""

from __future__ import annotations

import argparse
import ast
import bz2
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from single_shot_sonnet import (  # noqa: E402
    MAX_TOKENS, RESULTS_DIR, WORKSPACE,
    _ANSI, _PYTEST_FINAL_RE, _truncate, MAX_STUB_FILE_BYTES,
    TEST_DIR_OVERRIDES,
    discover_stub_files, extract_pdf_text, load_dotenv,
    git, write_files,
)
from _llm import LLMClient, cost, DEFAULT_MODELS  # noqa: E402


# -------------------- Decompose: per-file --------------------

def discover_files(repo_dir: Path) -> list[Path]:
    """Every .py file under the package source. Order: smaller first (cheaper to retry)."""
    files = discover_stub_files(repo_dir)
    return sorted(files, key=lambda p: p.stat().st_size)


# -------------------- Recompose: per-stub --------------------

PROMPT_PREAMBLE = """You are regenerating ONE file in a commit0 Python library.
The full specification is provided below (cached across files in this library).
You must return the COMPLETE replacement file contents."""


def build_cached_block(repo_name: str, spec_text: str) -> str:
    """The cacheable portion: spec + repo intro. Same string for every file in this lib."""
    return (
        f"# Library: {repo_name}\n\n"
        "## Specification\n\n"
        + (spec_text or "(spec PDF text extraction failed)")
        + "\n"
    )


def build_file_instructions(file: Path, file_src: str, repo_dir: Path,
                            prior_attempt: Optional[str] = None,
                            failure_signal: Optional[str] = None) -> str:
    rel = file.relative_to(repo_dir).as_posix()
    parts = [PROMPT_PREAMBLE, ""]
    parts.append(f"## File to regenerate: `{rel}`")
    parts.append("")
    parts.append("Current contents (may be a partial implementation, may have stubs):")
    parts.append("```python")
    parts.append(_truncate(file_src, MAX_STUB_FILE_BYTES))
    parts.append("```")
    parts.append("")
    parts.append(
        "Return ONE fenced code block tagged `python:full-file` containing the COMPLETE "
        "replacement file contents. Preserve module-level docstring if present. Implement "
        "ALL stub functions (any function whose body is `pass` or otherwise incomplete). "
        "If the module is a data-table file (e.g., Unicode table), emit the full data "
        "structure required by the spec."
    )
    if prior_attempt and failure_signal:
        parts.append("")
        parts.append("## Previous attempt failed -- use this signal to fix")
        parts.append("```")
        parts.append(failure_signal[:3000])
        parts.append("```")
        parts.append(
            "Adjust your output to address the specific failure above. Only emit the "
            "corrected file contents."
        )
    return "\n".join(parts)


_FULL_RE = re.compile(r"```python:full-file\n(.*?)```", re.DOTALL)
_GENERIC_FENCE_RE = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)


def parse_full_file(response: str) -> str:
    """Extract the full-file code block. Falls back to any python fence."""
    m = _FULL_RE.search(response)
    if m: return m.group(1)
    m = _GENERIC_FENCE_RE.search(response)
    if m: return m.group(1)
    return ""


def write_file(path: Path, content: str) -> None:
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8", newline="")


# -------------------- Pytest harness --------------------

ANSI = re.compile(r"\x1b\[[0-9;]*m")
PYTEST_FINAL_RE = re.compile(
    r"={3,}\s+((?:\d+\s+(?:passed|failed|skipped|error[s]?|warning[s]?|deselected|xfailed|xpassed)[, ]*)+).*?\sin\s+[\d.]+s\s+={3,}",
    re.IGNORECASE,
)


def find_summary(p: Path) -> str:
    if not p.exists(): return ""
    txt = ANSI.sub("", p.read_text(encoding="utf-8", errors="replace"))
    for line in reversed(txt.splitlines()):
        if PYTEST_FINAL_RE.search(line): return line.strip()
    return ""


def parse_counts(s: str) -> dict[str, int]:
    out = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for n, k in re.findall(r"(\d+)\s+(passed|failed|skipped|errors?)", ANSI.sub("", s or "")):
        kn = "errors" if k.startswith("error") else k
        out[kn] = int(n)
    return out


def run_pytest(repo_name: str, branch: str) -> tuple[int, str, str]:
    """Returns (exit_code, summary_line, sanitized_failure_excerpt_for_grounding)."""
    test_dir = TEST_DIR_OVERRIDES.get(repo_name, "tests")
    cmd = ["commit0", "test", repo_name, test_dir,
           "--branch", branch, "--backend", "local", "--timeout", "600"]
    r = subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True)
    log_root = WORKSPACE / "logs" / "pytest" / repo_name / branch
    summary = ""
    failure_signal = ""
    if log_root.is_dir():
        runs = sorted(log_root.iterdir(), key=lambda d: d.stat().st_mtime)
        if runs:
            test_output = runs[-1] / "test_output.txt"
            if test_output.exists():
                txt = test_output.read_text(encoding="utf-8", errors="replace")
                summary = find_summary(test_output)
                # Failure signal: the FAILURES section, sanitized to drop test source
                m = re.search(r"=+ FAILURES =+\n(.*?)(?:=+ |$)", txt, re.DOTALL)
                if m:
                    failure_signal = ANSI.sub("", m.group(1))[:3000]
    if not summary:
        summary = (r.stdout + r.stderr)[-500:]
    return r.returncode, summary, failure_signal


# -------------------- Per-lib orchestration --------------------

def run_one_lib(repo: str, provider: str, model: str, max_retries_per_file: int = 1) -> dict:
    print(f"\n{'='*60}\n[kaizen-delta] {repo} -- provider={provider} model={model}\n{'='*60}")
    repo_dir = WORKSPACE / "repos" / repo
    spec_bz2 = repo_dir / "spec.pdf.bz2"
    if not spec_bz2.exists():
        return {"repo": repo, "error": "missing_spec"}

    spec_text = extract_pdf_text(bz2.decompress(spec_bz2.read_bytes()))
    print(f"  spec text: {len(spec_text)} chars")

    files = discover_files(repo_dir)
    print(f"  decomposed: {len(files)} files (sorted small-to-large)")
    if not files:
        return {"repo": repo, "error": "no_files"}

    branch = "kaizen_delta"
    git(repo_dir, "checkout", "commit0")
    git(repo_dir, "branch", "-D", branch)
    git(repo_dir, "checkout", "-b", branch)

    client = LLMClient(provider, model)
    cached_block = build_cached_block(repo, spec_text)

    per_file = []
    total_cost = 0.0
    total_input = total_output = total_cache_r = total_cache_w = 0
    last_passed = 0  # Tracks pytest progress for grounding decisions
    last_summary = ""
    t0_total = time.time()

    for i, file in enumerate(files, 1):
        rel = file.relative_to(repo_dir).as_posix()
        print(f"  [{i}/{len(files)}] {rel} ({file.stat().st_size}b)")
        original_src = file.read_text(encoding="utf-8", errors="replace")
        prior_attempt = None
        prior_failure = None
        attempts: list[dict] = []
        accepted = False

        for attempt_n in range(max_retries_per_file + 1):
            t0 = time.time()
            instructions = build_file_instructions(file, original_src, repo_dir,
                                                   prior_attempt, prior_failure)
            try:
                response, usage = client.call(instructions, cached_block)
            except Exception as e:
                print(f"      attempt {attempt_n+1} call failed: {type(e).__name__}: {e}")
                attempts.append({"attempt": attempt_n + 1, "error": str(e)[:200]})
                break
            elapsed = time.time() - t0
            content = parse_full_file(response)
            c = cost(provider, usage)
            total_cost += c
            total_input += usage["input"]; total_output += usage["output"]
            total_cache_r += usage["cache_read"]; total_cache_w += usage["cache_write"]
            print(f"      attempt {attempt_n+1}: {elapsed:.1f}s in={usage['input']} "
                  f"cached={usage['cache_read']} out={usage['output']} content_chars={len(content)}")

            if not content.strip():
                attempts.append({"attempt": attempt_n + 1, "elapsed_s": round(elapsed, 1),
                                 "usage": usage, "result": "empty_response"})
                break

            try:
                write_file(file, content)
            except Exception as e:
                attempts.append({"attempt": attempt_n + 1, "elapsed_s": round(elapsed, 1),
                                 "usage": usage, "apply_error": str(e)[:200]})
                break

            git(repo_dir, "add", "-A")
            git(repo_dir, "commit", "--allow-empty", "-m",
                f"kaizen file={rel} attempt={attempt_n+1}")
            exit_code, summary, failure = run_pytest(repo, branch)
            counts = parse_counts(summary)
            now_passed = counts.get("passed", 0)
            attempts.append({"attempt": attempt_n + 1, "elapsed_s": round(elapsed, 1),
                             "usage": usage, "summary": ANSI.sub("", summary).strip(),
                             "counts": counts})
            print(f"      pytest: {ANSI.sub('', summary).strip()[:120]}")

            # Grounding rule: accept this attempt if pytest progress did not regress
            #   AND we didn't introduce new collection errors.
            errs = counts.get("errors", 0)
            if now_passed >= last_passed and errs == 0:
                last_passed = now_passed
                last_summary = ANSI.sub("", summary).strip()
                accepted = True
                break

            # Reject and retry: revert this file, prepare grounded feedback
            if attempt_n < max_retries_per_file:
                prior_attempt = content
                prior_failure = failure or summary
                git(repo_dir, "checkout", str(file.relative_to(repo_dir)))
                # original_src stays the same for the retry context

        if not accepted:
            # Revert this file to its pre-attempt state -- don't keep regressions
            git(repo_dir, "checkout", str(file.relative_to(repo_dir)))
            print(f"      -> reverted (no improvement after {len(attempts)} attempt(s))")

        per_file.append({"file": rel, "size": file.stat().st_size,
                         "accepted": accepted, "attempts": attempts})

    print(f"\n  [final] running full pytest for {repo}")
    git(repo_dir, "add", "-A")
    git(repo_dir, "commit", "--allow-empty", "-m", "kaizen final")
    exit_code, summary, _ = run_pytest(repo, branch)
    final_counts = parse_counts(summary)
    elapsed_total = time.time() - t0_total

    result = {
        "repo": repo, "provider": provider, "model": model, "branch": branch,
        "files_total": len(files),
        "files_accepted": sum(1 for f in per_file if f.get("accepted")),
        "elapsed_s": round(elapsed_total, 1),
        "final_summary": ANSI.sub("", summary).strip(),
        "final_counts": final_counts,
        "totals": {
            "input_tokens": total_input, "output_tokens": total_output,
            "cache_read_tokens": total_cache_r, "cache_write_tokens": total_cache_w,
            "cost_usd": round(total_cost, 4),
        },
        "per_file": per_file,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{repo}_kaizen_delta_{provider}.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n  final: {result['final_summary']}")
    print(f"  files accepted: {result['files_accepted']}/{result['files_total']}")
    print(f"  cost:  ${total_cost:.4f}  cache_read={total_cache_r/1000:.1f}K  "
          f"out={total_output/1000:.1f}K  wall={elapsed_total:.0f}s")
    print(f"  -> {out_path}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", help="commit0 library name")
    parser.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    parser.add_argument("--model", default=None,
                        help="Default: claude-sonnet-4-6 / gpt-5.4")
    parser.add_argument("--max-retries-per-file", type=int, default=1)
    args = parser.parse_args()

    load_dotenv(Path("/mnt/c/RepoEx/Kaizen-delta/.env"))
    key_env = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}[args.provider]
    if not os.environ.get(key_env):
        print(f"{key_env} not set", file=sys.stderr)
        return 2

    model = args.model or DEFAULT_MODELS[args.provider]
    result = run_one_lib(args.repo, args.provider, model, args.max_retries_per_file)
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
