"""Implementation-leak gate: ADRs must describe behavior, not code.

Per ADR-0063: leakage rigs the round-trip — if the ADR contains the answer,
Recompose isn't being tested, the prompt is. This gate scans ADR text for
code-shaped content and flags it.

Detection:
    1. Fenced code blocks longer than 2 lines (``` ... ```).
       Short snippets (signatures, single expressions) are allowed; full
       implementations are not.
    2. Identifiers from the original code's PRIVATE surface (names starting
       with `_`) appearing verbatim in ADR text. Public names are expected;
       private names mean the ADR is leaking implementation details.
    3. Lines that lex as Python statements (def/return/yield/import) outside
       fenced blocks.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


_FENCED = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)\n```", re.DOTALL)
_INLINE_STATEMENT = re.compile(
    r"^\s*(def|class|return|yield|import|from\s+\S+\s+import)\b",
    re.MULTILINE,
)


def _private_symbols(original_dir: Path) -> set[str]:
    private: set[str] = set()
    skip_dirs = {"tests", "test", ".git", ".tox", "__pycache__", "build", "dist"}

    for py in original_dir.rglob("*.py"):
        if any(part in skip_dirs for part in py.parts):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            name = getattr(node, "name", None)
            if isinstance(name, str) and name.startswith("_") and not name.startswith("__"):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    private.add(name)
    return private


def _strip_fenced(text: str) -> str:
    return _FENCED.sub("", text)


def check(spec_dir: Path, original_dir: Path) -> dict:
    adrs_dir = spec_dir / "adrs"
    if not adrs_dir.is_dir():
        return {
            "gate": "implementation_leak",
            "pass": False,
            "failures": [{"reason": "adrs_dir_missing", "path": str(adrs_dir)}],
        }

    private = _private_symbols(original_dir) if original_dir.is_dir() else set()
    failures: list[dict] = []
    blocks_total = 0

    for adr in sorted(adrs_dir.rglob("*.md")):
        try:
            text = adr.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = adr.relative_to(spec_dir).as_posix()

        for m in _FENCED.finditer(text):
            blocks_total += 1
            block = m.group(1)
            line_count = block.count("\n") + 1
            if line_count > 8:
                failures.append(
                    {
                        "adr": rel,
                        "leak_kind": "long_code_block",
                        "lines": line_count,
                        "preview": block.splitlines()[0][:120] if block else "",
                        "remediation": (
                            f"{rel} contains a {line_count}-line fenced code block. "
                            f"ADRs describe decisions, not implementations. Replace "
                            f"the block with the *decision* it embodies (algorithm "
                            f"name, complexity bound, contract) or move the code "
                            f"into a contract."
                        ),
                    }
                )

        for priv in private:
            if re.search(rf"\b{re.escape(priv)}\b", text):
                failures.append(
                    {
                        "adr": rel,
                        "leak_kind": "private_symbol_reference",
                        "symbol": priv,
                        "remediation": (
                            f"{rel} references private symbol `{priv}`. Private "
                            f"names are implementation detail; ADRs should reference "
                            f"only the public surface or rename the concept to a "
                            f"behavioral one."
                        ),
                    }
                )

        text_no_fenced = _strip_fenced(text)
        for m in _INLINE_STATEMENT.finditer(text_no_fenced):
            line = text_no_fenced[m.start() : text_no_fenced.find("\n", m.start())]
            failures.append(
                {
                    "adr": rel,
                    "leak_kind": "inline_python_statement",
                    "preview": line.strip()[:120],
                    "remediation": (
                        f"{rel} contains a Python statement outside a fenced "
                        f"block: `{line.strip()[:80]}`. Reword as a behavioral "
                        f"description or move into a contract file."
                    ),
                }
            )

    return {
        "gate": "implementation_leak",
        "pass": len(failures) == 0,
        "failures": failures,
        "stats": {
            "code_blocks_seen": blocks_total,
            "private_symbols_indexed": len(private),
            "leaks_total": len(failures),
        },
    }
