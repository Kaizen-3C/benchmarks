# ADR-0004: Marker System for Dict Keys

## Status
Accepted

## Context
Dict schema keys need metadata: required vs optional, default values, custom error messages, mutual exclusion groups, inclusion groups.

## Decision
`Marker` is the abstract base class for annotated schema keys. It wraps an inner schema value (`schema` attribute) and optionally carries `msg` and `description`. Subclasses:

- `Required(schema, msg=None, description=None, default=UNDEFINED)` — key must be present; if `default` is provided, it is used when the key is absent. The `default` is stored via `default_factory(value)` so it can be a zero-argument callable or a plain value.
- `Optional(schema, msg=None, description=None, default=UNDEFINED)` — key may be absent; if `default` provided, inserts it into output.
- `Exclusive(schema, group_of_exclusion, msg=None, description=None)` — at most one key from the named group may be present.
- `Inclusive(schema, group_of_inclusion, msg=None, description=None)` — either all keys in the named group are present, or none are (with exception: if all have defaults and none are present, defaults are applied).
- `Remove(schema)` — key is removed from output if it validates; if it does not validate, it is left to other handlers.

`default_factory(value)` returns `UNDEFINED` if given `UNDEFINED`, returns the callable unchanged if it is already callable (and not `Undefined` instance), otherwise wraps in `lambda: value`.

`UNDEFINED` is a singleton instance of `Undefined` class (falsy, repr `...`).

## Consequences
Marker instances are valid dict keys in schema dicts. The mapping compiler checks `isinstance(skey, Required)`, etc. to determine treatment.
