# ADR-0005: Zero Width Joiner and Variation Selector-16 Handling in wcswidth

## Status
Accepted

## Context
Modern Unicode includes emoji sequences where combining characters affect the visual width of adjacent characters. Two special cases must be handled:

1. **Zero Width Joiner (ZWJ, U+200D)**: joins two adjacent characters into a single glyph. Both the ZWJ and the following character should not contribute to measured width.
2. **Variation Selector-16 (VS16, U+FE0F)**: when placed after a narrow codepoint that appears in `VS16_NARROW_TO_WIDE`, it causes that codepoint to render as wide (2 columns) instead of narrow (1 column).

## Decision
In `wcswidth()`, a stateful loop processes characters with index `idx`:

- If `char == U+200D`: skip this character and the next (`idx += 2`), do not update `last_measured_char`.
- If `char == U+FE0F` and `last_measured_char` is not `None`:
  - Lazily resolve `_unicode_version` if not yet computed.
  - If `_unicode_version >= (9, 0, 0)`: look up `ord(last_measured_char)` in `VS16_NARROW_TO_WIDE["9.0.0"]` and add the result (0 or 1) to `width`. Reset `last_measured_char = None`.
  - Increment `idx` by 1.
- Otherwise: call `wcwidth(char, unicode_version)`. If result < 0, return -1 immediately. If result > 0, set `last_measured_char = char`. Add result to `width`.

Only a single shared VS16 table keyed at `"9.0.0"` is used regardless of the active Unicode version, because VS16 semantics are considered stable from Unicode 9.0.0 onward.

## Consequences
- The VS16 table is only consulted when the resolved unicode version is ≥ 9.0.0.
- ZWJ sequences are handled by skipping two characters, which may not be correct for all emoji ZWJ sequences but is a pragmatic approximation.
- `wcswidth()` is not cached (unlike `wcwidth()`).
