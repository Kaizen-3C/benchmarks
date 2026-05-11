"""Apply reviewer critiques surgically — the reframed Idea A.

Sibling to `code_edit_loop.py`, but keyed on a reviewer's findings
(produced by `cross_model_review.py --review-only`) instead of a
smoke-test traceback. The executor is asked to make the smallest set of
edits that addresses each finding, NOT to regenerate the package.

Why this exists: a prior experiment (2026-05-08) showed that re-running
Recompose with the reviewer's critique injected as a spec amendment
regresses Q1 on both deprecated (−0.205) and pyjwt (114 newly-skipped
crypto tests) — the executor introduces collateral changes well beyond
the critique's scope. Surgical edits to the existing artifact, in the
shape of `code_edit_loop.iterate_to_smoke_pass`, is the right vector.

Run (Windows or WSL):
    python benchmarks/round_trip/critique_edit_loop.py deprecated \\
        --critique benchmarks/round_trip/results/deprecated_review_only.json \\
        --executor-model claude-sonnet-4-6

Q1 measurement is out of scope here — run it separately in WSL where
`~/kaizen-commit0/repos/<lib>/` is available.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
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


_EDIT_INSTRUCTIONS = """\
You are surgically editing an existing Python package to address a list
of behavioural findings produced by a SECOND-OPINION reviewer. The
package was previously recomposed by another model from a specification;
it imports cleanly and its tests collect, but a fraction of canonical
tests fail because the code silently diverges from the spec on specific
points. Your job is to fix those points — and ONLY those points.

You will be given:
  1. A list of findings (severity, file, spec_anchor, evidence, expected, fix_hint).
  2. The current contents of every Python file in the package.

Constraints — read carefully. Past experiments failed here.

  1. **Edit the SMALLEST set of files needed to address each finding.**
     If a finding cites `sphinx.py` line N, the fix lives in `sphinx.py`.
     Do not also touch unrelated files.

  2. **DO NOT add imports unless a finding explicitly requires it.** A
     prior run added `cryptography.exceptions.InvalidSignature` etc. and
     broke `has_crypto` detection downstream — 114 tests silently skipped.
     If you think you need a new import, justify it in the comment of
     the changed line. Otherwise leave imports as-is.

  3. **Preserve the public API exactly.** Do not rename, remove, or add
     public functions/classes. Findings are about behaviour, not surface.
     If a finding suggests a public-API change, prefer adjusting only the
     internal dispatch.

  4. **Apply each finding's `fix_hint` literally if it is concrete.** If
     the fix_hint says "remove .strip() on line X" — remove .strip(), and
     nothing else. Do not interpret loosely.

  5. **If a finding cannot be addressed without violating constraints
     1–4, skip it.** Better to miss one finding than introduce collateral
     damage. Note the skipped finding in a comment near the relevant code.

Emit your edits as one or more file replacements, each delimited by:

    === <relative/path> ===
    <new full file content>

Path conventions:
  - Paths are relative to the package directory (e.g., `sphinx.py`,
    `jwt/api_jwk.py`).
  - You may CREATE new files only if a finding says a module is missing.
  - You REPLACE existing files. The content you emit overwrites the
    file completely — include everything, not just the diff.
  - You may NOT delete files.

Do NOT emit any preamble, markdown, or commentary outside the
`=== ... ===` blocks.
"""


_SECTION_RE = re.compile(r"^=== (?P<path>[^=]+?) ===\s*$", re.MULTILINE)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    fence_re = re.compile(r"^```[a-zA-Z0-9_+-]*\n(.*?)\n```\s*$", re.DOTALL)
    m = fence_re.match(text)
    if m:
        return m.group(1)
    return text


def _parse_response(response: str) -> dict[str, str]:
    matches = list(_SECTION_RE.finditer(response))
    if not matches:
        return {}
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        path = m.group("path").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(response)
        out[path] = _strip_code_fence(response[start:end])
    return out


def _detect_package_dir(recomposed_dir: Path) -> tuple[Path, str]:
    """Same logic as code_edit_loop / smoke_test."""
    if (recomposed_dir / "__init__.py").is_file():
        return recomposed_dir, recomposed_dir.name
    candidates = [
        d for d in recomposed_dir.iterdir()
        if d.is_dir() and (d / "__init__.py").is_file()
    ]
    if len(candidates) == 1:
        return candidates[0], candidates[0].name
    return recomposed_dir, recomposed_dir.name


def _gather_package_files(pkg_dir: Path) -> str:
    parts: list[str] = []
    skip_dirs = {"target", "node_modules", "__pycache__", "dist", "build"}
    for f in sorted(pkg_dir.rglob("*")):
        if not f.is_file():
            continue
        if any(p in skip_dirs for p in f.parts):
            continue
        if f.suffix not in (".py", ".pyi"):
            continue
        rel = f.relative_to(pkg_dir).as_posix()
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = f.read_bytes().decode("latin-1", errors="replace")
        parts.append(f"### FILE: {rel}\n```python\n{text}\n```\n")
    return "# Package files\n\n" + "\n".join(parts) + "\n"


def _format_findings(findings: list[dict], cap: int = 10) -> str:
    """Render reviewer findings as an edit task list.

    Caps at `cap` to keep the prompt focused; high-severity first.
    """
    by_sev = {"high": 0, "medium": 1, "low": 2}
    sorted_findings = sorted(
        findings, key=lambda f: (by_sev.get(f.get("severity", "low"), 3),
                                 f.get("file", ""))
    )[:cap]

    lines = [f"# Reviewer findings ({len(sorted_findings)} of "
             f"{len(findings)} total, ordered by severity)\n"]
    for f in sorted_findings:
        lines.append(
            f"## {f.get('id', '?')} — [{f.get('severity', '?')}] "
            f"{f.get('kind', '?')}"
        )
        lines.append(f"- file: `{f.get('file', '?')}`")
        lines.append(f"- spec anchor: {f.get('spec_anchor', '?')}")
        if f.get("evidence"):
            lines.append(f"- evidence: {f['evidence']}")
        if f.get("expected"):
            lines.append(f"- expected: {f['expected']}")
        if f.get("fix_hint"):
            lines.append(f"- fix_hint: {f['fix_hint']}")
        lines.append("")
    return "\n".join(lines)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def critique_edit(
    lib: str,
    recomposed_dir: Path,
    output_dir: Path,
    critique: dict,
    executor_model: str,
    provider: str = "anthropic",
    timeout: float | None = None,
    max_findings: int = 10,
) -> dict:
    """Apply reviewer critique surgically to a copy of the recomposed package.

    Steps:
      1. Copy `recomposed_dir/<lib>/` to `output_dir/<lib>/` (so we don't
         touch the baseline artifact).
      2. Build prompt: package files + findings (capped).
      3. One LLM call with edit instructions.
      4. Apply each `=== path ===` patch in place under `output_dir/<lib>/`.

    Returns:
      {
        "ok": bool,
        "lib": str,
        "executor_model": str,
        "findings_count": int,
        "files_edited": list[str],
        "cost_usd": float,
        "elapsed_s": float,
        "usage": dict,
        "raw_response_head": str,
      }
    """
    t0 = time.time()
    src = recomposed_dir / lib
    if not src.is_dir():
        return {"ok": False, "lib": lib,
                "error": f"recomposed dir missing: {src}",
                "cost_usd": 0.0, "elapsed_s": 0.0}

    findings = critique.get("findings") or []
    if not findings:
        return {"ok": False, "lib": lib,
                "error": "critique has no findings",
                "cost_usd": 0.0, "elapsed_s": 0.0}

    dst = output_dir / lib
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    pkg_src, pkg_name = _detect_package_dir(dst)

    files_block = _gather_package_files(pkg_src)
    findings_block = _format_findings(findings, cap=max_findings)
    cached_block = (
        f"Importable package: `{pkg_name}`\n\n"
        + findings_block
        + "\n\n"
        + files_block
    )

    client_kwargs = {"timeout": timeout} if timeout is not None else {}
    client = LLMClient(provider, executor_model, **client_kwargs)
    response, usage = client.call(_EDIT_INSTRUCTIONS, cached_block)
    spend = cost(provider, usage)

    sections = _parse_response(response)
    files_edited: list[str] = []
    parse_warning = None
    if not sections:
        _write_text(dst / "RAW_EDIT_RESPONSE.md", response)
        parse_warning = "no `=== path ===` sections; saved raw response"
    else:
        for rel_path, content in sections.items():
            normalized = rel_path
            if normalized.startswith(f"{pkg_name}/"):
                normalized = normalized[len(pkg_name) + 1:]
            if normalized.startswith(("/", "..")) or ".." in normalized.split("/"):
                continue
            target = pkg_src / normalized
            _write_text(target, content)
            files_edited.append(normalized)

    out = {
        "ok": parse_warning is None and len(files_edited) > 0,
        "lib": lib,
        "executor_model": client.model,
        "provider": provider,
        "findings_count": len(findings),
        "findings_used": min(len(findings), max_findings),
        "files_edited": files_edited,
        "cost_usd": round(spend, 4),
        "elapsed_s": round(time.time() - t0, 3),
        "usage": usage,
        "raw_response_head": response[:600],
    }
    if parse_warning:
        out["parse_warning"] = parse_warning
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lib", help="library name (must already have "
                                      "recomposed/<lib>/ on disk)")
    parser.add_argument("--critique", type=Path, required=True,
                        help="Path to <lib>_review_only.json (from "
                             "cross_model_review.py --review-only).")
    parser.add_argument("--provider", default="anthropic",
                        choices=["anthropic", "openai"])
    parser.add_argument("--executor-model", default="claude-sonnet-4-6")
    parser.add_argument("--recomposed-dir", type=Path,
                        default=HERE / "recomposed")
    parser.add_argument("--output-dir", type=Path,
                        default=HERE / "recomposed_critique_edited")
    parser.add_argument("--results-dir", type=Path, default=HERE / "results")
    parser.add_argument("--max-findings", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=None)
    args = parser.parse_args()

    critique_full = json.loads(args.critique.read_text(encoding="utf-8"))
    # Accept either {"review": {...}} (full record) or {...} (raw critique).
    critique = critique_full.get("review", critique_full)

    result = critique_edit(
        args.lib, args.recomposed_dir, args.output_dir, critique,
        args.executor_model,
        provider=args.provider, timeout=args.timeout,
        max_findings=args.max_findings,
    )
    out_path = args.results_dir / f"{args.lib}_critique_edit.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"executor: {args.executor_model}")
    print(f"findings used: {result.get('findings_used')}/{result.get('findings_count')}")
    print(f"files edited: {result.get('files_edited')}")
    print(f"cost: ${result.get('cost_usd')}  elapsed: {result.get('elapsed_s')}s")
    if result.get("parse_warning"):
        print(f"WARN: {result['parse_warning']}")
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
