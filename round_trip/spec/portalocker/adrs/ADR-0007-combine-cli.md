# ADR-0007: `__main__.py` Combine CLI

## Status
Accepted

## Context
The package ships a CLI (`python -m portalocker combine`) that merges all source modules into a single `dist/portalocker.py` file for zero-dependency distribution.

## Decision
`__main__.py` implements an `argparse`-based CLI with one subcommand `combine`:
- Default output: `<repo_root>/dist/portalocker.py`.
- Walks `portalocker/__init__.py` recursively via `_read_file()`, following relative imports.
- Strips: `from __future__ import ...` lines, `try:` blocks, `except ImportError` blocks, Redis-related lines, useless self-assignments (`x = x\n`).
- Prepends `from __future__ import annotations\n\n` to output.
- Uses regex patterns: `_NAMES_RE`, `_RELATIVE_IMPORT_RE`, `_USELESS_ASSIGNMENT_RE`, `_FUTURE_IMPORT_RE`.

## Consequences
- Not part of the runtime public API; only used for packaging.
- Not tested by the main test suite.
