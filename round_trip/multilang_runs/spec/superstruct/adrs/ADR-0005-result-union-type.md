# ADR-0005: Flexible Validator Return Type (`Result`)

## Status
Accepted

## Context
Validator and refiner functions need to be ergonomic for common cases (return
`true`/`false`/string) while also supporting structured partial `Failure`
objects and iterables of failures.

## Decision
`Result = boolean | string | Partial<Failure> | Iterable<boolean | string | Partial<Failure>>`

`toFailure()` normalises a single result:
- `true` → no failure
- `false` → failure with default message
- `string` → failure with that message
- `Partial<Failure>` → merged with defaults

`toFailures()` wraps a non-iterable in an array then maps `toFailure`.

## Consequences
Validators can return `true`, `false`, a string message, a partial failure
object, or an iterable of any of the above. This covers all practical
validation patterns without requiring a dedicated result class.
