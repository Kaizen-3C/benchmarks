# ADR-0001: Cache Base Class Design

## Status
Accepted

## Context
The library needs a unified base for all cache variants so that size
accounting, `MutableMapping` compliance, and eviction hooks work
consistently across every implementation.

## Decision
`Cache` extends `collections.abc.MutableMapping` and owns all size
accounting logic.  Two internal attributes are central:

- `__data: dict` — the raw key→value store.
- `__size: dict | _DefaultSize` — per-key size in "units".

`maxsize` is the capacity ceiling in units.  `currsize` tracks current
usage.  When `getsizeof` is not provided (or is the default static method
returning `1`), `_DefaultSize` is used as a zero-allocation sentinel that
always returns `1` and asserts only `1` is written.  When a custom
`getsizeof` is supplied the per-key size dict is a real `dict`.

`__setitem__` enforces the ceiling by calling `self.popitem()` repeatedly
until the new item fits, then raises `ValueError` if the single item
exceeds `maxsize`.

## Consequences
Every subclass must implement `popitem()` for eviction; all other
`MutableMapping` methods are inherited from `Cache`.  Name-mangled
attributes (`_Cache__data`, `_Cache__size`, etc.) are accessed by
subclasses via the mangled names where direct access is required.
