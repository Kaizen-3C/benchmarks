"""Decompose a working library into ADRs + contracts + oracles.

Phase 2: real prompt that walks `repo_dir/<lib>/` source files and emits
ADRs/contracts/oracles into `output_dir/<lib>/{adrs,contracts,oracles}/`.

The LLM call uses `_llm.LLMClient` with the source-tree as the cached_block
(so re-running with model swap or re-doing recompose only doesn't repay
input tokens). The response is parsed via the simple `=== path ===`
delimiter scheme so the LLM emits one structured artifact.

Run standalone:
    python benchmarks/round_trip/decompose_from_reference.py wcwidth
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path

# Reuse the commit0 baseline's LLM client + cost helper.
_COMMIT0_BASELINES = (
    Path(__file__).resolve().parent.parent / "commit0" / "baselines"
)
if str(_COMMIT0_BASELINES) not in sys.path:
    sys.path.insert(0, str(_COMMIT0_BASELINES))

from _llm import LLMClient, cost, DEFAULT_MODELS  # noqa: E402

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from dynamic_intent import capture_intent  # noqa: E402


DEFAULT_REPOS_ROOT = Path.home() / "kaizen-commit0" / "repos"

# Files we deliberately exclude when assembling the source-tree block.
_EXCLUDE_DIR_NAMES = {".git", ".tox", "__pycache__", "build", "dist", ".pytest_cache", ".mypy_cache"}
_EXCLUDE_FILE_PREFIXES = ("test_",)
_EXCLUDE_FILE_NAMES = {"conftest.py", "setup.py"}

# Per-file size cap: data-table files (e.g., wcwidth/table_wide.py) can be
# many thousands of lines. Trying to round-trip those through ADRs is not
# the point of the benchmark — they're data, not logic. Truncate with a
# clear marker so the LLM knows the file is data and the recomposer can
# generate equivalent lookups instead of memorizing the table.
_MAX_FILE_BYTES = 30_000

_DECOMPOSE_INSTRUCTIONS = """\
You are reading the complete source of a Python library and producing a
specification that another engineer (with no access to this source) could
use to rebuild a functionally-equivalent library FROM SCRATCH.

The rebuilt library must be RUNNABLE — tests must be able to import it and
execute. This means the spec must capture not just WHAT the code does but
HOW to make it importable and installable.

Emit a single response composed of named sections, each delimited by:

    === <relative/path> ===
    <content>

Use these path conventions strictly:

* `manifest.json` — (REQUIRED, emit FIRST) a JSON object with:
  - `"package_name"`: the importable package name (directory name)
  - `"version"`: the version string
  - `"install_requires"`: list of pip dependencies needed at runtime
    (e.g., `["cryptography>=3.4.0"]`). Use `[]` if pure stdlib.
  - `"python_requires"`: minimum Python version (e.g., `">=3.8"`)
  - `"modules"`: list of `.py` filenames in the package (e.g.,
    `["__init__.py", "core.py", "utils.py"]`)

* `import_map.json` — (REQUIRED) a JSON object mapping each module file
  to its intra-package imports. For example:
  ```
  {
    "__init__.py": {"from .core import MyClass, my_func": "re-export"},
    "core.py": {"from .utils import helper": "internal"},
    "utils.py": {}
  }
  ```
  Every `from .X import Y` and `from <pkg>.X import Y` MUST appear here.
  This is critical — the recomposer cannot guess relative import paths.

* `reexports.json` — (REQUIRED) a JSON object describing exactly what
  `__init__.py` re-exports. Format:
  ```
  {
    "from .module import Name": ["Name1", "Name2"],
    "__all__": ["Name1", "Name2"],
    "__version__": "1.0.0"
  }
  ```
  If `__init__.py` does `from .api import encode, decode`, that line
  MUST appear here verbatim. Missing re-exports break `from pkg import X`
  in the test suite.

* `adrs/ADR-NNNN-<slug>.md` — Architectural Decision Records. Each ADR
  documents a SINGLE decision in prose. Examples of decisions worth an ADR:
  why a cache is used and what eviction policy, what data structure backs
  a lookup, what the public API guarantees about thread safety, how
  versioning works. Make decisions concrete (numbers, library names,
  algorithms) — vague ADRs (e.g., "we use a cache" with no params) will
  fail the Specificity gate.

* `contracts/<Name>.md` — public-API contracts. One contract per public
  module. List every public function/class with its signature, type
  annotations, and a one-line behavioural summary. Cross-reference ADRs
  by ID when a contract decision is documented elsewhere.

* `oracles/<topic>.jsonl` — behaviour oracles. Each line is a JSON object
  with `{"name": "...", "input": ..., "expected": ...}` describing one
  expected (input, output) pair. Aim for 5–20 oracles per public function;
  include happy-path AND edge cases.

The spec must be self-contained. Do NOT include code blocks longer than
~3 lines (the Implementation-leak gate will fail otherwise — bodies are
the recomposer's job, not the spec's). Function signatures and small
illustrative snippets are fine.

If the source contains large data tables (Unicode ranges, frequency
tables, etc.), describe their shape and provenance in an ADR. Do NOT
embed the tables in the spec.

Order your sections: manifest.json first, import_map.json second,
reexports.json third, then ADRs, contracts, oracles.

Do not emit any preamble or commentary outside the `=== ... ===` blocks.
"""


_PACKAGING_FILES = ("setup.py", "setup.cfg", "pyproject.toml", "requirements.txt")


def _gather_packaging(repo_dir: Path) -> str:
    """Collect packaging/dependency metadata the LLM needs to emit manifest.json."""
    parts: list[str] = []
    for name in _PACKAGING_FILES:
        p = repo_dir / name
        if p.is_file():
            raw = p.read_bytes()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1", errors="replace")
            if len(text) > 5_000:
                text = text[:5_000] + "\n# ...truncated\n"
            parts.append(f"### PACKAGING: {name}\n```\n{text}\n```\n")
    if not parts:
        return ""
    return "# Packaging metadata\n\n" + "\n".join(parts) + "\n"


def _write_text(path: Path, text: str) -> None:
    """UTF-8 + LF newlines — Windows→Linux-container safe."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _gather_source(repo_dir: Path) -> tuple[str, int]:
    """Concatenate library source into a single string, with file delimiters.

    Returns (source_text, files_included).
    """
    parts: list[str] = []
    files_included = 0
    for py in sorted(repo_dir.rglob("*.py")):
        if any(part in _EXCLUDE_DIR_NAMES for part in py.parts):
            continue
        if py.name in _EXCLUDE_FILE_NAMES:
            continue
        if any(py.name.startswith(p) for p in _EXCLUDE_FILE_PREFIXES):
            continue
        # Skip files inside a tests/ directory at any depth.
        if any(p in {"tests", "test", "testing"} for p in py.parts):
            continue
        rel = py.relative_to(repo_dir).as_posix()
        try:
            raw = py.read_bytes()
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")
        if len(text) > _MAX_FILE_BYTES:
            text = (
                text[:_MAX_FILE_BYTES]
                + f"\n\n# ...truncated ({len(text) - _MAX_FILE_BYTES:,} more bytes; "
                "this file is data; describe shape+provenance in an ADR)\n"
            )
        parts.append(f"### FILE: {rel}\n```python\n{text}\n```\n")
        files_included += 1
    header = f"# Library source ({files_included} files)\n\n"
    return header + "\n".join(parts), files_included


_SECTION_RE = re.compile(r"^=== (?P<path>[^=]+?) ===\s*$", re.MULTILINE)


def _parse_response(response: str) -> dict[str, str]:
    """Split LLM response on `=== path ===` markers.

    Returns dict: relative_path -> content.
    """
    matches = list(_SECTION_RE.finditer(response))
    if not matches:
        return {}
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        path = m.group("path").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(response)
        content = response[start:end].strip()
        out[path] = content
    return out


def decompose_from_reference(
    lib: str,
    output_dir: Path,
    provider: str = "anthropic",
    model: str | None = None,
    repos_root: Path | None = None,
    clean: bool = True,
    timeout: float | None = None,
) -> dict:
    """Emit `output_dir/<lib>/{adrs,contracts,oracles}/` from a working lib.

    Args:
      lib: commit0-lite library name (e.g., "wcwidth").
      output_dir: root for `<lib>/` spec dirs (default: round_trip/spec/).
      provider: "anthropic" or "openai".
      model: provider-specific model id; defaults from _llm.DEFAULT_MODELS.
      repos_root: where the library checkouts live (default: ~/kaizen-commit0/repos/).
      clean: if True, delete any pre-existing `output_dir/<lib>/` before writing.

    Returns: {cost_usd, elapsed_s, files_in_spec, model, provider, usage,
              parse_warning?}.
    """
    t0 = time.time()
    repos_root = repos_root or DEFAULT_REPOS_ROOT
    repo_dir = repos_root / lib
    if not repo_dir.is_dir():
        return {
            "cost_usd": 0.0, "elapsed_s": 0.0, "files_in_spec": 0,
            "error": f"repo_dir missing: {repo_dir}",
        }

    spec_dir = output_dir / lib
    if clean and spec_dir.exists():
        shutil.rmtree(spec_dir)
    for sub in ("adrs", "contracts", "oracles"):
        (spec_dir / sub).mkdir(parents=True, exist_ok=True)

    source_block, files_seen = _gather_source(repo_dir)
    if files_seen == 0:
        return {
            "cost_usd": 0.0, "elapsed_s": 0.0, "files_in_spec": 0,
            "error": f"no source files in {repo_dir}",
        }

    packaging_block = _gather_packaging(repo_dir)
    try:
        intent = capture_intent(repo_dir)
        intent_block = (
            "# Required test-reach surface (dynamic intent capture)\n\n"
            "This block was captured by AST-walking the test suite for "
            "attribute chains rooted at the package. Every symbol listed "
            "here MUST be present in the spec — either in `reexports.json` "
            "or in a contract — or the recomposed code WILL fail at test "
            "collection time. This addresses the attribute-access ceiling "
            "(see ADR-0063 §5.4).\n\n"
            + intent["summary"] + "\n"
        )
    except Exception:
        intent = None
        intent_block = ""
    combined_block = intent_block + packaging_block + source_block

    client_kwargs = {"timeout": timeout} if timeout is not None else {}
    client = LLMClient(provider, model, **client_kwargs)
    response, usage = client.call(_DECOMPOSE_INSTRUCTIONS, combined_block)
    spend = cost(provider, usage)

    sections = _parse_response(response)
    parse_warning = None
    if not sections:
        # Save the raw response so the engineer can inspect.
        _write_text(spec_dir / "RAW_DECOMPOSE_RESPONSE.md", response)
        parse_warning = "no `=== path ===` sections found; saved raw response"
    else:
        _ALLOWED_TOPLEVEL = {"manifest.json", "import_map.json", "reexports.json"}
        for rel_path, content in sections.items():
            if rel_path in _ALLOWED_TOPLEVEL:
                pass  # write directly under spec_dir
            elif not rel_path.startswith(("adrs/", "contracts/", "oracles/")):
                rel_path = f"oracles/_unrouted_{rel_path.replace('/', '_')}"
            _write_text(spec_dir / rel_path, content)

    elapsed = round(time.time() - t0, 3)
    files_written = len(sections)
    result: dict = {
        "cost_usd": round(spend, 4),
        "elapsed_s": elapsed,
        "files_in_spec": files_written,
        "files_in_source": files_seen,
        "model": client.model,
        "provider": provider,
        "usage": usage,
    }
    if parse_warning:
        result["parse_warning"] = parse_warning
    if intent is not None:
        result["intent_capture"] = {
            "package_root": intent["package_root"],
            "static_attr_chains": len(intent["static_attr_chains"]),
            "runtime_modules": len(intent["runtime_modules"]),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lib", help="commit0-lite library name (e.g., wcwidth)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "spec",
        help="Root directory for spec/<lib>/. Default: benchmarks/round_trip/spec/",
    )
    parser.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--no-clean", action="store_true",
        help="Don't delete pre-existing spec/<lib>/ before writing.",
    )
    args = parser.parse_args()

    result = decompose_from_reference(
        args.lib, args.output_dir, args.provider, args.model,
        clean=not args.no_clean,
    )
    print(f"decompose {args.lib}: {result}")
    return 0 if "error" not in result else 2


if __name__ == "__main__":
    sys.exit(main())
