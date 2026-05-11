"""Q4 v2 — Line Derivability via Haiku.

For each non-trivial line of original source code, ask: "could this line be
reasonably derived from the spec alone?" Aggregate the yes-fraction across
all candidate lines as the v2 information-loss metric.

Why this matters (per the Phase 2 pilot findings, 2026-05-06):
  - v1 (symbol-name coverage) is too uniform: mean Q4 = 0.90 across 13 libs;
    it doesn't discriminate between libraries with high vs. low fidelity.
  - Q4 needs to measure *implementation* derivability, not just *naming* —
    which is a Haiku-shaped task: per-spec-section yes/no, simple judgement.

Cost target: Haiku is ~10x cheaper than Sonnet on input and ~10x on output.
Expected per-lib cost: ~$0.05 (one call per source file with cached spec).
For the 16 commit0-lite libs: ~$0.80 total. (vs ~$8 if we used Sonnet.)

Tool routing: this is the **Haiku** slot per the kaizen-delta convention.
Decompose / Recompose stay Sonnet; this metric uses Haiku for cost reasons
and because the per-line yes/no judgement doesn't need stronger reasoning.

Compatibility: returns the same shape as q4_information_loss (the v1 module),
so a runner can swap them. The runner registers v1 as `q4_information_loss`
and v2 as `q4_line_derivability` in metrics/__init__.py — both run, both
report, separate values.
"""

from __future__ import annotations

import ast
import json
import re
import sys
import time
from pathlib import Path

_COMMIT0_BASELINES = (
    Path(__file__).resolve().parents[2] / "commit0" / "baselines"
)
if str(_COMMIT0_BASELINES) not in sys.path:
    sys.path.insert(0, str(_COMMIT0_BASELINES))

from _llm import LLMClient  # noqa: E402

# --- Haiku pricing (locally-defined; not in _llm.py's cost() at time of writing) ---
# Anthropic Claude Haiku 4 list pricing as of 2026-05.
HAIKU_INPUT = 0.25       # $/MTok
HAIKU_OUTPUT = 1.25      # $/MTok
HAIKU_CACHE_READ = 0.025
HAIKU_CACHE_WRITE = 0.30

DEFAULT_HAIKU_MODEL = "claude-haiku-4-5"

_SKIP_DIR_PARTS = {".git", ".tox", "__pycache__", "build", "dist",
                   ".pytest_cache", ".mypy_cache", "tests", "test", "testing"}

# Lines we skip up front (no need to spend a Haiku judgement on them).
# Trivial = blank, comment-only, or a basic import.
_TRIVIAL_LINE_RE = re.compile(
    r"""
    ^\s*$                          # blank
    | ^\s*\#                       # comment-only
    | ^\s*from\s+__future__         # __future__ imports
    | ^\s*import\s+\w+(?:\.\w+)*\s*$    # bare `import x`
    | ^\s*from\s+\w[\w.]*\s+import\s   # `from X import Y` (allow simple)
    """,
    re.VERBOSE,
)


def _is_trivial_line(line: str) -> bool:
    return bool(_TRIVIAL_LINE_RE.match(line))


_INSTRUCTIONS = """\
You are checking whether a Python library's source code can be reconstructed
from its specification (ADRs + contracts + oracles).

The full specification was given to you in the cached context above. Below
is a set of numbered lines from ONE source file in the original library.
For each line, decide:

  "Y" — this line could be reasonably derived from the spec alone (no source).
        Includes: function/class definitions named in the spec; control-flow
        lines (if/for/while/try) implied by the documented algorithm;
        docstrings paraphrasing the spec; simple list/dict literals listed
        in oracles; return statements that follow obviously from contract.

  "N" — this line could NOT be derived from the spec alone.
        Includes: magic numbers, specific algorithmic constants, private
        helpers whose existence isn't implied by public API, library-internal
        cleverness not described anywhere, lines that contradict the spec.

Return a JSON object exactly of this shape — no prose, no markdown:

  {"verdicts": [{"line": <int>, "v": "Y" | "N"}, ...]}

Only return verdicts for the line numbers you were given. Don't invent
new lines. Be honest — if half the lines aren't in the spec, mark them N."""


def _spec_text(spec_dir: Path) -> str:
    """Concatenate adrs/contracts/oracles into one text block (the cached prefix)."""
    parts: list[str] = []
    for sub in ("adrs", "contracts", "oracles"):
        sub_dir = spec_dir / sub
        if not sub_dir.is_dir():
            continue
        for f in sorted(sub_dir.rglob("*")):
            if f.is_dir() or f.name.startswith("."):
                continue
            try:
                parts.append(f"### SPEC: {f.relative_to(spec_dir).as_posix()}\n")
                parts.append(f.read_text(encoding="utf-8"))
                parts.append("\n")
            except UnicodeDecodeError:
                parts.append(f.read_text(encoding="latin-1"))
    return "".join(parts)


def _candidate_lines(file_text: str) -> list[tuple[int, str]]:
    """Number the file lines, drop trivials, return (lineno, content) pairs."""
    out: list[tuple[int, str]] = []
    for i, raw in enumerate(file_text.splitlines(), start=1):
        if _is_trivial_line(raw):
            continue
        out.append((i, raw))
    return out


def _file_block(rel_path: str, candidate_lines: list[tuple[int, str]]) -> str:
    """Render the per-file prompt block: file label + numbered candidate lines."""
    parts = [f"### FILE: {rel_path}\n```python"]
    for lineno, content in candidate_lines:
        parts.append(f"{lineno:5d}  {content}")
    parts.append("```\n")
    return "\n".join(parts)


def _haiku_cost(usage: dict) -> float:
    """Cost from a usage dict produced by LLMClient.call() at Haiku rates."""
    return (
        usage.get("input", 0) * HAIKU_INPUT
        + usage.get("cache_read", 0) * HAIKU_CACHE_READ
        + usage.get("cache_write", 0) * HAIKU_CACHE_WRITE
        + usage.get("output", 0) * HAIKU_OUTPUT
    ) / 1_000_000


_VERDICT_RE = re.compile(r'\{\s*"line"\s*:\s*(\d+)\s*,\s*"v"\s*:\s*"([YN])"\s*\}')


def _parse_verdicts(response: str) -> dict[int, str]:
    """Extract {lineno: 'Y'|'N'} from the LLM response.

    Tolerant: tries strict JSON first, falls back to regex if the LLM wraps
    the JSON in prose or markdown.
    """
    # Try strict JSON.
    try:
        # Find a JSON object inside the response (LLM may add prose).
        m = re.search(r'\{[\s\S]*"verdicts"[\s\S]*\}', response)
        if m:
            obj = json.loads(m.group(0))
            verdicts = {int(v["line"]): v["v"] for v in obj.get("verdicts", [])}
            if verdicts:
                return verdicts
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass
    # Regex fallback.
    return {int(lineno): v for lineno, v in _VERDICT_RE.findall(response)}


def compute(original_dir: Path, recomposed_dir: Path, **kwargs) -> dict:
    """Q4 v2 — Haiku-judged line derivability.

    kwargs:
      spec_dir: required, path to spec/<lib>/
      model:    optional, override the default Haiku model id
      timeout:  optional, per-LLM-call timeout (default: LLMClient default)
    """
    spec_dir: Path | None = kwargs.get("spec_dir")
    if not spec_dir or not Path(spec_dir).is_dir():
        return {
            "metric": "q4_line_derivability", "value": None,
            "detail": {"error": f"spec_dir missing: {spec_dir}"},
        }
    if not original_dir.is_dir():
        return {
            "metric": "q4_line_derivability", "value": None,
            "detail": {"error": f"original_dir missing: {original_dir}"},
        }

    lib_name = recomposed_dir.name if recomposed_dir else None
    pkg_in_original = (original_dir / lib_name) if lib_name else None
    orig_root = (
        pkg_in_original if pkg_in_original and pkg_in_original.is_dir()
        else original_dir
    )

    spec_block = _spec_text(Path(spec_dir))
    if not spec_block.strip():
        return {
            "metric": "q4_line_derivability", "value": None,
            "detail": {"error": f"spec text empty under {spec_dir}"},
        }

    model = kwargs.get("model") or DEFAULT_HAIKU_MODEL
    timeout = kwargs.get("timeout")
    client_kwargs = {"timeout": timeout} if timeout is not None else {}
    client = LLMClient("anthropic", model, **client_kwargs)

    t0 = time.time()
    total_cost = 0.0
    total_verdicts: dict[str, dict[int, str]] = {}
    file_stats: list[dict] = []
    errors: list[str] = []

    for py in sorted(orig_root.rglob("*.py")):
        if any(p in _SKIP_DIR_PARTS for p in py.parts):
            continue
        if py.name in {"setup.py", "conftest.py"} or py.name.startswith("test_"):
            continue
        try:
            file_text = py.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            file_text = py.read_text(encoding="latin-1")
        candidates = _candidate_lines(file_text)
        if not candidates:
            continue

        rel_path = py.relative_to(orig_root).as_posix()
        prompt = _file_block(rel_path, candidates)

        try:
            response, usage = client.call(_INSTRUCTIONS + "\n\n" + prompt, spec_block)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{rel_path}: {type(e).__name__}: {e}")
            continue

        cost = _haiku_cost(usage)
        total_cost += cost
        verdicts = _parse_verdicts(response)
        total_verdicts[rel_path] = verdicts

        n_total = len(candidates)
        n_judged = len(verdicts)
        n_yes = sum(1 for v in verdicts.values() if v == "Y")
        file_stats.append({
            "file": rel_path,
            "candidate_lines": n_total,
            "lines_judged": n_judged,
            "lines_derivable": n_yes,
            "fraction_derivable": (n_yes / n_judged) if n_judged else None,
            "cost_usd": round(cost, 5),
        })

    # Aggregate: total derivable / total judged, across all files.
    total_judged = sum(s["lines_judged"] for s in file_stats)
    total_yes = sum(s["lines_derivable"] for s in file_stats)
    value = (total_yes / total_judged) if total_judged else None

    return {
        "metric": "q4_line_derivability",
        "value": round(value, 4) if value is not None else None,
        "detail": {
            "model": model,
            "files_judged": len(file_stats),
            "total_candidate_lines": sum(s["candidate_lines"] for s in file_stats),
            "total_lines_judged": total_judged,
            "total_lines_derivable": total_yes,
            "cost_usd": round(total_cost, 5),
            "elapsed_s": round(time.time() - t0, 2),
            "per_file": file_stats,
            "errors": errors,
        },
    }
