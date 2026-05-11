# ADR-0005: Callable Kind Detection (function vs method vs classmethod)

## Status
Accepted

## Context
The deprecation message should accurately state whether a callable is a plain function, a method, or a classmethod.

## Decision
`_kind_for_callable(obj)` inspects the signature of `obj` via `inspect.signature`. The first parameter name determines the kind:

- First parameter named `"self"` → `"method"`
- First parameter named `"cls"` → `"class method"` on Python ≥ 3.9, else `"function (or staticmethod)"`
- No parameters, or any other first parameter name → `"function (or staticmethod)"`
- If `inspect.signature` raises any exception → treated as `"function (or staticmethod)"`

## Consequences
- Detection is heuristic (based on parameter names) and can mis-classify functions that coincidentally use `self` or `cls` as their first parameter name.
- Python < 3.9 cannot reliably distinguish classmethods from plain functions at decoration time, so both report `"function (or staticmethod)"`.
