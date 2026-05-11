# ADR-0007: _WithSubValidators Base for Any/All/Union/SomeOf

## Status
Accepted

## Context
`Any`, `All`, `Union`, `SomeOf` share the pattern of holding a list of sub-validators and running them in some combination.

## Decision
`_WithSubValidators` is a non-public base class. Its `__voluptuous_compile__` hook is called during schema compilation; it compiles each sub-validator against the parent schema (temporarily adjusting `schema.required`) and stores results in `self._compiled`. It also provides a `__call__` fallback that wraps each validator in a fresh `Schema` for standalone use. Subclasses override `_run(path, value)` and `_exec(validators, value)`.

- `Any` (`Or`) — returns first passing validator's result; raises `AnyInvalid` if all fail.
- `All` (`And`) — chains validators; result of each is passed to next; raises on first failure.
- `Union` (`Switch`) — like `Any` but supports an optional `discriminant` callable that pre-filters validators based on the value.
- `SomeOf` — counts passing validators; raises `NotEnoughValid` or `TooManyValid` if count is outside `[min_valid, max_valid]`.

`discriminant` for `Union` is a callable `(value, validators) -> iterable_of_validators`.

## Consequences
New combination validators can be added by subclassing `_WithSubValidators` and implementing `_run`.
