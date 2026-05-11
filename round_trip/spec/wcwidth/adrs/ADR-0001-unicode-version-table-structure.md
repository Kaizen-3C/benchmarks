# ADR-0001: Unicode Version-Keyed Lookup Tables

## Status
Accepted

## Context
The library must return character display widths that are correct for a caller-specified Unicode version level, not just the latest. Different terminals and environments conform to different Unicode versions.

## Decision
Three lookup tables are maintained, each a Python `dict` mapping a Unicode version string (e.g., `"9.0.0"`) to a tuple of `(start, end)` integer pairs representing inclusive codepoint ranges:

- `WIDE_EASTASIAN`: codepoints that occupy 2 terminal columns
- `ZERO_WIDTH`: codepoints that occupy 0 terminal columns
- `VS16_NARROW_TO_WIDE`: codepoints that are narrow by default but become wide when followed by Variation Selector-16 (U+FE0F)

Each table is stored in its own module (`table_wide.py`, `table_zero.py`, `table_vs16.py`). The range tuples are **half-open** — `(start, end)` covers codepoints `start <= cp < end` in the source generation script but are stored as inclusive pairs `(start, end-1)` in the final tables for binary search compatibility.

## Consequences
- Binary search (`O(log n)`) is used for lookup rather than a set or dict.
- Adding a new Unicode version requires appending a new key; old versions are never modified.
- The tables are imported at module load time; no file I/O at call time.
