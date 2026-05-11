# Contract: wcwidth module (`wcwidth/wcwidth.py`)

Primary computation module. All public symbols are re-exported from `wcwidth/__init__.py`.

See ADR-0002 for binary search, ADR-0003 for version matching, ADR-0004 for caching, ADR-0005 for ZWJ/VS16, ADR-0009 for control characters.

---

## `wcwidth(wc: str, unicode_version: str = 'auto') -> int`

Given a single Unicode character string, return its display width in terminal cells.

**Parameters:**
- `wc`: A single Unicode character (length-1 string). If falsy/empty, treated as NUL (ordinal 0).
- `unicode_version`: Version string such as `'6.0.0'`, `'auto'` (default), or `'latest'`. Resolved via `_wcmatch_version`. See ADR-0003.

**Returns:**
- `0` if the character is zero-width (including NUL U+0000).
- `-1` if the character is a C0/C1 control character (non-printable). See ADR-0009.
- `1` if the character occupies one terminal column.
- `2` if the character occupies two terminal columns (wide/fullwidth).

**Caching:** `@lru_cache(maxsize=1000)` on `(wc, unicode_version)`. See ADR-0004.

---

## `wcswidth(pwcs: str, n: int | None = None, unicode_version: str = 'auto') -> int`

Given a Unicode string, return its total display width in terminal cells.

**Parameters:**
- `pwcs`: Unicode string to measure.
- `n`: If not `None`, measure only the first `n` characters (POSIX compatibility).
- `unicode_version`: Same semantics as `wcwidth`.

**Returns:**
- Non-negative integer: total cell width.
- `-1`: if any character is a C0/C1 control (non-printable).

**Special character handling** (see ADR-0005):
- U+200D (ZWJ): skips itself and the next character.
- U+FE0F (VS16): if preceded by a measurable character and unicode version ≥ 9.0.0, may add 1 to width.

Not cached.

---

## `list_versions() -> list[str]`

Return the list of Unicode version strings supported by this build, in ascending sorted order.

Returns a new list on each call. See ADR-0006 for the exact set of versions.

---

## `_bisearch(ucs: int, table: tuple[tuple[int, int], ...]) -> int`

Binary search helper. Returns `1` if `ucs` is within any `(start, end)` range in `table`, else `0`. See ADR-0002.

---

## `_wcmatch_version(given_version: str) -> str`

Resolve an arbitrary version string to a supported version string. See ADR-0003.

`@lru_cache(maxsize=8)`.

---

## `_wcversion_value(ver_string: str) -> tuple[int, ...]`

Parse a dotted version string into a tuple of integers, e.g. `"9.0.0"` → `(9, 0, 0)`.

`@lru_cache(maxsize=128)`.

---

## Module-level data

- `WIDE_EASTASIAN`: `dict[str, tuple[tuple[int, int], ...]]` — wide codepoint ranges keyed by version. See ADR-0001.
- `ZERO_WIDTH`: `dict[str, tuple[tuple[int, int], ...]]` — zero-width codepoint ranges keyed by version. See ADR-0001.
- `VS16_NARROW_TO_WIDE`: `dict[str, tuple[tuple[int, int], ...]]` — narrow-to-wide-via-VS16 codepoint ranges keyed by version. See ADR-0001, ADR-0005.
