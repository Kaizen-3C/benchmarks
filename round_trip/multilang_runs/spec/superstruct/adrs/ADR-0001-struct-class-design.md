# ADR-0001: Struct Class as Central Validation Unit

## Status
Accepted

## Context
The library needs a composable, typed validation primitive that can hold
coercion logic, validation logic, refinement logic, and entry-point iteration
for nested values.

## Decision
A single generic class `Struct<T, S>` encapsulates:
- `type`: string name used in error messages
- `schema`: raw schema (S) for introspection / composition
- `coercer`: transforms unknown input before validation (used only in `create`/`mask`)
- `validator`: checks structural correctness, returns `Iterable<Failure>`
- `refiner`: checks additional constraints after structure is confirmed valid
- `entries`: yields `[key, value, Struct]` triples for recursive traversal

Instance methods `assert`, `create`, `is`, `mask`, `validate` all delegate to
the corresponding module-level helpers.

## Consequences
All struct factories return `new Struct(...)` instances. Composing structs
(e.g. `optional`, `nullable`, `refine`) spread the existing struct's props via
`{ ...struct }` and override only what changes. This preserves the coercer and
entries unless explicitly overridden.
