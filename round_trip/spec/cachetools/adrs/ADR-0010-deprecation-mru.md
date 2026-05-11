# ADR-0010: MRUCache and mru_cache Deprecation

## Status
Accepted

## Context
Most-Recently-Used eviction is rarely the intended policy; it was
included historically but confuses users.

## Decision
`MRUCache.__init__` calls `warnings.warn("MRUCache is deprecated",
DeprecationWarning, stacklevel=2)` unconditionally.  `func.mru_cache`
passes through the warning transitively.

## Consequences
Any code constructing `MRUCache` directly or via `mru_cache` will receive
a `DeprecationWarning`.  The class is still functional and exported in
`__all__` for backwards compatibility.
