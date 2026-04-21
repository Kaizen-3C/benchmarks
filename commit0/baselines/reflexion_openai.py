"""Reflexion-style baseline with GPT-5.4.

Mirrors reflexion_sonnet.py but uses OpenAI's API. OpenAI auto-caches
repeated prompt prefixes across calls within 5 min — no cache_control
headers needed. We report `cached_tokens` from usage.prompt_tokens_details
to quantify hit rate.

Max 3 iterations per lib with same early-stop rules as Sonnet version.
"""

from __future__ import annotations

import argparse
import bz2
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from single_shot_sonnet import (  # noqa: E402
    MAX_TOKENS, MAX_STUB_FILE_BYTES, RESULTS_DIR, WORKSPACE,
    _ANSI, _PYTEST_FINAL_RE, _truncate, TEST_DIR_OVERRIDES,
    discover_stub_files, extract_pdf_text, load_dotenv,
    parse_response, write_files, git,
)
from reflexion_sonnet import (  # noqa: E402
    sanitize_pytest_output, find_final_summary, parse_counts,
)

from openai import OpenAI

MODEL = "gpt-5.4"
MAX_ITERS_DEFAULT = 3


def run_pytest(repo_name: str, branch: str) -> tuple[int, str, str]:
    test_dir = TEST_DIR_OVERRIDES.get(repo_name, "tests")
    cmd = ["commit0", "test", repo_name, test_dir,
           "--branch", branch, "--backend", "local", "--timeout", "600"]
    r = subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True)
    log_root = WORKSPACE / "logs" / "pytest" / repo_name / branch
    summary, full_output = "", ""
    if log_root.is_dir():
        per_run_dirs = sorted(log_root.iterdir(), key=lambda d: d.stat().st_mtime)
        if per_run_dirs:
            test_output = per_run_dirs[-1] / "test_output.txt"
            if test_output.exists():
                full_output = test_output.read_text(encoding="utf-8", errors="replace")
                summary = find_final_summary(test_output)
    if not summary:
        summary = (r.stdout + r.stderr)[-500:]
    return r.returncode, summary, sanitize_pytest_output(full_output)


def build_initial_prompt(repo_name: str, stub_files, repo_dir: Path, spec_text: str) -> str:
    parts = [
        f"You are filling in stubs for the Python library `{repo_name}`.",
        "",
        "=== SPECIFICATION ===",
        spec_text or "(spec PDF text extraction failed)",
        "",
        "=== INSTRUCTIONS ===",
        f"There are {len(stub_files)} source files below. Each shows its repo-relative path.",
        "Function bodies that contain only `pass` (or are otherwise empty stubs) need real implementations.",
        "Module-level data structures that are placeholders (empty dicts, empty tuples) need their full data.",
        "Files marked TRUNCATED were too large to send fully -- infer the structure and emit your best version.",
        "",
        "Return ONE response containing one fenced code block per file you modify.",
        "Each code block MUST be tagged with the language and filename, like this:",
        "",
        "```python:wcwidth/wcwidth.py",
        "<full file contents>",
        "```",
        "",
        "Rules:",
        "- Emit the COMPLETE file contents in each block, not a diff",
        "- Preserve existing imports, docstrings, and signatures",
        "- Only emit blocks for files you changed",
        "- Do not emit explanatory text outside the code blocks",
        "",
        "=== STUB FILES ===",
        "",
    ]
    for p in stub_files:
        rel = p.relative_to(repo_dir).as_posix()
        content = _truncate(p.read_text(encoding="utf-8", errors="replace"), MAX_STUB_FILE_BYTES)
        parts.append(f"--- {rel} ---")
        parts.append(content)
        parts.append("")
    return "\n".join(parts)


def call_llm(client: OpenAI, messages: list[dict]) -> tuple[str, dict]:
    msg = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=MAX_TOKENS,
        messages=messages,
    )
    response = msg.choices[0].message.content or ""
    details = getattr(msg.usage, "prompt_tokens_details", None)
    cached = (details.cached_tokens if details else 0) or 0
    usage = {
        "input_tokens": msg.usage.prompt_tokens,
        "cached_input_tokens": cached,
        "output_tokens": msg.usage.completion_tokens,
        "stop_reason": msg.choices[0].finish_reason,
    }
    return response, usage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("--branch", default="reflexion_openai")
    parser.add_argument("--max-iters", type=int, default=MAX_ITERS_DEFAULT)
    args = parser.parse_args()

    load_dotenv(Path("/mnt/c/RepoEx/Kaizen-delta/.env"))
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    repo_dir = WORKSPACE / "repos" / args.repo
    spec_bz2 = repo_dir / "spec.pdf.bz2"
    if not (repo_dir.is_dir() and spec_bz2.exists()):
        print(f"bad repo {args.repo}", file=sys.stderr)
        return 2

    pdf_bytes = bz2.decompress(spec_bz2.read_bytes())
    spec_text = extract_pdf_text(pdf_bytes)
    print(f"[setup] spec PDF {len(pdf_bytes)} B -> {len(spec_text)} chars text")

    stub_files = discover_stub_files(repo_dir)
    print(f"[setup] {len(stub_files)} source files")
    if not stub_files:
        return 3

    initial_prompt = build_initial_prompt(args.repo, stub_files, repo_dir, spec_text)
    client = OpenAI(timeout=600.0, max_retries=4)

    iterations = []
    best_pass = -1
    best_summary = ""
    prior_failure_log = ""
    conversation = [{"role": "user", "content": initial_prompt}]

    for iter_n in range(1, args.max_iters + 1):
        print(f"\n=== iter {iter_n}/{args.max_iters} ===")
        if iter_n > 1:
            reflection_text = (
                f"The previous attempt's pytest output (test source elided per rules):\n"
                f"```\n{prior_failure_log}\n```\n\n"
                f"Reflect briefly on the failure pattern, then emit corrected files in "
                f"the same fenced format. Only emit files you are changing."
            )
            conversation.append({"role": "user", "content": reflection_text})

        t0 = time.time()
        response, usage = call_llm(client, conversation)
        elapsed = time.time() - t0
        print(f"  call: {elapsed:.1f}s  in={usage['input_tokens']} "
              f"cached={usage['cached_input_tokens']} out={usage['output_tokens']}")

        conversation.append({"role": "assistant", "content": response})

        files = parse_response(response)
        print(f"  parsed {len(files)} code blocks")
        if not files:
            iterations.append({"iter": iter_n, "elapsed_s": round(elapsed, 1),
                               "files_written": [], "summary": "(no code parsed)",
                               "counts": {}, "usage": usage})
            break

        git(repo_dir, "checkout", "commit0")
        git(repo_dir, "branch", "-D", args.branch)
        git(repo_dir, "checkout", "-b", args.branch)
        written = write_files(repo_dir, files)
        git(repo_dir, "add", "-A")
        git(repo_dir, "commit", "-m", f"reflexion-openai iter {iter_n}")

        exit_code, summary, sanitized = run_pytest(args.repo, args.branch)
        counts = parse_counts(summary)
        passed = counts.get("passed", 0)
        clean = _ANSI.sub("", summary).strip()
        print(f"  pytest exit={exit_code}  summary: {clean}")

        iterations.append({"iter": iter_n, "elapsed_s": round(elapsed, 1),
                           "files_written": written, "summary": clean,
                           "counts": counts, "usage": usage, "pytest_exit": exit_code})

        attempted = passed + counts.get("failed", 0) + counts.get("errors", 0)
        if passed > best_pass:
            best_pass = passed
            best_summary = clean
        if attempted > 0 and passed == attempted:
            print("  -> 100% pass, stopping")
            break
        if iter_n >= 2 and iterations[-1]["counts"].get("passed", 0) <= \
                iterations[-2]["counts"].get("passed", 0):
            print("  -> no improvement vs prior iter, stopping")
            break
        prior_failure_log = sanitized

    total_in = sum(it["usage"].get("input_tokens", 0) for it in iterations)
    total_cached = sum(it["usage"].get("cached_input_tokens", 0) for it in iterations)
    total_out = sum(it["usage"].get("output_tokens", 0) for it in iterations)
    total_elapsed = sum(it["elapsed_s"] for it in iterations)

    result = {
        "repo": args.repo, "branch": args.branch, "model": MODEL,
        "max_iters": args.max_iters, "iters_run": len(iterations),
        "best_pass": best_pass, "best_summary": best_summary,
        "iterations": iterations,
        "totals": {
            "input_tokens": total_in,
            "cached_input_tokens": total_cached,
            "output_tokens": total_out,
            "elapsed_s": round(total_elapsed, 1),
        },
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"{args.repo}_reflexion_openai.json").write_text(json.dumps(result, indent=2))
    print(f"\nbest: {best_summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
