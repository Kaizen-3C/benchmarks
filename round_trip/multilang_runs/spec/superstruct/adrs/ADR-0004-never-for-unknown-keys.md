# ADR-0004: `never()` Struct for Unknown Object Keys

## Status
Accepted

## Context
`object(schema)` should reject keys not listed in the schema.

## Decision
`object`'s `entries` generator collects all keys present in the value, removes
known keys, then yields the remaining unknown keys paired with the singleton
`Never = never()` struct. Since `never()` always fails validation, any extra
key produces a failure with `type: 'never'`.

## Consequences
- Unknown properties always produce `{ type: 'never', ... }` failures.
- `type(schema)` does NOT yield unknown keys — it is the open/structural
  equivalent of `object`.
- `mask()` avoids this failure by deleting unknown keys before entries are
  iterated (via the `mask` flag in the object coercer).
