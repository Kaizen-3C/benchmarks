"""Pre-decompose intent capture: what surface do tests actually reach?

Static AST scans of `from <pkg> import X` miss attribute-access patterns:

    from marshmallow import utils      # static scan sees: utils
    utils.to_timestamp(...)            # static scan misses: to_timestamp

The Decomposer doesn't surface `to_timestamp` in any contract because no
test imports it directly. The Recomposer never re-exports it. Tests fail
at runtime. This is the named ceiling in §5.4 of the round-trip paper.

This module produces a "tests reach this surface" set by:

  1. Parsing every test file's AST.
  2. Resolving `Name` nodes to their bound source: imports, function args,
     local assignments. Specifically: tracking which names refer to the
     library package or one of its submodules.
  3. Walking `Attribute` chains rooted at those names.
  4. Optionally augmenting with a `pytest --collect-only` run that records
     which library modules actually load (bypasses the AST entirely for
     dynamic imports).

Output: a set of (module, attribute) pairs the tests reach. Fed into the
Decomposer prompt as a REQUIRED-SURFACE hint.

Zero LLM cost.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path


def _find_tests_dir(original_dir: Path) -> Path | None:
    for name in ("tests", "test", "testing"):
        d = original_dir / name
        if d.is_dir():
            return d
    return None


class _AttrChainCollector(ast.NodeVisitor):
    """Walk attribute chains rooted at a known set of names.

    `name_to_module`: dict from local name -> the (module-relative) it points
    at within the package. E.g., after `from marshmallow import utils as u`,
    name_to_module = {"u": "utils", "utils": "utils"}.

    Records (module, attribute_chain) tuples. Chain is dotted, so
    `u.to_timestamp` -> ("utils", "to_timestamp"); `m.utils.fn` ->
    ("utils", "fn") if m maps to package root.
    """

    def __init__(self, name_to_module: dict[str, str], pkg_root: str):
        self.name_to_module = name_to_module
        self.pkg_root = pkg_root
        self.hits: set[tuple[str, str]] = set()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Walk down to the root Name.
        attrs: list[str] = []
        cur: ast.AST = node
        while isinstance(cur, ast.Attribute):
            attrs.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            attrs.reverse()
            mapped = self.name_to_module.get(cur.id)
            if mapped is None:
                self.generic_visit(node)
                return
            # Module is `mapped`, attribute chain is `attrs`.
            # If mapped == pkg_root (the user did `import marshmallow as m`),
            # the first attr is the submodule and the rest is the attribute.
            if mapped == "<root>":
                if len(attrs) >= 2:
                    self.hits.add((attrs[0], ".".join(attrs[1:])))
                elif len(attrs) == 1:
                    self.hits.add(("<root>", attrs[0]))
            else:
                # `mapped` is a submodule already; full chain is the attribute path.
                self.hits.add((mapped, ".".join(attrs)))
        self.generic_visit(node)


def _collect_test_attr_chains(test_dir: Path, pkg_root: str) -> set[tuple[str, str]]:
    """For each test file, build a name->module map then walk Attributes."""
    hits: set[tuple[str, str]] = set()
    for py in test_dir.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        # Build the name binding map for this file.
        name_to_module: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                # `from pkg import X [as Y]` -> Y bound to module-rooted X
                # `from pkg.sub import X [as Y]` -> Y bound to module-rooted sub.X
                if node.module == pkg_root:
                    for alias in (node.names or []):
                        if alias.name == "*":
                            continue
                        local = alias.asname or alias.name
                        name_to_module[local] = alias.name
                elif node.module.startswith(pkg_root + "."):
                    submod = node.module[len(pkg_root) + 1:]
                    for alias in (node.names or []):
                        if alias.name == "*":
                            continue
                        local = alias.asname or alias.name
                        # The bound name *is* the attribute on submod.
                        # We store it so direct references count too.
                        name_to_module[local] = submod
            elif isinstance(node, ast.Import):
                for alias in (node.names or []):
                    if alias.name == pkg_root:
                        local = alias.asname or alias.name
                        name_to_module[local] = "<root>"
                    elif alias.name.startswith(pkg_root + "."):
                        local = alias.asname or alias.name.split(".")[-1]
                        name_to_module[local] = alias.name[len(pkg_root) + 1:]

        if not name_to_module:
            continue
        collector = _AttrChainCollector(name_to_module, pkg_root)
        collector.visit(tree)
        hits.update(collector.hits)
    return hits


def _runtime_modules_loaded(original_dir: Path, pkg_root: str,
                             pkg_path: Path | None = None) -> list[str]:
    """Run `pytest --collect-only` and capture which `<pkg>.*` modules load.

    Uses a tiny conftest hack: insert sys.modules snapshot before/after.
    """
    tests = _find_tests_dir(original_dir)
    if tests is None:
        return []
    snippet = (
        "import sys, json\n"
        "before = set(sys.modules)\n"
        "def pytest_collection_finish(session):\n"
        "    after = set(sys.modules) - before\n"
        f"    relevant = sorted(m for m in after if m == {pkg_root!r} or m.startswith({pkg_root + '.'!r}))\n"
        "    sys.stdout.write('\\n__DYNAMIC_INTENT__:' + json.dumps(relevant) + '\\n')\n"
    )
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        conftest = Path(td) / "conftest_intent.py"
        conftest.write_text(snippet, encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(pkg_path or original_dir) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest",
                 "--collect-only", "-q", "--no-header",
                 "-p", "no:cacheprovider",
                 "-p", str(conftest.with_suffix("")).replace(os.sep, "."),
                 str(tests)],
                cwd=td, env=env, capture_output=True, timeout=120,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []
        out = (proc.stdout + proc.stderr).decode(errors="replace")
    for line in out.splitlines():
        if line.startswith("__DYNAMIC_INTENT__:"):
            import json
            try:
                return list(json.loads(line.split(":", 1)[1]))
            except json.JSONDecodeError:
                return []
    return []


def capture_intent(original_dir: Path, pkg_root: str | None = None) -> dict:
    """Capture the test surface for the package at `original_dir`.

    Args:
        original_dir: e.g., ~/kaizen-commit0/repos/marshmallow
        pkg_root: importable package name (default: dirname). Pyjwt is the
            classic counterexample where pkg_root != dirname.

    Returns:
        {
          "package_root": str,
          "static_attr_chains": [{"module": str, "attr": str}],
          "runtime_modules": [str],
          "tests_dir": str | None,
          "summary": str,           # prompt-ready text block
        }
    """
    pkg_path = original_dir  # PYTHONPATH dir; may be original_dir/src.
    if pkg_root is None:
        _SKIP = {"tests", "test", "testing", "docs", "doc", "examples",
                 "example", "performance", "benchmarks", "scripts"}
        if (original_dir / original_dir.name / "__init__.py").is_file():
            pkg_root = original_dir.name
        elif (original_dir / "src" / original_dir.name / "__init__.py").is_file():
            pkg_root = original_dir.name
            pkg_path = original_dir / "src"
        else:
            for parent in (original_dir / "src", original_dir):
                if not parent.is_dir():
                    continue
                inner = [
                    d for d in parent.iterdir()
                    if d.is_dir() and d.name not in _SKIP
                    and (d / "__init__.py").is_file()
                ]
                if len(inner) == 1:
                    pkg_root = inner[0].name
                    pkg_path = parent
                    break
            if pkg_root is None:
                pkg_root = original_dir.name

    tests = _find_tests_dir(original_dir)
    static_hits: set[tuple[str, str]] = set()
    if tests is not None:
        static_hits = _collect_test_attr_chains(tests, pkg_root)
    runtime_modules = _runtime_modules_loaded(original_dir, pkg_root, pkg_path)

    # Group by module for compact prompt rendering.
    by_mod: dict[str, set[str]] = {}
    for mod, attr in sorted(static_hits):
        by_mod.setdefault(mod, set()).add(attr)
    summary_lines = [
        f"# Test-reach surface for `{pkg_root}`",
        "",
        "The test suite reaches the following module attributes at runtime "
        "(captured from AST attribute chains rooted at the package). The "
        "spec MUST surface these symbols in contracts and `reexports.json` "
        "so the recomposed code keeps the test surface intact.",
        "",
    ]
    if by_mod:
        for mod in sorted(by_mod):
            attrs = ", ".join(sorted(by_mod[mod])[:30])
            summary_lines.append(f"- `{pkg_root}.{mod}`: {attrs}")
    else:
        summary_lines.append("- (none captured statically)")
    if runtime_modules:
        summary_lines.append("")
        summary_lines.append(
            "Runtime-loaded modules during collection (these MUST exist in "
            "`manifest.json -> modules`):"
        )
        for m in runtime_modules:
            summary_lines.append(f"- `{m}`")
    summary_lines.append("")
    return {
        "package_root": pkg_root,
        "static_attr_chains": [
            {"module": m, "attr": a} for (m, a) in sorted(static_hits)
        ],
        "runtime_modules": runtime_modules,
        "tests_dir": str(tests) if tests else None,
        "summary": "\n".join(summary_lines),
    }


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--original", type=Path, required=True)
    ap.add_argument("--pkg-root", default=None)
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()

    out = capture_intent(args.original, args.pkg_root)
    if args.summary_only:
        print(out["summary"])
    else:
        print(json.dumps(out, indent=2, default=str))
