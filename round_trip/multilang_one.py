"""Minimal language-agnostic round-trip runner.

Phase C: pick a LangAdapter, send source through Decompose -> Recompose -> Smoke
-> (optional) code_edit_loop -> Q1. Uses adapter methods instead of Python-
specific helpers.

Decompose/Recompose prompts are language-parametric: they ask the LLM to
emit a manifest+import_map+reexports tuple appropriate for the target
language ('Cargo.toml + lib.rs re-exports + module graph' for Rust).

Run:
    python benchmarks/round_trip/multilang_one.py \\
        --lang rust --lib ru_lru \\
        --repos-root ~/kaizen-rust-corpus/repos
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

_BASELINES = HERE.parent / "commit0" / "baselines"
if str(_BASELINES) not in sys.path:
    sys.path.insert(0, str(_BASELINES))

from _llm import LLMClient, cost  # noqa: E402
import lang_adapter  # noqa: E402
from lang_adapters import python, rust, typescript  # noqa: E402,F401  (registers)


_DECOMPOSE_INSTRUCTIONS = """\
You are reading a complete {lang} library and producing a specification
that another engineer (with no access to this source) could use to rebuild
a functionally-equivalent library FROM SCRATCH.

The rebuilt library must be RUNNABLE — it must satisfy `{build_cmd}` and
`{test_cmd}` against the canonical tests.

Emit a single response with named sections, each delimited by:

    === <relative/path> ===
    <content>

REQUIRED top-level artifacts (emit FIRST):

* `manifest.json` — JSON with:
    - "language": "{lang}"
    - "package_name": importable name
    - "version": version string
    - "modules": list of source files (e.g., {file_examples})
    - "test_command": exact command the recomposer should expect tests
       to run with (e.g., "{test_cmd}")
    - "{native_manifest}": verbatim copy of the project's native
       package manifest ({native_manifest_examples})

* `import_map.json` — for each module, list its intra-package imports:
    e.g., {import_map_example}
    For {lang}, this is the {graph_term} graph.

* `reexports.json` — what the entry point ({entry_point}) re-exports
    publicly. Format: {reexports_example}

Then emit:

* `adrs/ADR-NNNN-<slug>.md` — one ADR per non-obvious design decision.
* `contracts/<Name>.md` — one contract per public module. List signatures,
    types, and a one-line behavioural summary per public item.
* `oracles/<topic>.jsonl` — behaviour oracles. One JSON per line:
    {{"name": "...", "input": ..., "expected": ...}}.

Constraints:

  1. Spec must be self-contained — no code blocks longer than ~3 lines.
     Function signatures are fine; bodies are the recomposer's job.
  2. Public API must be reproducible from the contracts.
  3. {lang_specific_note}

Order: manifest.json, import_map.json, reexports.json, ADRs, contracts,
oracles. No commentary outside `=== ... ===` blocks.
"""

_RECOMPOSE_INSTRUCTIONS = """\
You are reading a complete specification for a {lang} library and emitting
a working source tree from scratch. You have NEVER seen the original
source; the spec is your only input.

Read these spec artifacts in order and follow them exactly:

  1. manifest.json — modules to create, native package manifest, test
     command. Recreate EVERY listed module.
  2. reexports.json — what {entry_point} must re-export. Verbatim.
  3. import_map.json — intra-package imports/uses. Every relation
     listed must appear in the corresponding file.
  4. contracts — public API signatures and behaviour summaries.
  5. oracles — input/output pairs that must hold.
  6. ADRs — design rationale.

Emit a single response. Each output file is delimited by:

    === <relative/path> ===
    <content>

Path conventions:
  - The {native_manifest} file at the repository root.
  - {entry_point} is the package entry point.
  - Other modules live under the standard layout for {lang}.

CRITICAL: the test command `{test_cmd}` MUST pass against your output.
Match the public API exactly: names and signatures.

Constraints:
  1. Pure {lang}, no exotic dependencies beyond what manifest.json lists.
  2. Public surface must be exactly what contracts list.
  3. {lang_specific_note}

No preamble or commentary outside `=== ... ===` blocks.
"""


_LANG_PARAMS = {
    "rust": {
        "build_cmd": "cargo check --all-targets",
        "test_cmd": "cargo test --no-fail-fast",
        "file_examples": '["lib.rs", "core.rs", "utils.rs"]',
        "native_manifest": "cargo_toml",
        "native_manifest_examples": "Cargo.toml",
        "import_map_example": '{"src/lib.rs": ["pub mod core", "pub mod utils"], "src/core.rs": ["use crate::utils::helper"]}',
        "graph_term": "module declaration + use",
        "entry_point": "src/lib.rs",
        "reexports_example": '{"pub use core::Foo": "Foo", "__all__": ["Foo", "Bar"]}',
        "lang_specific_note": (
            "Generic data tables (Unicode, encoding) must be derived "
            "programmatically from std crates (`unicode_categories` shape) "
            "or hardcoded only if <100 entries. Match `pub` visibility "
            "exactly — extra `pub` items count as drift."
        ),
    },
    "python": {
        "build_cmd": "python -c \"import <pkg>\"",
        "test_cmd": "pytest",
        "file_examples": '["__init__.py", "core.py", "utils.py"]',
        "native_manifest": "setup_py_or_pyproject",
        "native_manifest_examples": "setup.py / pyproject.toml",
        "import_map_example": '{"__init__.py": {"from .core import X": "re-export"}}',
        "graph_term": "import",
        "entry_point": "__init__.py",
        "reexports_example": '{"from .module import X": ["X"]}',
        "lang_specific_note": "Pure Python ≥3.8 unless manifest lists deps.",
    },
    "typescript": {
        "build_cmd": "tsc --noEmit (when tsconfig.json present)",
        "test_cmd": "vitest run / ava / jest (whichever the package uses)",
        "file_examples": '["src/lib.ts", "src/core.ts"] OR ["index.js", "lib/foo.js"] depending on the original',
        "native_manifest": "package_json",
        "native_manifest_examples": "package.json (and tsconfig.json if TypeScript)",
        "import_map_example": '{"src/lib.ts": ["export {Foo} from \\"./core\\""], "src/core.ts": ["import {helper} from \\"./utils\\""]}',
        "graph_term": "import / export",
        "entry_point": "value of `main` (or `exports.default`) in package.json — could be index.js, src/lib.ts, etc.",
        "reexports_example": '{"export {Foo} from \\"./core\\"": ["Foo"]}',
        "lang_specific_note": (
            "MATCH THE ORIGINAL SOURCE LANGUAGE. If the original ships as "
            ".js / .mjs (with optional .d.ts type declarations on the side), "
            "emit the same — do NOT convert to .ts. If the original is .ts "
            "with strict typing, emit .ts. The package's `exports` / `main` "
            "field in package.json determines the entry point. Use ESM by "
            "default (`type: \"module\"` in modern packages); CommonJS only "
            "if the original uses it. Match the test runner the original "
            "ships (vitest / ava / jest). Match exact getter/setter shapes; "
            "reproduce class member visibility verbatim."
        ),
    },
}


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


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    fence = re.compile(r"^```[a-zA-Z0-9_+-]*\n(.*?)\n```\s*$", re.DOTALL)
    m = fence.match(text)
    return m.group(1) if m else text


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


_MAX_FILE_BYTES = 30_000


def _gather_source(repo_dir: Path, exts: tuple[str, ...]) -> str:
    parts: list[str] = []
    skip_dirs = {"target", "node_modules", "__pycache__", ".git", "dist", "build"}
    for f in sorted(repo_dir.rglob("*")):
        if not f.is_file() or f.suffix not in exts:
            continue
        if any(p in skip_dirs for p in f.parts):
            continue
        rel = f.relative_to(repo_dir).as_posix()
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = f.read_bytes().decode("latin-1", errors="replace")
        if len(text) > _MAX_FILE_BYTES:
            extra = len(text) - _MAX_FILE_BYTES
            text = (
                text[:_MAX_FILE_BYTES]
                + f"\n\n# ...truncated ({extra:,} more bytes; this file is "
                "data — describe shape and provenance in an ADR; the recomposer "
                "should derive its contents programmatically from stdlib / the "
                "language's standard crate, NOT enumerate the table inline.)\n"
            )
        parts.append(f"### FILE: {rel}\n```\n{text}\n```\n")
    # Also include manifest files so the LLM sees deps.
    for name in ("Cargo.toml", "Cargo.lock", "package.json", "tsconfig.json",
                  "setup.py", "pyproject.toml"):
        p = repo_dir / name
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = p.read_bytes().decode("latin-1", errors="replace")
            parts.append(f"### MANIFEST: {name}\n```\n{text}\n```\n")
    return "# Library source\n\n" + "\n".join(parts)


_MULTI_SHOT_INSTRUCTIONS = """\
You are reading a complete specification for a {lang} library and emitting
ONE FILE at a time. The full spec is in the system prompt below; you have
already (in earlier turns) emitted other files. NOW emit ONLY the file
named in the user message.

Wrap your output as:

    === <relative/path> ===
    <full file content>

Emit EXACTLY ONE such block — no other files, no commentary.

Constraints:
  - Match the public surface in `manifest.json` / `reexports.json` /
    contracts exactly. Do NOT invent extra public items.
  - Match imports declared in `import_map.json` for this file.
  - For data-table files (Unicode ranges, encoding maps, frequency
    tables, etc.) DERIVE programmatically from stdlib/std crate; do
    NOT enumerate inline. Truncation = SyntaxError.
  - Test files are NOT in the manifest's modules list — do not emit them.
"""


def _list_modules_from_manifest(spec_dir: Path) -> list[str]:
    """Read manifest.json to get the list of files to emit."""
    mf = spec_dir / "manifest.json"
    if not mf.is_file():
        return []
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    mods = data.get("modules")
    if isinstance(mods, list):
        return [m for m in mods if isinstance(m, str)]
    return []


def _multi_shot_recompose(client, recompose_prompt: str, spec_block: str,
                            spec_dir: Path, rec_dir: Path, lang: str,
                            provider: str) -> tuple[float, int, dict]:
    """Multi-shot recompose: ask LLM for one file at a time.

    Each call has the full spec_block in `cached_block` (so input tokens
    don't repay) and a short user message naming the target file. This
    avoids the single-shot output-token wall (~1000 LOC ceiling).

    Returns (total_cost_usd, files_emitted, info_dict).
    """
    modules = _list_modules_from_manifest(spec_dir)
    info: dict = {"modules_listed": len(modules), "per_file": []}
    total_cost = 0.0
    files_emitted = 0

    # Always emit the native package manifest first if listed in the spec.
    # Look for it as a top-level spec key like 'cargo_toml', 'package_json', etc.
    # Also look for entries in `_LANG_PARAMS[lang]['native_manifest_examples']`.
    params = _LANG_PARAMS.get(lang, {})
    native_examples = params.get("native_manifest_examples", "")
    native_files: list[str] = []
    for tok in re.split(r"[\s,/]+", native_examples):
        tok = tok.strip()
        if tok and tok not in native_files:
            native_files.append(tok)

    # Build the per-file ordering: native manifest(s) first, then modules.
    targets: list[str] = []
    for nf in native_files:
        if nf:
            targets.append(nf)
    for m in modules:
        if m not in targets:
            targets.append(m)

    if not targets:
        # Fallback: nothing to do; signal caller to use single-shot.
        return 0.0, 0, {**info, "error": "no targets in manifest"}

    instructions = _MULTI_SHOT_INSTRUCTIONS.format(lang=lang)
    # System prompt = recompose preamble + the full spec (cached).
    system = recompose_prompt + "\n\n" + spec_block

    for target in targets:
        user_msg = f"Emit ONLY this file: `{target}`"
        try:
            response, usage = client.call(system + "\n\n" + instructions, user_msg)
        except Exception as e:
            info["per_file"].append({"target": target, "error": str(e)})
            continue
        total_cost += cost(provider, usage)
        sections = _parse_response(response)
        wrote = 0
        for rel, content in sections.items():
            if rel.startswith(("/", "..")) or ".." in rel.split("/"):
                continue
            # Allow LLM to emit only the target file; skip others.
            if rel != target and target not in rel:
                continue
            _write_text(rec_dir / rel, _strip_code_fence(content))
            wrote += 1
            files_emitted += 1
        info["per_file"].append({
            "target": target, "wrote": wrote,
            "cost_usd": round(cost(provider, usage), 4),
        })

    return round(total_cost, 4), files_emitted, info


def round_trip(lib: str, lang: str, repos_root: Path,
                output_dir: Path, provider: str = "anthropic",
                model: str | None = None, timeout: float = 600.0,
                clean: bool = True, multi_shot: bool = False) -> dict:
    t0 = time.time()
    adapter = lang_adapter.get(lang)
    params = _LANG_PARAMS.get(lang)
    if params is None:
        raise ValueError(f"no _LANG_PARAMS for {lang}")

    repo = repos_root / lib
    if not repo.is_dir():
        return {"error": f"repo missing: {repo}"}

    spec_dir = output_dir / "spec" / lib
    rec_dir = output_dir / "recomposed" / lib
    if clean:
        for d in (spec_dir, rec_dir):
            if d.exists():
                shutil.rmtree(d)
    for d in (spec_dir, rec_dir):
        d.mkdir(parents=True, exist_ok=True)

    src_block = _gather_source(repo, adapter.file_extensions)

    client = LLMClient(provider, model, timeout=timeout)

    # 1. Decompose
    decompose_prompt = _DECOMPOSE_INSTRUCTIONS.format(lang=lang, **params)
    t_dec = time.time()
    response, usage = client.call(decompose_prompt, src_block)
    decompose_cost = cost(provider, usage)
    sections = _parse_response(response)
    files_in_spec = 0
    for rel, content in sections.items():
        if rel.startswith(("/", "..")) or ".." in rel.split("/"):
            continue
        _write_text(spec_dir / rel, content)
        files_in_spec += 1
    decompose_elapsed = round(time.time() - t_dec, 2)

    # 2. Recompose
    spec_block_parts = []
    for f in sorted(spec_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(spec_dir).as_posix()
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = f.read_bytes().decode("latin-1", errors="replace")
        spec_block_parts.append(f"### SPEC: {rel}\n{text}\n")
    spec_block = "# Specification\n\n" + "\n".join(spec_block_parts)

    recompose_prompt = _RECOMPOSE_INSTRUCTIONS.format(lang=lang, **params)
    t_rec = time.time()
    if multi_shot:
        recompose_cost, files_emitted, multi_shot_info = _multi_shot_recompose(
            client, recompose_prompt, spec_block, spec_dir, rec_dir, lang, provider,
        )
    else:
        response, usage = client.call(recompose_prompt, spec_block)
        recompose_cost = cost(provider, usage)
        sections = _parse_response(response)
        files_emitted = 0
        for rel, content in sections.items():
            if rel.startswith(("/", "..")) or ".." in rel.split("/"):
                continue
            _write_text(rec_dir / rel, _strip_code_fence(content))
            files_emitted += 1
        multi_shot_info = None
    recompose_elapsed = round(time.time() - t_rec, 2)

    # 3. Smoke + Q1
    smoke = adapter.smoke_check(repo, rec_dir)
    q1 = adapter.run_tests(repo, rec_dir, timeout=timeout) if smoke["ok"] else {
        "metric": "q1_test_parity", "value": 0.0,
        "detail": {"error": "smoke failed", "smoke_traceback": smoke.get("first_traceback", "")[-1500:]},
    }

    return {
        "lib": lib,
        "lang": lang,
        "decompose": {
            "files_in_spec": files_in_spec,
            "cost_usd": round(decompose_cost, 4),
            "elapsed_s": decompose_elapsed,
        },
        "recompose": {
            "files_emitted": files_emitted,
            "multi_shot": multi_shot_info,
            "cost_usd": round(recompose_cost, 4),
            "elapsed_s": recompose_elapsed,
        },
        "smoke": {
            "ok": smoke["ok"],
            "build_ok": smoke.get("build", {}).get("ok"),
            "collect_ok": smoke.get("collect", {}).get("ok"),
            "first_traceback": smoke.get("first_traceback", "")[-2000:],
            "package_name": smoke.get("package_name"),
        },
        "metrics": {"q1_test_parity": q1},
        "totals": {
            "cost_usd": round(decompose_cost + recompose_cost, 4),
            "elapsed_s": round(time.time() - t0, 2),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lang", required=True, choices=list(_LANG_PARAMS))
    ap.add_argument("--lib", required=True)
    ap.add_argument("--repos-root", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path,
                    default=Path(__file__).resolve().parent / "multilang_runs")
    ap.add_argument("--provider", default="anthropic")
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--multi-shot", action="store_true",
                    help="File-by-file recompose; bypasses single-call output ceiling.")
    args = ap.parse_args()

    r = round_trip(args.lib, args.lang, args.repos_root,
                    args.output_dir, args.provider, args.model, args.timeout,
                    multi_shot=args.multi_shot)
    out_path = args.output_dir / f"{args.lang}_{args.lib}_round_trip.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    print(f"\nresult written: {out_path}")
    print(f"Q1: {r.get('metrics', {}).get('q1_test_parity', {}).get('value')}")
    print(f"smoke: {r.get('smoke', {}).get('ok')}")
    print(f"cost: ${r.get('totals', {}).get('cost_usd', 0):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
