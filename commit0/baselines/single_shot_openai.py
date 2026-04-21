"""Single-shot GPT-5.4 baseline for one commit0 library.

Mirrors single_shot_sonnet.py but uses OpenAI's API instead of Anthropic.
Imports the prompt builder, file discovery, parser, and pytest harness
from the Sonnet script to keep them in lockstep.

Differences from Sonnet:
  - No native PDF input — we use the same extracted-text path
  - No prompt caching (OpenAI auto-caches but no manual cache_control)
  - Different stop-reason semantics

Run: python baselines/single_shot_openai.py <repo>
"""

from __future__ import annotations

import argparse
import bz2
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from single_shot_sonnet import (  # noqa: E402
    MAX_TOKENS, MAX_STUB_FILE_BYTES, RESULTS_DIR, WORKSPACE,
    build_prompt, discover_stub_files, extract_pdf_text,
    git, load_dotenv, parse_response, run_pytest_via_commit0,
    write_files,
)

from openai import OpenAI

MODEL = "gpt-5.4"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("--branch", default="single_shot_openai")
    parser.add_argument("--no-test", action="store_true")
    args = parser.parse_args()

    load_dotenv(Path("/mnt/c/RepoEx/Kaizen-delta/.env"))
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not in env", file=sys.stderr)
        return 2

    repo_dir = WORKSPACE / "repos" / args.repo
    spec_bz2 = repo_dir / "spec.pdf.bz2"
    if not spec_bz2.exists():
        print(f"spec.pdf.bz2 not found in {repo_dir}", file=sys.stderr)
        return 2

    pdf_bytes = bz2.decompress(spec_bz2.read_bytes())
    spec_text = extract_pdf_text(pdf_bytes)
    print(f"[1/5] Spec PDF: {len(pdf_bytes)} B → {len(spec_text)} chars text")

    stub_files = discover_stub_files(repo_dir)
    print(f"[2/5] Found {len(stub_files)} source files")
    if not stub_files:
        return 3

    prompt = build_prompt(args.repo, stub_files, repo_dir, spec_text)
    print(f"[3/5] Prompt: {len(prompt)} chars; sending to {MODEL}")

    client = OpenAI(timeout=600.0, max_retries=4)
    t0 = time.time()
    msg = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=MAX_TOKENS,  # GPT-5.x renamed from max_tokens
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - t0
    response = msg.choices[0].message.content or ""
    in_tokens = msg.usage.prompt_tokens
    out_tokens = msg.usage.completion_tokens
    cached_tokens = getattr(msg.usage, "prompt_tokens_details", None)
    cache_read = (cached_tokens.cached_tokens if cached_tokens else 0) or 0
    print(f"      Done in {elapsed:.1f}s; in={in_tokens} cache_r={cache_read} out={out_tokens}")
    print(f"      Finish reason: {msg.choices[0].finish_reason}")

    files = parse_response(response)
    print(f"[4/5] Parsed {len(files)} code blocks")
    for relpath in files:
        print(f"      → {relpath}")
    if not files:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (RESULTS_DIR / f"{args.repo}_raw_response_openai.txt").write_text(response)
        return 1

    git(repo_dir, "checkout", "commit0")
    git(repo_dir, "branch", "-D", args.branch)
    git(repo_dir, "checkout", "-b", args.branch)
    written = write_files(repo_dir, files)
    git(repo_dir, "add", "-A")
    git(repo_dir, "commit", "-m", f"single-shot openai baseline ({MODEL})")

    result: dict[str, object] = {
        "repo": args.repo,
        "branch": args.branch,
        "model": MODEL,
        "elapsed_s": round(elapsed, 2),
        "input_tokens": in_tokens,
        "cached_input_tokens": cache_read,
        "output_tokens": out_tokens,
        "finish_reason": msg.choices[0].finish_reason,
        "files_written": written,
    }

    if args.no_test:
        print("[5/5] --no-test set, skipping pytest")
    else:
        print(f"[5/5] commit0 test {args.repo} --branch {args.branch}")
        exit_code, summary = run_pytest_via_commit0(args.repo, args.branch)
        result["pytest_exit"] = exit_code
        result["pytest_summary"] = summary
        print(f"      pytest exit={exit_code}  summary: {summary}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{args.repo}_single_shot_openai.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"      result → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
