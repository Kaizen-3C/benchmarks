"""Single-shot Claude Sonnet 4.6 baseline for one commit0 library.

Reads:
  - <repo>/spec.pdf.bz2  (the spec, as a bz2-compressed PDF)
  - All Python files inside <repo>/<package>/ that contain stubs (`pass`-bodies)

Sends one Anthropic API call with the PDF + concatenated stub files,
asks for filled-in implementations back as fenced code blocks tagged
with the file path, parses the response, writes files back.

Run:
  python baselines/single_shot_sonnet.py <repo_name>

E.g.:  python baselines/single_shot_sonnet.py wcwidth
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

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16000
MAX_STUB_FILE_BYTES = 30_000  # truncate monster data files in the prompt
WORKSPACE = Path.home() / "kaizen-commit0"
RESULTS_DIR = WORKSPACE / "baselines" / "results"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


EXCLUDE_DIRS = {
    "tests", "test", "testing", "docs", "doc", "examples", "example",
    "bin", "build", "dist", "scripts", "site-packages", ".git", ".venv",
    ".tox", ".pytest_cache", "__pycache__", "artwork", "code_templates",
    ".github",
}


def _candidate_package_dirs(repo_dir: Path) -> list[Path]:
    """Find import-time package directories at depth ≤ 2 from repo root."""
    candidates: list[Path] = []
    # Depth 1: standard `<repo>/<pkg>/__init__.py`
    for p in sorted(repo_dir.iterdir()):
        if (
            p.is_dir()
            and p.name not in EXCLUDE_DIRS
            and not p.name.startswith(".")
            and (p / "__init__.py").exists()
        ):
            candidates.append(p)
    # Depth 2: `src/<pkg>/__init__.py` (PEP-517 src layout)
    src = repo_dir / "src"
    if src.is_dir():
        for p in sorted(src.iterdir()):
            if p.is_dir() and (p / "__init__.py").exists() and p.name not in EXCLUDE_DIRS:
                candidates.append(p)
    return candidates


def discover_stub_files(repo_dir: Path) -> list[Path]:
    """Find Python source files (stubs to fill).

    Strategy:
      1. Standard depth-1 packages with __init__.py
      2. src/ layout
      3. Fallback: scan all .py files outside tests/docs/etc that contain
         either `pass` bodies or empty data containers — typical commit0 stubs.
    """
    files: list[Path] = []
    for pkg in _candidate_package_dirs(repo_dir):
        for py in sorted(pkg.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            files.append(py)

    if files:
        return files

    # Fallback: scan flat layouts. Only include .py files that *look* like
    # they're part of the importable package, not tests/scripts.
    for py in sorted(repo_dir.rglob("*.py")):
        if any(part in EXCLUDE_DIRS or part.startswith(".") for part in py.parts):
            continue
        # skip top-level setup.py / conftest.py / etc
        if py.parent == repo_dir and py.name in {"setup.py", "conftest.py", "noxfile.py"}:
            continue
        files.append(py)
    return files


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Best-effort PDF -> plain text. Falls back to empty string on failure."""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return ""
    from io import BytesIO
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        parts: list[str] = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n\n".join(parts).strip()
    except Exception as e:
        print(f"  [warn] PDF text extraction failed: {e}", file=sys.stderr)
        return ""


def _truncate(content: str, max_bytes: int) -> str:
    if len(content.encode("utf-8")) <= max_bytes:
        return content
    head = content[: max_bytes // 2]
    tail = content[-max_bytes // 2 :]
    return (
        head
        + "\n# ... [TRUNCATED FOR PROMPT — file is too large for single-shot baseline] ...\n"
        + tail
    )


def build_prompt(
    repo_name: str,
    stub_files: list[Path],
    repo_dir: Path,
    spec_text: str,
) -> str:
    parts = [
        f"You are filling in stubs for the Python library `{repo_name}`.",
        "",
        "=== SPECIFICATION ===",
        spec_text or "(spec PDF text extraction failed; rely on stub docstrings/signatures)",
        "",
        "=== INSTRUCTIONS ===",
        f"There are {len(stub_files)} source files below. Each shows its repo-relative path.",
        "Function bodies that contain only `pass` (or are otherwise empty stubs) need real implementations.",
        "Module-level data structures that are placeholders (empty dicts, empty tuples) need their full data.",
        "Files marked TRUNCATED were too large to send fully — infer the structure and emit your best version.",
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
        content = p.read_text(encoding="utf-8", errors="replace")
        content = _truncate(content, MAX_STUB_FILE_BYTES)
        parts.append(f"--- {rel} ---")
        parts.append(content)
        parts.append("")
    return "\n".join(parts)


CODE_BLOCK_RE = re.compile(
    r"```(?:python|py)?:([^\n`]+)\n(.*?)```",
    re.DOTALL,
)


def parse_response(text: str) -> dict[str, str]:
    """Return {relpath: file_content} extracted from fenced blocks."""
    result: dict[str, str] = {}
    for m in CODE_BLOCK_RE.finditer(text):
        relpath = m.group(1).strip()
        content = m.group(2)
        if not content.endswith("\n"):
            content += "\n"
        result[relpath] = content
    return result


def write_files(repo_dir: Path, files: dict[str, str]) -> list[str]:
    written: list[str] = []
    for relpath, content in files.items():
        target = repo_dir / relpath
        if not target.is_relative_to(repo_dir):
            print(f"  REFUSED (path escape): {relpath}", file=sys.stderr)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="")
        written.append(relpath)
    return written


def git(repo_dir: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", *args], cwd=repo_dir, capture_output=True, text=True, check=False
    )
    return (r.stdout + r.stderr).strip()


_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_PYTEST_FINAL_RE = re.compile(
    r"={3,}\s+((?:\d+\s+(?:passed|failed|skipped|error[s]?|warning[s]?|deselected|xfailed|xpassed)[, ]*)+).*?\sin\s+[\d.]+s\s+={3,}",
    re.IGNORECASE,
)


def _find_pytest_summary_in_output(output_text: str) -> str:
    """Return the canonical pytest final summary line, scanning bottom-up."""
    clean = _ANSI.sub("", output_text)
    for line in reversed(clean.splitlines()):
        if _PYTEST_FINAL_RE.search(line):
            return line.strip()
    return ""


# Per-library test directory selectors (pulled from
# wentingzhao/commit0_combined dataset metadata). For libs not listed here,
# default to the universal "tests" directory.
TEST_DIR_OVERRIDES = {
    "voluptuous": "voluptuous/tests",
    "chardet": ".",
    "portalocker": "portalocker_tests/",
}


def run_pytest_via_commit0(repo_name: str, branch: str) -> tuple[int, str]:
    """Invoke commit0 test for this repo on the given branch. Return (exit, summary).

    The summary is read from the on-disk test_output.txt (the truth) — not from
    the noisy commit0 stdout, which interleaves docker setup messages.
    """
    test_dir = TEST_DIR_OVERRIDES.get(repo_name, "tests")
    cmd = [
        "commit0", "test", repo_name, test_dir,
        "--branch", branch,
        "--backend", "local",
        "--timeout", "600",
    ]
    r = subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True)

    # Find the per-run test_output.txt that commit0 just produced.
    log_root = WORKSPACE / "logs" / "pytest" / repo_name / branch
    summary = ""
    if log_root.is_dir():
        per_run_dirs = sorted(
            (d for d in log_root.iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime,
        )
        if per_run_dirs:
            test_output = per_run_dirs[-1] / "test_output.txt"
            if test_output.exists():
                summary = _find_pytest_summary_in_output(
                    test_output.read_text(encoding="utf-8", errors="replace")
                )
    if not summary:
        summary = (r.stdout + r.stderr)[-500:]
    return r.returncode, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", help="commit0 library name, e.g. wcwidth")
    parser.add_argument("--branch", default="single_shot_sonnet")
    parser.add_argument("--no-test", action="store_true",
                        help="generate code only, don't run pytest")
    args = parser.parse_args()

    load_dotenv(Path("/mnt/c/RepoEx/Kaizen-delta/.env"))
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not in env after dotenv load", file=sys.stderr)
        return 2

    repo_dir = WORKSPACE / "repos" / args.repo
    if not repo_dir.is_dir():
        print(f"Repo not found: {repo_dir}", file=sys.stderr)
        return 2

    spec_bz2 = repo_dir / "spec.pdf.bz2"
    if not spec_bz2.exists():
        print(f"spec.pdf.bz2 not found in {repo_dir}", file=sys.stderr)
        return 2

    pdf_bytes = bz2.decompress(spec_bz2.read_bytes())
    print(f"[1/5] Spec PDF: {len(pdf_bytes)} bytes")
    spec_text = extract_pdf_text(pdf_bytes)
    print(f"      Spec text extracted: {len(spec_text)} chars")

    stub_files = discover_stub_files(repo_dir)
    print(f"[2/5] Found {len(stub_files)} source files")
    for f in stub_files:
        print(f"      {f.relative_to(repo_dir).as_posix()} ({f.stat().st_size} bytes)")
    if not stub_files:
        print("      ERROR: no source files found — bailing", file=sys.stderr)
        return 3

    prompt = build_prompt(args.repo, stub_files, repo_dir, spec_text)
    print(f"[3/5] Prompt: {len(prompt)} chars; sending to {MODEL}")

    client = Anthropic(timeout=600.0, max_retries=4)
    t0 = time.time()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - t0
    response = msg.content[0].text
    in_tokens = msg.usage.input_tokens
    out_tokens = msg.usage.output_tokens
    print(f"      Done in {elapsed:.1f}s; in_tokens={in_tokens} out_tokens={out_tokens}")
    print(f"      Stop reason: {msg.stop_reason}")

    files = parse_response(response)
    print(f"[4/5] Parsed {len(files)} code blocks from response")
    for relpath in files:
        print(f"      -> {relpath}")

    if not files:
        print("      (no code blocks parsed; saving raw response for inspection)")
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (RESULTS_DIR / f"{args.repo}_raw_response.txt").write_text(response, encoding="utf-8")
        return 1

    # Commit on a branch
    git(repo_dir, "checkout", "commit0")
    git(repo_dir, "branch", "-D", args.branch)
    git(repo_dir, "checkout", "-b", args.branch)
    written = write_files(repo_dir, files)
    git(repo_dir, "add", "-A")
    git(repo_dir, "commit", "-m", f"single-shot sonnet baseline ({MODEL})")
    print(f"      Committed {len(written)} files on branch '{args.branch}'")

    result: dict[str, object] = {
        "repo": args.repo,
        "branch": args.branch,
        "model": MODEL,
        "elapsed_s": round(elapsed, 2),
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "stop_reason": msg.stop_reason,
        "files_written": written,
    }

    if args.no_test:
        print("[5/5] --no-test set, skipping pytest")
    else:
        print(f"[5/5] Running commit0 test {args.repo} --branch {args.branch}")
        exit_code, summary = run_pytest_via_commit0(args.repo, args.branch)
        result["pytest_exit"] = exit_code
        result["pytest_summary"] = summary
        print(f"      pytest exit={exit_code}")
        print(f"      summary: {summary}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{args.repo}_single_shot_sonnet.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"      result -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
