# ADR-0014: Coerce Validator with Enum Support

## Status
Accepted

## Context
Data often arrives as strings that need to be converted to typed values.

## Decision
`Coerce(type, msg=None)` calls `type(v)` and catches `(ValueError, TypeError, decimal.InvalidOperation)`. If the type is an `Enum` subclass (detected via optional import of `enum.Enum`), the error message is extended with the list of valid enum values.

`Enum` is imported at module top level; if the import fails, `Enum = None` and the enum branch is skipped.

## Consequences
`Coerce` works with any callable type constructor. Enum detection is optional and degrades gracefully.
