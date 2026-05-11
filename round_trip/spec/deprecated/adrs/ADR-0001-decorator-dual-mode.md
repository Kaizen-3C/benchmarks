# ADR-0001: Dual-Mode Decorator Invocation

## Status
Accepted

## Context
The `deprecated` decorator must support two call signatures:

1. **Bare** (no parentheses): `@deprecated` — the decorated object is passed directly as the first argument.
2. **Parameterised** (with parentheses): `@deprecated(reason="...", version="1.0")` — returns a decorator function.

## Decision
Both `classic.deprecated` and `sphinx.deprecated` detect bare usage by checking whether `reason` is callable AND all other parameters hold their default values (`version=None`, `category=DeprecationWarning`, `action=None`, `extra_stacklevel=0`; and additionally `line_length=70` for sphinx). When that condition is true the first argument is treated as the decorated object, `reason` is set to `None`, and decoration proceeds immediately. Otherwise a decorator closure is returned.

## Consequences
- No separate `@deprecated_with_args` / `@deprecated` split is needed.
- The heuristic relies on `reason` being callable only when it is actually the target object — callers must not pass a callable as a reason string.
