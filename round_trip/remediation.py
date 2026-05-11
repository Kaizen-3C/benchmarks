"""Gate-failure -> spec-amendment loop.

Phase 3: given gate failures from a fresh decompose, emit an LLM call that
amends the spec so the next Recompose has a better starting point. The new
artifacts (manifest.json, import_map.json, reexports.json) cover the
"can't import" failures; remediation here addresses the residual gate
findings:

  - coverage: orphan symbols → add ADR/contract sections
  - specificity: vague spots → tighten ADR text
  - consistency: spec disagreements → reconcile
  - test_oracle_alignment: missing oracles → add rows
  - implementation_leak: leaked code → rewrite to prose

This is a single-pass, single-LLM-call loop. It writes amendments back into
spec_dir/<lib>/{adrs,contracts,oracles}/ and adds a remediation_log.md
documenting what changed.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

_COMMIT0_BASELINES = (
    Path(__file__).resolve().parent.parent / "commit0" / "baselines"
)
if str(_COMMIT0_BASELINES) not in sys.path:
    sys.path.insert(0, str(_COMMIT0_BASELINES))

from _llm import LLMClient, cost  # noqa: E402


_REMEDIATION_INSTRUCTIONS = """\
You are amending a Python library specification (manifest + ADRs +
contracts + oracles) to address findings from automated drift gates. The
spec was produced by a Decomposer; gates flagged residual problems that
will hurt the Recomposer. Your job: emit amendments that close the gaps.

You have NEVER seen the original library source. Work only from the
existing spec content and the gate failure list.

Emit a single response composed of named sections, each delimited by:

    === <relative/path> ===
    <content>

Path conventions (same as the Decomposer):

  - `adrs/ADR-NNNN-<slug>.md` — new ADR or REPLACEMENT for an existing one
  - `contracts/<Name>.md` — new contract or REPLACEMENT
  - `oracles/<topic>.jsonl` — APPEND to an existing file (one JSON object
    per line, no array wrapper)

If you replace an existing file, you must include ALL content (yours +
preserved original) — we overwrite, not merge.

If a runtime smoke-test traceback is provided, ADDRESS IT FIRST. The
traceback is the highest-signal failure: a real Python error from real
code. Trace the missing import / attribute / name back to its likely
source (manifest.json, import_map.json, reexports.json, or an ADR/contract
that should have surfaced it) and emit the amendment that fixes it.
Common patterns:

  - `ImportError: cannot import name 'X' from 'pkg.module'` → either `X`
    is missing from `manifest.json -> modules` (add it) or from the
    contract for `pkg.module` (add it). Update `reexports.json` if the
    import happens at package root.

  - `ModuleNotFoundError: No module named 'pkg.submod'` → add `submod.py`
    to `manifest.json -> modules` and emit a contract.

  - `AttributeError: module 'pkg' has no attribute 'X'` → `X` is missing
    from `reexports.json` for `__init__.py`.

For each gate failure category:

  * coverage: emit an ADR section that documents the orphan symbol's
    purpose and an entry in the relevant contract listing its signature.
    Use the symbol's source location hint to guide your prose.

  * specificity: emit a REPLACEMENT for the named ADR with concrete
    parameters (numbers, library names, algorithms) instead of vague
    phrasing.

  * consistency: emit a REPLACEMENT that reconciles the conflicting
    statements. Pick the version most consistent with the contracts.

  * test_oracle_alignment: APPEND oracle rows for the missing test
    behaviours. One JSON object per line in the named .jsonl file.

  * implementation_leak: emit a REPLACEMENT for the ADR with the leaked
    code block rewritten as prose / a short pseudocode summary
    (≤3 lines).

If a category has no failures, do not emit anything for it.

Do not emit any preamble, markdown, or commentary outside the
`=== ... ===` blocks.
"""


def _summarize_gate_failures(gate_results: dict[str, dict]) -> str:
    """Compact a gate_results dict into a prompt-sized failure block.

    Caps each gate's failures at 20 entries to keep the prompt bounded.
    """
    parts: list[str] = []
    for gate_name, gr in gate_results.items():
        if gr.get("pass"):
            continue
        failures = gr.get("failures", [])
        if not failures:
            continue
        capped = failures[:20]
        parts.append(f"## Gate: {gate_name} ({len(failures)} failures)")
        for i, f in enumerate(capped, 1):
            # Each gate has its own failure shape; render keys generically.
            kv = ", ".join(f"{k}={v!r}" for k, v in f.items() if k != "remediation")
            rem = f.get("remediation")
            line = f"{i}. {kv}"
            if rem:
                line += f"\n   suggested fix: {rem}"
            parts.append(line)
        if len(failures) > 20:
            parts.append(f"   ... and {len(failures) - 20} more")
        parts.append("")
    if not parts:
        return ""
    return "# Gate failures to address\n\n" + "\n".join(parts) + "\n"


def _gather_current_spec(spec_dir: Path) -> str:
    """Read the existing spec into a text block so the LLM has context."""
    parts: list[str] = []
    for top in ("manifest.json", "import_map.json", "reexports.json"):
        p = spec_dir / top
        if p.is_file():
            parts.append(f"### CURRENT: {top}\n{p.read_text(encoding='utf-8')}\n")
    for sub in ("adrs", "contracts", "oracles"):
        d = spec_dir / sub
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(spec_dir).as_posix()
            try:
                text = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = f.read_bytes().decode("latin-1", errors="replace")
            parts.append(f"### CURRENT: {rel}\n{text}\n")
    return "# Current specification\n\n" + "\n".join(parts) + "\n"


_SECTION_RE = re.compile(r"^=== (?P<path>[^=]+?) ===\s*$", re.MULTILINE)


def _parse_response(response: str) -> dict[str, str]:
    matches = list(_SECTION_RE.finditer(response))
    if not matches:
        return {}
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        path = m.group("path").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(response)
        out[path] = response[start:end].strip()
    return out


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write(text)


def remediate(
    gate_results: dict[str, dict],
    spec_dir: Path,
    provider: str = "anthropic",
    model: str | None = None,
    timeout: float | None = None,
    smoke_traceback: str | None = None,
) -> dict:
    """Run a single-pass spec amendment loop driven by failures.

    The driver is, in order of preference:
      1. `smoke_traceback` — runtime traceback from import / collect-only
         (when available, this is the highest-signal input).
      2. `gate_results` — static gate failures (fallback / supplementary).

    Returns: {cost_usd, elapsed_s, amendments_applied, model, provider, usage,
              skipped?, parse_warning?}.

    If both inputs are empty, returns immediately with skipped=True.
    """
    t0 = time.time()
    failures_block = _summarize_gate_failures(gate_results)
    smoke_block = ""
    if smoke_traceback:
        smoke_block = (
            "# Runtime smoke-test failure (highest priority)\n\n"
            "The recomposed package was staged and `python -c \"import "
            "<pkg>\"` (or `pytest --collect-only`) failed. Fix the spec so "
            "the next Recompose produces code that imports cleanly. The "
            "traceback below points at the exact missing/wrong symbol.\n\n"
            "```\n" + smoke_traceback.strip() + "\n```\n\n"
        )
    if not failures_block and not smoke_block:
        return {
            "cost_usd": 0.0, "elapsed_s": 0.0, "amendments_applied": 0,
            "skipped": True, "reason": "no failures to remediate",
        }
    if not spec_dir.is_dir():
        return {
            "cost_usd": 0.0, "elapsed_s": 0.0, "amendments_applied": 0,
            "error": f"spec_dir missing: {spec_dir}",
        }

    spec_block = _gather_current_spec(spec_dir)
    cached_block = spec_block + "\n\n" + smoke_block + failures_block

    client_kwargs = {"timeout": timeout} if timeout is not None else {}
    client = LLMClient(provider, model, **client_kwargs)
    response, usage = client.call(_REMEDIATION_INSTRUCTIONS, cached_block)
    spend = cost(provider, usage)

    sections = _parse_response(response)
    parse_warning = None
    amendments_applied = 0
    log_entries: list[str] = []
    if not sections:
        _write_text(spec_dir / "REMEDIATION_RAW_RESPONSE.md", response)
        parse_warning = "no `=== path ===` sections found; saved raw response"
    else:
        _ALLOWED_TOPLEVEL = {"manifest.json", "import_map.json", "reexports.json"}
        for rel_path, content in sections.items():
            if rel_path in _ALLOWED_TOPLEVEL:
                _write_text(spec_dir / rel_path, content)
                log_entries.append(f"REPLACED: {rel_path}")
            elif rel_path.startswith("oracles/"):
                # Oracles are append-only (one JSON object per line).
                _append_text(spec_dir / rel_path, content)
                log_entries.append(f"APPENDED: {rel_path}")
            elif rel_path.startswith(("adrs/", "contracts/")):
                # ADRs and contracts are replace-or-create.
                _write_text(spec_dir / rel_path, content)
                log_entries.append(f"WROTE: {rel_path}")
            else:
                log_entries.append(f"SKIPPED (bad path): {rel_path}")
                continue
            amendments_applied += 1

        log_path = spec_dir / "REMEDIATION_LOG.md"
        log_text = (
            f"# Remediation log\n\n"
            f"- model: {client.model}\n"
            f"- amendments applied: {amendments_applied}\n"
            f"- gate failures fed in: {sum(len(g.get('failures', [])) for g in gate_results.values() if not g.get('pass'))}\n\n"
            "## Changes\n\n"
            + "\n".join(f"- {entry}" for entry in log_entries)
            + "\n"
        )
        _write_text(log_path, log_text)

    elapsed = round(time.time() - t0, 3)
    result: dict = {
        "cost_usd": round(spend, 4),
        "elapsed_s": elapsed,
        "amendments_applied": amendments_applied,
        "model": client.model,
        "provider": provider,
        "usage": usage,
    }
    if parse_warning:
        result["parse_warning"] = parse_warning
    return result
