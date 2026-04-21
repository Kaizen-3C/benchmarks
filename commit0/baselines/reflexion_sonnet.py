"""Reflexion-style baseline: Sonnet 4.6 + iterative pytest-feedback loop.

Iteration N:
  1. Generate code (iter 1 = same prompt as single-shot; iter 2+ = adds
     "previous attempt's pytest output" as a reflection signal)
  2. Commit on a branch, run `commit0 test`, capture test_output.txt
  3. If 100% pass OR no improvement vs prior iter → stop early
  4. Otherwise feed the (test-source-stripped) failure log into next iter

Reflection constraint: failure log is sanitized — any line whose path comes
from a `tests/` or `test_*` file is replaced with `<test source elided>`.
This honors the §3.4 protocol rule: Reflexion sees pass/fail outcomes and
exception messages, NOT the test code itself.

Prompt caching: the spec + stub block is marked with cache_control:ephemeral
so iterations 2-3 read it from cache (~10% of the per-token cost).

Run: python baselines/reflexion_sonnet.py <repo> [--max-iters N]
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

from anthropic import Anthropic

sys.path.insert(0, str(Path(__file__).parent))
from single_shot_sonnet import (  # noqa: E402
    MAX_TOKENS, MODEL, RESULTS_DIR, TEST_DIR_OVERRIDES, WORKSPACE,
    _ANSI, _PYTEST_FINAL_RE, _truncate, MAX_STUB_FILE_BYTES,
    discover_stub_files, extract_pdf_text, load_dotenv,
    parse_response, write_files, git,
)

MAX_ITERS_DEFAULT = 3
LARGE_PROMPT_THRESHOLD_TOKENS = 1024  # Anthropic minimum for caching


def sanitize_pytest_output(text: str, max_chars: int = 20_000) -> str:
    """Drop lines whose source paths come from tests/ — Reflexion must not see test code."""
    clean = _ANSI.sub("", text)
    out_lines: list[str] = []
    elided = False
    for line in clean.splitlines():
        # Heuristic: pytest tracebacks show source like "tests/test_foo.py:42: in test_bar"
        # or "/testbed/tests/conftest.py:5: in <module>". Suppress these (and the
        # immediately-following code-context lines) — they leak test source.
        is_test_path = bool(re.search(r"(^|[/\\])tests?[/\\][\w_-]+\.py", line))
        if is_test_path:
            if not elided:
                out_lines.append("  <test source elided>")
                elided = True
            continue
        # Reset the elision flag when we leave the test-traceback block
        # (a blank line or a non-indented line breaks the hunk).
        if elided and (not line.strip() or not line.startswith("  ")):
            elided = False
        out_lines.append(line)
    sanitized = "\n".join(out_lines)
    if len(sanitized) > max_chars:
        head = sanitized[: max_chars // 2]
        tail = sanitized[-max_chars // 2 :]
        sanitized = head + "\n... [truncated] ...\n" + tail
    return sanitized


def find_final_summary(p: Path) -> str:
    if not p.exists():
        return ""
    txt = _ANSI.sub("", p.read_text(encoding="utf-8", errors="replace"))
    for line in reversed(txt.splitlines()):
        if _PYTEST_FINAL_RE.search(line):
            return line.strip()
    return ""


def parse_counts(summary: str) -> dict[str, int]:
    out = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for n, kind in re.findall(
        r"(\d+)\s+(passed|failed|skipped|errors?)", _ANSI.sub("", summary or "")
    ):
        kind_norm = "errors" if kind.startswith("error") else kind
        out[kind_norm] = int(n)
    return out


def pass_count(summary: str) -> int:
    return parse_counts(summary).get("passed", 0)


def run_pytest(repo_name: str, branch: str) -> tuple[int, str, str]:
    """Run pytest in container; return (exit_code, summary_line, sanitized_output)."""
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


def build_initial_prompt_blocks(
    repo_name: str, stub_files: list[Path], repo_dir: Path, spec_text: str
) -> list[dict]:
    """Return content blocks. The cacheable block is the spec+stubs;
    the rules block is small and not cached."""
    spec_and_stubs_parts = [
        "=== SPECIFICATION ===",
        spec_text or "(spec PDF text extraction failed)",
        "",
        "=== STUB FILES ===",
        "",
    ]
    for p in stub_files:
        rel = p.relative_to(repo_dir).as_posix()
        content = _truncate(p.read_text(encoding="utf-8", errors="replace"),
                            MAX_STUB_FILE_BYTES)
        spec_and_stubs_parts.append(f"--- {rel} ---")
        spec_and_stubs_parts.append(content)
        spec_and_stubs_parts.append("")
    cached_text = "\n".join(spec_and_stubs_parts)

    rules_text = (
        f"You are filling in stubs for the Python library `{repo_name}`.\n"
        "\n"
        "Return ONE response with one fenced code block per file you modify.\n"
        "Each block MUST be tagged with the filename, like:\n"
        "\n"
        "```python:wcwidth/wcwidth.py\n"
        "<full file contents>\n"
        "```\n"
        "\n"
        "Rules:\n"
        "- Emit COMPLETE file contents in each block, not a diff.\n"
        "- Preserve existing imports, docstrings, and signatures.\n"
        "- Only emit blocks for files you changed.\n"
        "- No explanatory prose outside the code blocks.\n"
    )

    blocks: list[dict] = [
        # The big cacheable chunk: spec + stubs. Cache for ~5 min so subsequent
        # reflection iterations on the same lib hit the cache.
        {"type": "text", "text": cached_text,
         "cache_control": {"type": "ephemeral"}},
        # The instruction tail varies less but isn't worth caching separately.
        {"type": "text", "text": rules_text},
    ]
    return blocks


def call_llm(client: Anthropic, system_blocks: list[dict] | None,
             messages: list[dict]) -> tuple[str, dict]:
    kwargs: dict = {"model": MODEL, "max_tokens": MAX_TOKENS, "messages": messages}
    if system_blocks:
        kwargs["system"] = system_blocks
    msg = client.messages.create(**kwargs)
    response = msg.content[0].text
    usage = {
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
        "cache_read_input_tokens": getattr(msg.usage, "cache_read_input_tokens", 0),
        "cache_creation_input_tokens": getattr(msg.usage, "cache_creation_input_tokens", 0),
        "stop_reason": msg.stop_reason,
    }
    return response, usage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("--branch", default="reflexion_sonnet")
    parser.add_argument("--max-iters", type=int, default=MAX_ITERS_DEFAULT)
    args = parser.parse_args()

    load_dotenv(Path("/mnt/c/RepoEx/Kaizen-delta/.env"))
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set after dotenv load", file=sys.stderr)
        return 2

    repo_dir = WORKSPACE / "repos" / args.repo
    if not repo_dir.is_dir():
        print(f"Repo not found: {repo_dir}", file=sys.stderr)
        return 2
    spec_bz2 = repo_dir / "spec.pdf.bz2"
    if not spec_bz2.exists():
        print(f"spec.pdf.bz2 not found", file=sys.stderr)
        return 2

    pdf_bytes = bz2.decompress(spec_bz2.read_bytes())
    spec_text = extract_pdf_text(pdf_bytes)
    print(f"[setup] spec PDF {len(pdf_bytes)} B -> {len(spec_text)} chars text")

    stub_files = discover_stub_files(repo_dir)
    print(f"[setup] {len(stub_files)} source files")
    if not stub_files:
        print("ERROR: no source files", file=sys.stderr)
        return 3

    blocks = build_initial_prompt_blocks(args.repo, stub_files, repo_dir, spec_text)
    client = Anthropic(timeout=600.0, max_retries=4)

    iterations: list[dict] = []
    best_pass = -1
    best_summary = ""
    prior_failure_log = ""

    # Conversation: keep accumulating user/assistant turns to give the model
    # the iteration history. The cached block stays in messages[0].user.
    conversation: list[dict] = [{"role": "user", "content": blocks}]

    for iter_n in range(1, args.max_iters + 1):
        print(f"\n=== iter {iter_n}/{args.max_iters} ===")
        if iter_n > 1:
            # Append a user turn with the prior pytest result + reflection prompt
            reflection_text = (
                f"The previous attempt's pytest output (test source elided per rules):\n"
                f"```\n{prior_failure_log}\n```\n\n"
                f"Reflect briefly on the failure pattern, then emit corrected files in "
                f"the same fenced format. Only emit files you are changing."
            )
            conversation.append({"role": "user",
                                 "content": [{"type": "text", "text": reflection_text}]})

        t0 = time.time()
        response, usage = call_llm(client, None, conversation)
        elapsed = time.time() - t0
        print(f"  call: {elapsed:.1f}s  in={usage['input_tokens']} "
              f"cache_r={usage['cache_read_input_tokens']} "
              f"cache_w={usage['cache_creation_input_tokens']} "
              f"out={usage['output_tokens']}")

        # Append assistant response to conversation for next iter
        conversation.append({"role": "assistant",
                             "content": [{"type": "text", "text": response}]})

        files = parse_response(response)
        print(f"  parsed {len(files)} code blocks")

        if not files:
            print("  no code blocks parsed, stopping early")
            iterations.append({
                "iter": iter_n, "elapsed_s": round(elapsed, 1),
                "files_written": [], "summary": "(no code parsed)",
                "counts": {}, "usage": usage,
            })
            break

        # Reset branch to the commit0 base, write files, commit
        git(repo_dir, "checkout", "commit0")
        git(repo_dir, "branch", "-D", args.branch)
        git(repo_dir, "checkout", "-b", args.branch)
        written = write_files(repo_dir, files)
        git(repo_dir, "add", "-A")
        git(repo_dir, "commit", "-m", f"reflexion iter {iter_n}")
        print(f"  wrote {len(written)} files, branch {args.branch}")

        exit_code, summary, sanitized = run_pytest(args.repo, args.branch)
        counts = parse_counts(summary)
        passed = counts.get("passed", 0)
        clean_summary = _ANSI.sub("", summary).strip()
        print(f"  pytest exit={exit_code}  summary: {clean_summary}")

        iterations.append({
            "iter": iter_n,
            "elapsed_s": round(elapsed, 1),
            "files_written": written,
            "summary": clean_summary,
            "counts": counts,
            "usage": usage,
            "pytest_exit": exit_code,
        })

        # Early stop conditions
        attempted = passed + counts.get("failed", 0) + counts.get("errors", 0)
        if passed > best_pass:
            best_pass = passed
            best_summary = clean_summary
        if attempted > 0 and passed == attempted:
            print("  -> 100% pass, stopping")
            break
        if iter_n >= 2 and iterations[-1]["counts"].get("passed", 0) <= \
                iterations[-2]["counts"].get("passed", 0):
            print("  -> no improvement vs prior iter, stopping")
            break

        prior_failure_log = sanitized

    # Emit final result JSON
    total_in = sum(it["usage"].get("input_tokens", 0) for it in iterations)
    total_out = sum(it["usage"].get("output_tokens", 0) for it in iterations)
    total_cache_r = sum(it["usage"].get("cache_read_input_tokens", 0) for it in iterations)
    total_cache_w = sum(it["usage"].get("cache_creation_input_tokens", 0) for it in iterations)
    total_elapsed = sum(it["elapsed_s"] for it in iterations)

    result = {
        "repo": args.repo,
        "branch": args.branch,
        "model": MODEL,
        "max_iters": args.max_iters,
        "iters_run": len(iterations),
        "best_pass": best_pass,
        "best_summary": best_summary,
        "iterations": iterations,
        "totals": {
            "input_tokens": total_in,
            "output_tokens": total_out,
            "cache_read_input_tokens": total_cache_r,
            "cache_creation_input_tokens": total_cache_w,
            "elapsed_s": round(total_elapsed, 1),
        },
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{args.repo}_reflexion_sonnet.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nbest: {best_summary}")
    print(f"result -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
