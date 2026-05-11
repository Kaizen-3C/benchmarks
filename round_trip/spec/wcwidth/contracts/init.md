# Contract: wcwidth package (`wcwidth/__init__.py`)

Top-level package. Re-exports all public and semi-public symbols from `wcwidth.wcwidth` so they are importable directly from the `wcwidth` package namespace.

**`__all__`**: `('wcwidth', 'wcswidth', 'list_versions')` — only these three are exported by `import *`.

**`__version__`**: `'0.6.0'` (string constant).

Re-exported names (importable but not in `__all__`):
- `ZERO_WIDTH`
- `WIDE_EASTASIAN`
- `VS16_NARROW_TO_WIDE`
- `_bisearch`
- `_wcmatch_version`
- `_wcversion_value`
