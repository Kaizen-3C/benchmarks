"""Stage 2 (ADR-0064): code-editing iteration loop.

When smoke_test fails on the recomposed package, instead of amending the
spec and regenerating from scratch (Stage 1's failed approach), we hand
the LLM the recomposed CODE plus the traceback and ask for a direct edit.
We apply, re-smoke, repeat — up to N iterations or smoke pass.

This is the OH/Aider/smolagents loop shape: failure -> code edit -> retry.
The LLM is patching the artifact, not the description.

Why this is different from remediation.py:
  - remediation.py edits spec_dir/<lib>/ (manifest, contracts, oracles)
    then re-Recomposes from scratch.
  - code_edit_loop.py edits recomposed/<lib>/ (the actual .py files)
    then re-runs smoke. No regeneration.

Cost: 1 LLM call per iteration. Cap at N=3 by default.
"""

from __future__ import annotations

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
from smoke_test import smoke_test as _python_smoke_test  # noqa: E402

# Adapter-aware mode is opt-in via the `adapter` argument. Default behavior
# is unchanged from earlier sessions — Python-only — so existing callers keep
# working.
import lang_adapter  # noqa: E402
try:
    from lang_adapters import python, rust, typescript  # noqa: F401
except ImportError:
    pass


_EDIT_INSTRUCTIONS = """\
You are debugging a {lang_label} package/crate. The smoke check failed.
Fix the package by editing files directly.

You will be given:
  1. The smoke-test traceback (the failure to fix)
  2. The current contents of every file in the package
  3. Optionally, the recomposed spec for context

Emit your fix as one or more file replacements, each delimited by:

    === <relative/path> ===
    <new full file content>

Path conventions:

  - Paths are relative to the package directory (e.g., `__init__.py`,
    `core.py`, `submod/utils.py`).
  - You may CREATE new files (e.g., a missing `submod/__init__.py`).
  - You may REPLACE existing files. The content you emit overwrites the
    file completely — include everything, not just the diff.
  - Do NOT delete files (we don't currently support that).

Critical rules:

  1. Trace the error to its precise cause. `ImportError: cannot import
     name 'X' from 'pkg.module'` usually means either (a) `X` is missing
     from `pkg/module.py`'s definitions, or (b) the import path is wrong
     in the file that did the import.

  2. Fix the SMALLEST set of files that resolves the failure. If the
     traceback points at a single import line, the fix is usually in one
     or two files. Don't rewrite the whole package.

  3. Preserve the working pieces. Most of the recomposed code is correct;
     don't regress it.

  4. After your edit, the package MUST `python -c "import <pkg>"` cleanly.
     Mentally run the imports before emitting.

  5. If the traceback is `ModuleNotFoundError: No module named
     'pkg.submod'`, you need to CREATE `submod.py` (or `submod/__init__.py`).
     Look at how the test suite uses it to infer what symbols it must
     export.

  6. Data-table modules — CRITICAL. If a file is or would be a literal
     enumeration of more than ~200 tuples/entries (Unicode ranges,
     language tables, encoding maps), DO NOT WRITE THE TABLE. Your
     output WILL truncate mid-tuple and leave SyntaxError; this has
     happened in past runs.

     Instead, derive the table programmatically. Examples:

       # WRONG — will truncate
       ZERO_WIDTH = ((0x0300, 0x036F), (0x0483, 0x0489), ... 5000 more ...)

       # RIGHT — compute at module load
       import unicodedata
       def _zero_width_ranges():
           ranges, start = [], None
           for cp in range(0x10FFFF + 1):
               try:
                   cat = unicodedata.category(chr(cp))
               except ValueError:
                   continue
               is_zero = cat in ("Mn", "Me", "Cf")
               if is_zero and start is None: start = cp
               elif not is_zero and start is not None:
                   ranges.append((start, cp - 1)); start = None
           if start is not None:
               ranges.append((start, 0x10FFFF))
           return tuple(ranges)
       ZERO_WIDTH = _zero_width_ranges()

     Same pattern for other Unicode-derived tables. For non-Unicode
     tables (e.g., character-encoding maps), use stdlib `codecs` or
     compute from the test inputs. If unsure how to derive: emit a
     stub that raises NotImplementedError with a comment — better than
     a syntax error.

Do not emit any preamble, markdown, or commentary outside the
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


def _gather_package_files(pkg_dir: Path,
                            extensions: tuple[str, ...] = (".py",),
                            also_root: tuple[str, ...] = ()) -> str:
    """Read all source files under pkg_dir into a single text block.

    `extensions`: which file types belong to the package source.
    `also_root`: extra files (e.g., 'Cargo.toml', 'package.json') to include
        if they sit alongside the source. Use this for typed-language adapters.
    """
    parts: list[str] = []
    skip_dirs = {"target", "node_modules", "__pycache__", "dist", "build"}
    for f in sorted(pkg_dir.rglob("*")):
        if not f.is_file():
            continue
        if any(p in skip_dirs for p in f.parts):
            continue
        if f.suffix not in extensions and f.name not in also_root:
            continue
        rel = f.relative_to(pkg_dir).as_posix()
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = f.read_bytes().decode("latin-1", errors="replace")
        # Pick a fence label hint by extension.
        fence = {
            ".py": "python", ".rs": "rust", ".ts": "typescript",
            ".tsx": "tsx", ".js": "javascript", ".mjs": "javascript",
            ".cjs": "javascript", ".d.ts": "typescript",
        }.get(f.suffix, "")
        parts.append(f"### FILE: {rel}\n```{fence}\n{text}\n```\n")
    return "# Package files\n\n" + "\n".join(parts) + "\n"


def _detect_package_dir(recomposed_dir: Path) -> tuple[Path, str]:
    """Same logic as Q1/smoke_test — find the importable package root."""
    if (recomposed_dir / "__init__.py").is_file():
        return recomposed_dir, recomposed_dir.name
    candidates = [
        d for d in recomposed_dir.iterdir()
        if d.is_dir() and (d / "__init__.py").is_file()
    ]
    if len(candidates) == 1:
        return candidates[0], candidates[0].name
    return recomposed_dir, recomposed_dir.name


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


_LANG_LABEL = {"python": "Python", "rust": "Rust", "typescript": "TypeScript"}


def iterate_to_smoke_pass(
    original_dir: Path,
    recomposed_dir: Path,
    max_iters: int = 3,
    provider: str = "anthropic",
    model: str | None = None,
    timeout: float | None = None,
    lang: str = "python",
    sp_stop: bool = False,
    sp_cost_threshold: float = 0.30,
) -> dict:
    """Run smoke -> edit -> smoke until smoke passes or budget exhausts.

    Args:
        original_dir: source-of-truth library checkout (has tests/).
        recomposed_dir: the recomposed package dir to edit in place.
        max_iters: max number of edit passes.
        provider, model, timeout: LLM config.
        lang: "python", "rust", or "typescript" — picks adapter + prompt label.
        sp_stop: stochastic stopping — halt when the traceback converges
            (identical on two consecutive iterations), indicating VoI ≈ 0.
            Only triggers after at least one iteration and when spend so far
            exceeds sp_cost_threshold.
        sp_cost_threshold: minimum spend (USD) before sp_stop activates.

    Returns:
        {
          "ok": bool,                  # smoke passed by end of loop
          "iterations": int,
          "cost_usd": float,
          "elapsed_s": float,
          "history": [
            {"iter": 1, "smoke_ok": False, "first_traceback": ...,
             "amendments": int, "cost_usd": ..., "files_edited": [...]},
            ...
          ],
          "final_smoke": dict,         # last smoke_test result
          "sp_stopped": bool,          # True if stochastic stopping fired
        }
    """
    t0 = time.time()
    history: list[dict] = []
    total_cost = 0.0
    prev_traceback: str = ""
    sp_stopped: bool = False

    # Pick adapter for language. Python keeps the legacy code path so existing
    # callers continue to work without explicit lang= argument.
    if lang == "python":
        adapter = None  # use module-level Python helpers
        pkg_src, pkg_name = _detect_package_dir(recomposed_dir)
        gather_exts: tuple[str, ...] = (".py",)
        gather_root: tuple[str, ...] = ()
        smoke = _python_smoke_test(original_dir, recomposed_dir)
    else:
        adapter = lang_adapter.get(lang)
        pkg_src, pkg_name = adapter.detect_package_dir(recomposed_dir)
        gather_exts = adapter.file_extensions
        gather_root = ("Cargo.toml", "package.json", "tsconfig.json",
                        "vitest.config.ts", "vitest.config.js")
        smoke_result = adapter.smoke_check(original_dir, recomposed_dir)
        # Adapter returns {ok, build, collect, first_traceback, package_name}
        # — same shape the legacy smoke_test uses, with import->build rename.
        smoke = {
            "ok": smoke_result["ok"],
            "import": smoke_result.get("build", {"ok": smoke_result["ok"]}),
            "collect": smoke_result.get("collect", {}),
            "first_traceback": smoke_result.get("first_traceback", ""),
            "package_name": smoke_result.get("package_name", pkg_name),
        }

    if smoke["ok"]:
        return {
            "ok": True, "iterations": 0, "cost_usd": 0.0,
            "elapsed_s": round(time.time() - t0, 3),
            "history": [],
            "final_smoke": smoke,
            "skipped": True, "reason": "smoke already passed",
            "lang": lang,
        }

    client_kwargs = {"timeout": timeout} if timeout is not None else {}
    client = LLMClient(provider, model, **client_kwargs)
    instructions = _EDIT_INSTRUCTIONS.format(
        lang_label=_LANG_LABEL.get(lang, lang.title()),
    )

    for i in range(1, max_iters + 1):
        traceback = smoke["first_traceback"]
        if not traceback:
            break

        # SP stopping: if the traceback hasn't changed since the last iteration
        # and we've already spent beyond the cost threshold, VoI ≈ 0 — stop.
        if sp_stop and i > 1 and total_cost >= sp_cost_threshold:
            if traceback.strip() == prev_traceback.strip():
                sp_stopped = True
                break

        prev_traceback = traceback

        files_block = _gather_package_files(pkg_src, gather_exts, gather_root)
        prompt = (
            f"# Smoke-test failure (iteration {i})\n\n"
            f"Importable package: `{pkg_name}`\n\n"
            "## Traceback\n\n"
            "```\n" + traceback.strip() + "\n```\n\n"
            + files_block
        )
        response, usage = client.call(instructions, prompt)
        spend = cost(provider, usage)
        total_cost += spend

        sections = _parse_response(response)
        files_edited: list[str] = []
        if not sections:
            history.append({
                "iter": i, "smoke_ok": False,
                "first_traceback_head": traceback[:200],
                "cost_usd": round(spend, 4), "files_edited": [],
                "parse_warning": "no `=== path ===` sections",
            })
            break

        for rel_path, content in sections.items():
            # Strip an accidental leading `<pkg>/` if the LLM included it.
            normalized = rel_path
            if normalized.startswith(f"{pkg_name}/"):
                normalized = normalized[len(pkg_name) + 1:]
            if normalized.startswith(("/", "..")) or ".." in normalized.split("/"):
                continue
            target = pkg_src / normalized
            _write_text(target, content)
            files_edited.append(normalized)

        # Re-smoke.
        if adapter is None:
            smoke = _python_smoke_test(original_dir, recomposed_dir)
        else:
            sr = adapter.smoke_check(original_dir, recomposed_dir)
            smoke = {
                "ok": sr["ok"],
                "import": sr.get("build", {"ok": sr["ok"]}),
                "collect": sr.get("collect", {}),
                "first_traceback": sr.get("first_traceback", ""),
                "package_name": sr.get("package_name", pkg_name),
            }
        history.append({
            "iter": i,
            "smoke_ok": smoke["ok"],
            "import_ok": smoke["import"]["ok"],
            "collect_ok": smoke["collect"].get("ok"),
            "first_traceback_head": (
                smoke.get("first_traceback", "")[:200]
                if not smoke["ok"] else ""
            ),
            "cost_usd": round(spend, 4),
            "files_edited": files_edited,
        })
        if smoke["ok"]:
            break

    return {
        "ok": smoke["ok"],
        "iterations": len(history),
        "cost_usd": round(total_cost, 4),
        "elapsed_s": round(time.time() - t0, 3),
        "history": history,
        "final_smoke": smoke,
        "model": getattr(client, "model", model),
        "provider": provider,
        "sp_stopped": sp_stopped,
    }


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--original", type=Path, required=True)
    ap.add_argument("--recomposed", type=Path, required=True)
    ap.add_argument("--max-iters", type=int, default=3)
    ap.add_argument("--provider", default="anthropic")
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--lang", default="python",
                    choices=["python", "rust", "typescript"])
    ap.add_argument("--sp-stop", action="store_true",
                    help="Stochastic stopping: halt when traceback converges (VoI=0)")
    ap.add_argument("--sp-cost-threshold", type=float, default=0.30,
                    help="Min spend (USD) before --sp-stop activates (default 0.30)")
    args = ap.parse_args()

    r = iterate_to_smoke_pass(
        args.original, args.recomposed,
        max_iters=args.max_iters, provider=args.provider,
        model=args.model, timeout=args.timeout, lang=args.lang,
        sp_stop=args.sp_stop, sp_cost_threshold=args.sp_cost_threshold,
    )
    print(json.dumps(r, indent=2, default=str))
    sys.exit(0 if r["ok"] else 1)
