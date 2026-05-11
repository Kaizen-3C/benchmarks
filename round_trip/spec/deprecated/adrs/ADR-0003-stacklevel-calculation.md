# ADR-0003: Stack Level Calculation for Warning Origin

## Status
Accepted

## Context
`warnings.warn` uses a `stacklevel` argument to point to the call site of the deprecated function rather than the decorator internals.

## Decision
The base stacklevel used inside the wrapper is **3**:
- Frame 0: `_warn` (or `warnings.warn` call site inside the wrapper)
- Frame 1: `wrapper` (the `functools.wraps`-decorated shim)
- Frame 2: the immediate caller of the deprecated function

An additional `extra_stacklevel` integer parameter (default `0`) is added to accommodate wrapper layers placed on top of the deprecated function by the caller. The final stacklevel is `3 + int(extra_stacklevel)`.

## Consequences
- Callers that wrap deprecated functions in their own layers must pass `extra_stacklevel=N` to get accurate file/line attribution.
- The stacklevel for class decoration (`_decorate_class`) follows the same formula applied inside `wrapped_new`.
