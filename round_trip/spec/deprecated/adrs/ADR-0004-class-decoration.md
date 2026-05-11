# ADR-0004: Class Decoration via __new__ Patching

## Status
Accepted

## Context
When a class is decorated with `@deprecated`, every instantiation must emit a warning.

## Decision
`_decorate_class` replaces `cls.__new__` with a `staticmethod`-wrapped shim `wrapped_new(subcls, *args, **kwargs)`. The shim:
1. Emits the deprecation warning.
2. Delegates to the original `__new__`. If the original `__new__` is exactly `object.__new__`, it is called as `object.__new__(subcls)` (no extra args) to avoid a `TypeError` on Python 3. Otherwise it is called with the full `(subcls, *args, **kwargs)`.

The warning message uses `kind="class"` and `name=cls.__name__`.

## Consequences
- Subclasses of the deprecated class will also trigger the warning when instantiated, because `__new__` is inherited.
- The class object itself is returned unmodified except for the patched `__new__`.
