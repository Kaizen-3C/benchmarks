"""Recompose code from ADRs + contracts + oracles (no source peeking).

Phase 2: real generator — reads ONLY `spec/<lib>/{adrs,contracts,oracles}/`
and emits a complete source tree to `output_dir/<lib>/`. The recomposer
must NOT see the original implementation (that would rig the round-trip;
see benchmarks/round_trip/PLAN.md "Recomposer view of ADRs: strict").

Run standalone:
    python benchmarks/round_trip/recompose_from_adrs.py wcwidth
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path

_COMMIT0_BASELINES = (
    Path(__file__).resolve().parent.parent / "commit0" / "baselines"
)
if str(_COMMIT0_BASELINES) not in sys.path:
    sys.path.insert(0, str(_COMMIT0_BASELINES))

from _llm import LLMClient, cost, DEFAULT_MODELS  # noqa: E402


_RECOMPOSE_INSTRUCTIONS = """\
You are reading a complete specification for a Python library (manifest +
import map + re-exports + ADRs + contracts + oracles, prepared by a
separate Decomposer) and producing a working Python source tree that
satisfies the spec.

You have NEVER seen the original library's source. The spec is your only
input. If the spec under-specifies something (e.g., refers to data tables
without enumerating them), use standard-library / well-known patterns
that satisfy the spec's behavioural oracles. Prefer correctness over
implementation tricks; we will measure your output against the original
test suite.

Emit a single response composed of named sections, each delimited by:

    === <relative/path> ===
    <content>

Use these path conventions:

* `<lib>/__init__.py` — the package root, re-exporting public API.
* `<lib>/<module>.py` — implementation files (one per logical module
  documented in the contracts).

The package directory is the library name (you'll see it in the contracts).
Match the public API exactly: function names, signatures, return types.

CRITICAL — read the spec artifacts in this order and follow them exactly:

1. **manifest.json** tells you the package name, version, dependencies,
   and which module files to create. Create EVERY file listed.
2. **reexports.json** tells you exactly what `__init__.py` must re-export.
   Copy these import lines VERBATIM — the test suite does
   `from <pkg> import X` and will fail if X is not re-exported.
3. **import_map.json** tells you the intra-package import structure.
   Every `from .X import Y` listed must appear in the corresponding file.
   Getting relative imports wrong is the #1 cause of test collection
   failure.
4. **contracts** define the public API signatures.
5. **oracles** define expected behaviour.
6. **ADRs** document design decisions to guide your implementation.

Constraints:

1. Pure Python ≥3.8. No external dependencies beyond the Python standard
   library, unless manifest.json lists them in `install_requires`.
2. Public functions must accept and return exactly the types the contracts
   specify. Names must match exactly (the test suite imports by name).
3. Behavioural oracles are the ground truth — every oracle's
   (input -> expected) pair must hold.
4. If the spec mentions a data table without enumerating it, derive the
   table from `unicodedata` (or analogous stdlib source). The oracle
   pairs will tell you whether you got it right.
5. Do not invent public API beyond what the contracts list — the
   Coverage gate will flag extras as drift.
6. Every module in import_map.json must be a real file. Every relative
   import listed must resolve. Missing files = ImportError = Q1 = 0.

Do not emit any preamble, markdown, or commentary outside the
`=== ... ===` blocks.
"""


def _write_text(path: Path, text: str) -> None:
    """UTF-8 + LF newlines — Windows→Linux-container safe."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


_RUNNABLE_ARTIFACTS = ("manifest.json", "import_map.json", "reexports.json")


def _gather_spec(spec_dir: Path) -> tuple[str, dict[str, int]]:
    """Concatenate spec contents into a single string for the LLM.

    Returns (spec_text, file_counts).
    """
    counts = {"adrs": 0, "contracts": 0, "oracles": 0, "runnable": 0}
    parts: list[str] = []

    # Runnable-spec artifacts first (manifest, import_map, reexports).
    for name in _RUNNABLE_ARTIFACTS:
        f = spec_dir / name
        if f.is_file():
            try:
                text = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = f.read_text(encoding="latin-1")
            parts.append(f"### SPEC: {name}\n{text}\n")
            counts["runnable"] += 1

    for sub in ("adrs", "contracts", "oracles"):
        sub_dir = spec_dir / sub
        if not sub_dir.is_dir():
            continue
        for f in sorted(sub_dir.rglob("*")):
            if f.is_dir():
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = f.read_text(encoding="latin-1")
            rel = f.relative_to(spec_dir).as_posix()
            parts.append(f"### SPEC: {rel}\n{text}\n")
            counts[sub] = counts.get(sub, 0) + 1
    header = (
        f"# Library specification\n\n"
        f"Runnable artifacts: {counts['runnable']}, "
        f"ADRs: {counts['adrs']}, contracts: {counts['contracts']}, "
        f"oracles: {counts['oracles']}\n\n"
    )
    return header + "\n".join(parts), counts


_SECTION_RE = re.compile(r"^=== (?P<path>[^=]+?) ===\s*$", re.MULTILINE)


def _strip_code_fence(text: str) -> str:
    """If the section content is wrapped in ```python ... ``` (or ``` ... ```),
    strip the fence so we write valid Python.
    """
    text = text.strip()
    fence_re = re.compile(r"^```[a-zA-Z0-9_+-]*\n(.*?)\n```\s*$", re.DOTALL)
    m = fence_re.match(text)
    if m:
        return m.group(1)
    return text


def _parse_response(response: str) -> dict[str, str]:
    """Split LLM response on `=== path ===` markers; strip code fences."""
    matches = list(_SECTION_RE.finditer(response))
    if not matches:
        return {}
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        path = m.group("path").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(response)
        content = _strip_code_fence(response[start:end])
        out[path] = content
    return out


def recompose_from_adrs(
    lib: str,
    spec_dir: Path,
    output_dir: Path,
    provider: str = "anthropic",
    model: str | None = None,
    clean: bool = True,
    timeout: float | None = None,
) -> dict:
    """Emit `output_dir/<lib>/` from `spec_dir/<lib>/`.

    Returns: {cost_usd, elapsed_s, files_emitted, model, provider, usage,
              parse_warning?}.
    """
    t0 = time.time()
    lib_spec = spec_dir / lib
    if not lib_spec.is_dir():
        return {
            "cost_usd": 0.0, "elapsed_s": 0.0, "files_emitted": 0,
            "error": f"spec_dir missing: {lib_spec}",
        }

    lib_out = output_dir / lib
    if clean and lib_out.exists():
        shutil.rmtree(lib_out)
    lib_out.mkdir(parents=True, exist_ok=True)

    spec_block, _counts = _gather_spec(lib_spec)
    if not spec_block.strip():
        return {
            "cost_usd": 0.0, "elapsed_s": 0.0, "files_emitted": 0,
            "error": f"empty spec: {lib_spec}",
        }

    client_kwargs = {"timeout": timeout} if timeout is not None else {}
    client = LLMClient(provider, model, **client_kwargs)
    response, usage = client.call(_RECOMPOSE_INSTRUCTIONS, spec_block)
    spend = cost(provider, usage)

    sections = _parse_response(response)
    parse_warning = None
    files_emitted = 0
    if not sections:
        _write_text(lib_out / "RAW_RECOMPOSE_RESPONSE.md", response)
        parse_warning = "no `=== path ===` sections found; saved raw response"
    else:
        for rel_path, content in sections.items():
            # Refuse paths that would escape the output dir (defense in depth).
            if rel_path.startswith(("/", "..")) or ".." in rel_path.split("/"):
                continue
            # Strip a leading `<lib>/` if present so we write into lib_out
            # rather than lib_out/<lib>/.
            normalized = rel_path
            if normalized.startswith(f"{lib}/"):
                normalized = normalized[len(lib) + 1:]
            elif normalized == lib:
                continue  # bare `<lib>` with no file; skip
            _write_text(lib_out / normalized, content)
            files_emitted += 1

    elapsed = round(time.time() - t0, 3)
    result: dict = {
        "cost_usd": round(spend, 4),
        "elapsed_s": elapsed,
        "files_emitted": files_emitted,
        "model": client.model,
        "provider": provider,
        "usage": usage,
    }
    if parse_warning:
        result["parse_warning"] = parse_warning
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lib", help="commit0-lite library name (e.g., wcwidth)")
    parser.add_argument(
        "--spec-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "spec",
        help="Root containing <lib>/. Default: benchmarks/round_trip/spec/",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "recomposed",
        help="Root for recomposed/<lib>/. Default: benchmarks/round_trip/recomposed/",
    )
    parser.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--no-clean", action="store_true",
        help="Don't delete pre-existing recomposed/<lib>/ before writing.",
    )
    args = parser.parse_args()

    result = recompose_from_adrs(
        args.lib, args.spec_dir, args.output_dir, args.provider, args.model,
        clean=not args.no_clean,
    )
    print(f"recompose {args.lib}: {result}")
    return 0 if "error" not in result else 2


if __name__ == "__main__":
    sys.exit(main())
