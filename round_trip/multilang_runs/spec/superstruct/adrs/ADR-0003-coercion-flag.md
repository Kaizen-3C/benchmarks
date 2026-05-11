# ADR-0003: Coercion is Opt-In via Runtime Flag

## Status
Accepted

## Context
`assert` and `is` should never mutate data. `create` and `mask` need coercion.

## Decision
The `run()` generator accepts a `coerce` boolean option (default `false`).
When `true`, each struct's `coercer` is called before validation and coerced
child values are written back into the parent. `create` passes `{ coerce: true
}` and `mask` passes `{ coerce: true, mask: true }`.

## Consequences
- `assert(data, S)` and `is(data, S)` never call coercers.
- `create(data, S)` always coerces.
- The `mask` flag is threaded through `Context` so `object`'s coercer can
  delete unknown keys recursively.
