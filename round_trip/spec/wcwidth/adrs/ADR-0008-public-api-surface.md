# ADR-0008: Public API Surface

## Status
Accepted

## Context
The library must present a minimal, stable public API while also exposing internal symbols for power users.

## Decision
The `__all__` attribute of `wcwidth/__init__.py` defines the **public** API as exactly three names: `wcwidth`, `wcswidth`, `list_versions`.

All other symbols (`_bisearch`, `_wcmatch_version`, `_wcversion_value`, `WIDE_EASTASIAN`, `ZERO_WIDTH`, `VS16_NARROW_TO_WIDE`) are re-exported from `wcwidth/__init__.py` using explicit imports but are considered private/semi-public (prefixed with `_` or are data tables). They are importable via `from wcwidth import <name>` but may change without notice.

The library version string is `__version__ = '0.6.0'` in `wcwidth/__init__.py`.

## Consequences
- `from wcwidth import *` imports only `wcwidth`, `wcswidth`, `list_versions`.
- Internal functions are accessible for advanced use but carry no stability guarantee.
