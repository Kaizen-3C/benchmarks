# ADR-0006: StructError Extends TypeError

## Status
Accepted

## Context
Validation errors need to be catchable as standard JS errors while carrying
structured metadata.

## Decision
`StructError extends TypeError`. The constructor receives the first `Failure`
and a generator-factory for subsequent failures. It:
- Spreads all `Failure` fields onto `this` (via `Object.assign`)
- Sets `message` to the path-prefixed failure message, or the custom
  `explanation` if provided
- Sets `this.cause` to the raw message when `explanation` overrides it
- Exposes `failures(): Array<Failure>` (cached after first call)

## Consequences
`instanceof TypeError` is true. `e.key`, `e.value`, `e.type`, `e.path`,
`e.branch`, `e.refinement` are all direct properties. Custom messages
(passed to `assert`/`create`/`validate`) become `e.message`; original
message is accessible via `e.cause`.
