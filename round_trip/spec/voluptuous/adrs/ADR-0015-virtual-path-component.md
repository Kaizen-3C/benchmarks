# ADR-0015: VirtualPathComponent for Non-Data Path Segments

## Status
Accepted

## Context
Some errors (e.g., exclusion/inclusion group violations) do not correspond to a data key; they need a path segment that displays distinctively.

## Decision
`VirtualPathComponent(str)` is a `str` subclass. Its `__str__` returns `<value>` (angle-bracket-wrapped). Its `__repr__` delegates to `__str__`. Used as the final path element in `ExclusiveInvalid` and `InclusiveInvalid` errors.

In `humanize_error`, a `VirtualPathComponent` in a path causes value extraction to abort (raises `KeyError`), so no `Got <value>` is appended for those errors.

## Consequences
`VirtualPathComponent` is importable from the top-level package and from `schema_builder`.
