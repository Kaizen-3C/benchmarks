# ADR-0009: C0/C1 Control Character Handling

## Status
Accepted

## Context
Control characters (e.g., `\x01`, `\x1b`) are not printable but have defined codepoint values. A consistent return value is needed.

## Decision
In `wcwidth(wc)`:
- Codepoints in range `1–31` (C0 controls, excluding NUL) return `-1`.
- Codepoints in range `0x7F–0x9F` (DEL and C1 controls) return `-1`.
- NUL (`U+0000`) is handled by the ZERO_WIDTH table and returns `0`.
- Printable ASCII `32–126` (`0x20–0x7E`) returns `1` via an early-exit optimisation before any table lookup.

In `wcswidth()`: if any character returns `-1` from `wcwidth()`, `wcswidth()` immediately returns `-1`.

## Consequences
- The early-exit for printable ASCII provides ~40% speedup for ASCII-heavy input.
- NUL returns 0, not -1, which matches the POSIX wcwidth(3) specification.
