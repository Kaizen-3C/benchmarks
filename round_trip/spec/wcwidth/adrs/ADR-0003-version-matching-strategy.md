# ADR-0003: Unicode Version Matching and Selection Strategy

## Status
Accepted

## Context
Callers may pass an arbitrary version string. The library supports only specific Unicode versions. A graceful fallback is required.

## Decision
The function `_wcmatch_version(given_version: str) -> str` resolves a caller-supplied version string to a supported version string using the following rules, in priority order:

1. If `given_version` is `"auto"`, read environment variable `UNICODE_VERSION`; if not set, treat as `"latest"`.
2. If `given_version` is `"latest"`, return the last entry in `list_versions()` (highest supported version).
3. If `given_version` is an exact string match in `list_versions()`, return it.
4. Parse `given_version` into an integer tuple via `_wcversion_value`. If parsing fails, emit a `warnings.warn` and return latest.
5. If the parsed tuple is ≤ the earliest supported version tuple, emit a `warnings.warn` and return the earliest supported version string.
6. Otherwise, iterate `list_versions()` in ascending order. For each consecutive pair `(v_i, v_{i+1})`:
   - If `given_version` matches `v_{i+1}` on all available dotted parts, return `v_{i+1}`.
   - If `v_{i+1}` > `given_version`, return `v_i`.
7. If iteration exhausts without return, return the latest version.

The function is memoized with `lru_cache(maxsize=8)`.

## Consequences
- Callers with versions between supported levels silently receive the nearest lower version.
- Warnings are issued for invalid or out-of-range versions.
- The environment variable `UNICODE_VERSION` allows runtime override without code changes.
