# ADR-0002: Per-Decorator Warning Action Override

## Status
Accepted

## Context
Python's `warnings` module provides global and per-category filters. Users sometimes need finer control — e.g., turning a specific deprecated function into an error while leaving others as warnings.

## Decision
`classic.deprecated` (and `sphinx.deprecated` by extension) accepts an `action` parameter accepting any value accepted by `warnings.simplefilter` (`"error"`, `"ignore"`, `"always"`, `"default"`, `"once"`, `"module"`, `"all"`, or `None`).

- When `action=None` (default): `warnings.warn` is called directly with no filter manipulation.
- When `action` is a string: a `warnings.catch_warnings()` context manager is entered, `warnings.simplefilter(action, category)` is applied, and then `warnings.warn` is called inside that context.

This ensures the action applies only to the single warning site without affecting other warnings globally.

## Consequences
- The action override takes priority over any globally configured filters because `catch_warnings` + `simplefilter` inserts a filter at the front of the filter chain.
- `action="error"` will raise the warning as an exception even if the caller has set `warnings.simplefilter("ignore")` globally.
