# ADR-0002: Binary Search Over Sorted Interval Table

## Status
Accepted

## Context
Unicode lookup tables contain hundreds of codepoint ranges. A hash set of individual codepoints would require tens of thousands of entries. A sorted interval table with binary search is more memory-efficient.

## Decision
The function `_bisearch(ucs: int, table: tuple[tuple[int, int], ...]) -> int` performs a standard binary search over a sorted list of `(start, end)` inclusive integer pairs.

Algorithm:
1. If `ucs < table[0][0]` or `ucs > table[-1][1]`, return `0`.
2. Binary search: maintain `lbound=0`, `ubound=len(table)-1`.
3. At each step compute `mid = (lbound + ubound) // 2`.
4. If `ucs > table[mid][1]`, set `lbound = mid + 1`.
5. If `ucs < table[mid][0]`, set `ubound = mid - 1`.
6. Otherwise return `1`.
7. If loop ends without match, return `0`.

Returns `1` if found, `0` if not found.

## Consequences
- Lookup is `O(log n)` where `n` is the number of ranges in the table (typically 50–200).
- Results are further cached by `wcwidth()` via `lru_cache`.
