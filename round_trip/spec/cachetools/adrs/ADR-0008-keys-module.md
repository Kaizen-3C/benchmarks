# ADR-0008: Cache Key Helper Design

## Status
Accepted

## Context
Cache keys must be hashable, support both positional and keyword
arguments, and optionally incorporate argument types for type-sensitive
dispatch.

## Decision
All key functions return a `_HashedTuple` — a `tuple` subclass that
caches its own hash in `self.__dict__["hashvalue"]` to avoid repeated
`tuple.__hash__` calls.  `_HashedTuple` supports `+` and `+=` for
key composition.

A singleton `_kwmark` (instance of `_KWMark`) is inserted between
positional args and sorted keyword pairs so that `f(1, b=2)` and
`f(1, 2)` do not collide.  `_KWMark.__reduce__` returns a factory
function `_kwmark_singleton` so the singleton survives pickling.

Four public functions:

| Function | Signature | Behaviour |
|---|---|---|
| `hashkey` | `(*args, **kwargs)` | Base key from args + sorted kwargs |
| `methodkey` | `(self, *args, **kwargs)` | `hashkey(*args, **kwargs)` — drops `self` |
| `typedkey` | `(*args, **kwargs)` | `hashkey` result extended with `type(v)` for each arg and kwarg value |
| `typedmethodkey` | `(self, *args, **kwargs)` | `typedkey(*args, **kwargs)` — drops `self` |

`_HashedTuple.__getstate__` / `__setstate__` return/accept empty dict so
the cached hash is not pickled (it is recomputed on first access after
unpickling).

## Consequences
`_kwmark` must be a true singleton for pickle round-trips to work.
Keyword argument order is normalised via `sorted(kwargs.items())`.
