# ADR-0009: Error Position Tracking

## Status
Accepted

## Context
JSON parse errors should report line and column numbers.

## Decision
- `Error` contains a boxed `ErrorImpl { code: ErrorCode, line: usize, column: usize }`.
- `SliceRead` and `StrRead` compute position lazily (only on error) via `memrchr` to find the start of the current line, then count newlines. `IoRead` uses `LineColIterator` which tracks position incrementally.
- `Error::fix_position`: errors created without position (line=0) can have their position filled in later by calling `fix_position(|code| self.error(code))`.
- Serde's `custom` error path parses "at line N column M" suffixes to recover position from round-tripped errors.

## Consequences
Position computation for `SliceRead` is O(offset) on error paths only, not on the hot path. `IoRead` pays incremental cost on every byte.
