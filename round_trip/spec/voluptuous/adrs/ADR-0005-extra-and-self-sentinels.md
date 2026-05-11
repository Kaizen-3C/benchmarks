# ADR-0005: Extra and Self Sentinels

## Status
Accepted

## Context
Schema authors need a way to say "allow any extra key/value" within a specific position, and to write self-referencing schemas.

## Decision
- `Extra` is a function (accepts one argument, returns `None`) that serves as a sentinel. When used as a dict schema key, it matches any key not already matched. When used as a sequence element, it matches any element. The module-level name `extra` is an alias for `Extra`.
- `Self` is a sentinel object (module-level, defined in `schema_builder`). When `_compile` encounters `Self`, it emits a lambda that delegates to `self._compiled`, enabling schemas that validate recursive data structures.
- Constants `PREVENT_EXTRA = 0`, `ALLOW_EXTRA = 1`, `REMOVE_EXTRA = 2` control dict extra-key behaviour at the Schema level.

## Consequences
`Extra` and `Self` are importable from the top-level package. Using `Schema(required=True)` makes all bare (non-Marker) keys behave as `Required` by default.
