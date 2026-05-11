"""Stage 2.5: cross-model adversarial review of the Recompose artifact.

Inspired by ARIS (arXiv 2605.03042), which uses a reviewer from a different
model family to critique an executor's intermediate artifacts. We adapt the
pattern to round-trip Recompose:

    Sonnet (executor) recomposes spec/<lib>/ -> recomposed/<lib>/
    Opus   (reviewer) reads spec + recomposed code, emits a structured critique
    Sonnet (executor) re-recomposes with the critique injected into the spec
                       -> recomposed_reviewed/<lib>/

Goal: catch *plausible unsupported success* — cases where the recomposed
package compiles, imports, and collects tests cleanly but silently diverges
from the canonical contract on Q1 (test parity).

Targets the failure class observed in `results/deprecated_round_trip.json`
(Q1=0.643) and `results/pyjwt_round_trip.json` (Q1=0.807): smoke passes,
Q3 surface parity is high, yet a meaningful fraction of canonical tests
fail.

Usage:
    python benchmarks/round_trip/cross_model_review.py deprecated \\
        --executor-model claude-sonnet-4-6 \\
        --reviewer-model claude-opus-4-7

Q1 measurement is OUT OF SCOPE for this module. Run Q1 separately via the
existing `metrics/q1_test_parity.py` (which requires original_dir, typically
under ~/kaizen-commit0/repos/<lib>/).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

_COMMIT0_BASELINES = HERE.parent / "commit0" / "baselines"
if str(_COMMIT0_BASELINES) not in sys.path:
    sys.path.insert(0, str(_COMMIT0_BASELINES))

from _llm import LLMClient, cost  # noqa: E402
from recompose_from_adrs import (  # noqa: E402
    _gather_spec,
    _parse_response as _parse_recompose_response,
    _write_text,
    _RECOMPOSE_INSTRUCTIONS,
)


_REVIEW_INSTRUCTIONS = """\
You are a SECOND-OPINION reviewer for a code-recomposition pipeline.

A first model (the EXECUTOR) was given a library specification (manifest,
import map, re-exports, ADRs, contracts, oracles) and produced a Python
package that purports to satisfy the spec without seeing the original
source. The executor's output passes surface checks (it imports, tests
collect), but we suspect it silently diverges from the canonical contract.

Your job is to read the spec AND the executor's recomposed code together
and identify *mapping failures*: places where the executor's code does
not realize what the spec describes.

Look specifically for:

1. **Behavioural drift.** A function exists with the right name and
   signature, but its body computes something inconsistent with the
   contract or oracles. Cite the file:line and the contract or oracle
   it violates.
2. **Silent omissions.** A spec element (an ADR decision, a contract
   clause, an oracle row) has no corresponding code. The function
   compiles but the decision was not implemented.
3. **Incorrect defaults.** Defaults differ between spec and code (e.g.,
   spec says `version=8.0`, code says `version=4.1`).
4. **Wrong dispatch.** The code branches on the wrong attribute, calls
   the wrong helper, or returns the wrong wrapper class — the kind of
   mistake that passes import-time checks but fails behavioural tests.
5. **Edge-case absence.** The spec mentions an edge case (empty input,
   None, unicode boundary) and the code does not handle it.

DO NOT comment on:
- Stylistic differences (formatting, naming when names are correct).
- Code the spec doesn't constrain.
- Performance unless the spec explicitly calls it out.

Output format — emit a single JSON object exactly matching this schema:

{
  "summary": "<one short paragraph: how confident the artifact is and where the biggest mapping failures are>",
  "findings": [
    {
      "id": "F1",
      "severity": "high" | "medium" | "low",
      "kind": "behavioural_drift" | "silent_omission" | "incorrect_default" | "wrong_dispatch" | "edge_case_absence",
      "file": "<recomposed file path or '(missing)'>",
      "spec_anchor": "<ADR/contract/oracle reference>",
      "evidence": "<what the code does>",
      "expected": "<what the spec requires>",
      "fix_hint": "<one sentence: the smallest change the executor should make>"
    }
  ]
}

Findings should be ordered by severity (high first), then by file. Cap at
12 findings; aggregate if needed.

If you genuinely find no mapping failures, return:

{
  "summary": "No mapping failures identified.",
  "findings": []
}

Do NOT emit any commentary outside the JSON object.
"""


def _gather_recomposed(lib_recomp_dir: Path) -> str:
    """Concatenate recomposed source files into a single block."""
    parts: list[str] = []
    skip_dirs = {"__pycache__", "build", "dist", "target", "node_modules"}
    extensions = (".py", ".pyi")
    for f in sorted(lib_recomp_dir.rglob("*")):
        if not f.is_file():
            continue
        if any(p in skip_dirs for p in f.parts):
            continue
        if f.suffix not in extensions:
            continue
        rel = f.relative_to(lib_recomp_dir).as_posix()
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = f.read_bytes().decode("latin-1", errors="replace")
        parts.append(f"### RECOMPOSED FILE: {rel}\n```python\n{text}\n```\n")
    return "# Recomposed package\n\n" + "\n".join(parts) + "\n"


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_review(response: str) -> dict:
    """Extract the JSON object from the reviewer's response."""
    text = response.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return {"summary": "(unparseable reviewer response)", "findings": [],
                "raw": response[:2000]}
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"summary": f"(JSON decode error: {e})", "findings": [],
                "raw": response[:2000]}
    obj.setdefault("summary", "")
    obj.setdefault("findings", [])
    return obj


def review_artifact(
    lib: str,
    spec_dir: Path,
    recomposed_dir: Path,
    reviewer_model: str,
    provider: str = "anthropic",
    timeout: float | None = None,
) -> dict:
    """Run the cross-model review pass.

    Returns:
        {
          "ok": bool,
          "review": {summary, findings: [...]},
          "cost_usd": float,            # NOTE: priced as Sonnet by _llm.cost()
          "elapsed_s": float,
          "model": <reviewer_model>,
          "usage": {input, output, cache_read, cache_write},
        }
    """
    t0 = time.time()
    lib_spec = spec_dir / lib
    lib_recomp = recomposed_dir / lib
    if not lib_spec.is_dir():
        return {"ok": False, "error": f"spec_dir missing: {lib_spec}",
                "cost_usd": 0.0, "elapsed_s": 0.0}
    if not lib_recomp.is_dir():
        return {"ok": False, "error": f"recomposed_dir missing: {lib_recomp}",
                "cost_usd": 0.0, "elapsed_s": 0.0}

    spec_block, _ = _gather_spec(lib_spec)
    code_block = _gather_recomposed(lib_recomp)
    cached_block = spec_block + "\n\n" + code_block

    client_kwargs = {"timeout": timeout} if timeout is not None else {}
    client = LLMClient(provider, reviewer_model, **client_kwargs)
    response, usage = client.call(_REVIEW_INSTRUCTIONS, cached_block)
    spend = cost(provider, usage)

    review = _parse_review(response)

    return {
        "ok": True,
        "review": review,
        "cost_usd": round(spend, 4),
        "elapsed_s": round(time.time() - t0, 3),
        "model": client.model,
        "provider": provider,
        "usage": usage,
        "raw_response_head": response[:600],
    }


def _format_critique_for_recompose(review: dict) -> str:
    """Render the reviewer's findings as a spec amendment block.

    The amendment is appended to the spec block fed to the executor. It
    surfaces the highest-severity findings as concrete fix hints anchored
    to the existing spec artifacts.
    """
    findings = review.get("findings") or []
    if not findings:
        return ""
    lines = [
        "### REVIEWER CRITIQUE (cross-model second-opinion)",
        "",
        "A reviewer from a different model family read your prior recomposition",
        "alongside the spec and identified the following mapping failures.",
        "Treat these as authoritative spec amendments. Each finding cites a",
        "spec_anchor (ADR/contract/oracle) and an expected behaviour.",
        "",
        f"Reviewer summary: {review.get('summary', '').strip()}",
        "",
    ]
    for f in findings:
        lines.append(
            f"- [{f.get('severity', '?')}] {f.get('kind', '?')} "
            f"in `{f.get('file', '?')}` "
            f"(anchor: {f.get('spec_anchor', '?')})"
        )
        if f.get("evidence"):
            lines.append(f"  - evidence: {f['evidence']}")
        if f.get("expected"):
            lines.append(f"  - expected: {f['expected']}")
        if f.get("fix_hint"):
            lines.append(f"  - fix: {f['fix_hint']}")
    lines.append("")
    return "\n".join(lines)


def re_recompose_with_critique(
    lib: str,
    spec_dir: Path,
    output_dir: Path,
    review: dict,
    executor_model: str,
    provider: str = "anthropic",
    timeout: float | None = None,
) -> dict:
    """Re-run Recompose with the reviewer's critique injected into the spec.

    Writes to `output_dir/<lib>/`. Mirrors `recompose_from_adrs.recompose_from_adrs`
    with one change: the spec block is extended with the critique block.
    """
    t0 = time.time()
    lib_spec = spec_dir / lib
    lib_out = output_dir / lib
    if not lib_spec.is_dir():
        return {"ok": False, "error": f"spec_dir missing: {lib_spec}",
                "cost_usd": 0.0, "elapsed_s": 0.0}

    if lib_out.exists():
        import shutil
        shutil.rmtree(lib_out)
    lib_out.mkdir(parents=True, exist_ok=True)

    spec_block, _ = _gather_spec(lib_spec)
    critique = _format_critique_for_recompose(review)
    augmented_spec = spec_block + "\n\n" + critique if critique else spec_block

    client_kwargs = {"timeout": timeout} if timeout is not None else {}
    client = LLMClient(provider, executor_model, **client_kwargs)
    response, usage = client.call(_RECOMPOSE_INSTRUCTIONS, augmented_spec)
    spend = cost(provider, usage)

    sections = _parse_recompose_response(response)
    files_emitted = 0
    parse_warning = None
    if not sections:
        _write_text(lib_out / "RAW_RECOMPOSE_RESPONSE.md", response)
        parse_warning = "no `=== path ===` sections found; saved raw response"
    else:
        for rel_path, content in sections.items():
            if rel_path.startswith(("/", "..")) or ".." in rel_path.split("/"):
                continue
            normalized = rel_path
            if normalized.startswith(f"{lib}/"):
                normalized = normalized[len(lib) + 1:]
            elif normalized == lib:
                continue
            _write_text(lib_out / normalized, content)
            files_emitted += 1

    result = {
        "ok": files_emitted > 0 or parse_warning is None,
        "cost_usd": round(spend, 4),
        "elapsed_s": round(time.time() - t0, 3),
        "files_emitted": files_emitted,
        "model": client.model,
        "provider": provider,
        "usage": usage,
        "critique_findings": len(review.get("findings") or []),
    }
    if parse_warning:
        result["parse_warning"] = parse_warning
    return result


def run_cross_model_review(
    lib: str,
    spec_dir: Path,
    recomposed_dir: Path,
    output_dir: Path,
    executor_model: str,
    reviewer_model: str,
    provider: str = "anthropic",
    timeout: float | None = None,
) -> dict:
    """End-to-end: review existing recompose, re-recompose with critique."""
    t0 = time.time()
    review_result = review_artifact(
        lib, spec_dir, recomposed_dir, reviewer_model,
        provider=provider, timeout=timeout,
    )
    if not review_result.get("ok"):
        return {
            "lib": lib,
            "review": review_result,
            "re_recompose": None,
            "totals": {"cost_usd": review_result.get("cost_usd", 0.0),
                       "elapsed_s": round(time.time() - t0, 3)},
        }

    re_result = re_recompose_with_critique(
        lib, spec_dir, output_dir, review_result["review"], executor_model,
        provider=provider, timeout=timeout,
    )

    total_cost = round(
        review_result.get("cost_usd", 0.0) + re_result.get("cost_usd", 0.0), 4
    )
    return {
        "lib": lib,
        "executor_model": executor_model,
        "reviewer_model": reviewer_model,
        "review": review_result,
        "re_recompose": re_result,
        "totals": {"cost_usd": total_cost,
                   "elapsed_s": round(time.time() - t0, 3)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lib", help="library name (must already have spec/<lib>/ "
                                      "and recomposed/<lib>/ on disk)")
    parser.add_argument("--provider", default="anthropic",
                        choices=["anthropic", "openai"])
    parser.add_argument("--executor-model", default="claude-sonnet-4-6",
                        help="Model that did (and will redo) Recompose.")
    parser.add_argument("--reviewer-model", default="claude-opus-4-7",
                        help="Model that critiques the recomposed artifact. "
                             "Picking a different family/size from --executor-model "
                             "is the whole point.")
    parser.add_argument("--spec-dir", type=Path, default=HERE / "spec")
    parser.add_argument("--recomposed-dir", type=Path, default=HERE / "recomposed")
    parser.add_argument("--output-dir", type=Path,
                        default=HERE / "recomposed_reviewed")
    parser.add_argument("--results-dir", type=Path, default=HERE / "results")
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--review-only", action="store_true",
                        help="Run the reviewer pass and dump the critique JSON; "
                             "skip the re-recompose step.")
    args = parser.parse_args()

    if args.review_only:
        result = review_artifact(
            args.lib, args.spec_dir, args.recomposed_dir, args.reviewer_model,
            provider=args.provider, timeout=args.timeout,
        )
        out_path = args.results_dir / f"{args.lib}_review_only.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path}")
        if result.get("ok"):
            r = result["review"]
            print(f"summary: {r.get('summary', '')[:240]}")
            print(f"findings: {len(r.get('findings', []))}")
            print(f"cost: ${result['cost_usd']}")
        else:
            print(f"error: {result.get('error')}")
        return 0 if result.get("ok") else 2

    result = run_cross_model_review(
        args.lib, args.spec_dir, args.recomposed_dir, args.output_dir,
        args.executor_model, args.reviewer_model,
        provider=args.provider, timeout=args.timeout,
    )
    out_path = args.results_dir / f"{args.lib}_cross_model_review.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"executor: {args.executor_model}  reviewer: {args.reviewer_model}")
    print(f"findings: {len(result['review']['review'].get('findings', []))}")
    if result["re_recompose"]:
        print(f"files emitted: {result['re_recompose'].get('files_emitted')}")
    print(f"cost: ${result['totals']['cost_usd']}  elapsed: "
          f"{result['totals']['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
