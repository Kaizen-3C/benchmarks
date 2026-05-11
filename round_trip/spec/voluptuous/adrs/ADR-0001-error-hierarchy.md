# ADR-0001: Exception Hierarchy Design

## Status
Accepted

## Context
The library must communicate validation failures with enough precision for callers to programmatically distinguish the kind of failure (wrong type, out of range, missing key, etc.) while still allowing catch-all handling via a single base class.

## Decision
All validation exceptions inherit from a two-level hierarchy:

1. `Error(Exception)` — base class for all library exceptions.
2. `Invalid(Error)` — base class for all data-validation failures. Carries `msg` (str), `path` (list of hashable keys/indices), `error_message` (str), and `error_type` (optional str).
3. `MultipleInvalid(Invalid)` — aggregates a list of `Invalid` instances. Delegates `msg`, `path`, and `error_message` properties to `errors[0]`. Supports `add(error)` and `prepend(path)`.
4. `SchemaError(Error)` — raised when the schema itself is malformed.

Concrete leaf exceptions (one per failure mode):

| Class | Meaning |
|---|---|
| `RequiredFieldInvalid` | Required key absent |
| `ObjectInvalid` | Value is not the expected object |
| `DictInvalid` | Value is not a dict |
| `ExclusiveInvalid` | Multiple mutually-exclusive keys present |
| `InclusiveInvalid` | Incomplete inclusion group |
| `SequenceTypeInvalid` | Value is not a sequence |
| `TypeInvalid` | Wrong type |
| `ValueInvalid` | Failed callable evaluation |
| `ContainsInvalid` | Required item absent from container |
| `ScalarInvalid` | Scalar mismatch |
| `CoerceInvalid` | Coercion impossible |
| `AnyInvalid` | No validator in `Any` passed |
| `AllInvalid` | A validator in `All` failed (with custom msg) |
| `MatchInvalid` | Regex mismatch |
| `RangeInvalid` | Out of range |
| `TrueInvalid` | Value not truthy |
| `FalseInvalid` | Value not falsy |
| `BooleanInvalid` | Value not boolean |
| `UrlInvalid` | Invalid URL |
| `EmailInvalid` | Invalid email |
| `FileInvalid` | Not a file path |
| `DirInvalid` | Not a directory path |
| `PathInvalid` | Path does not exist |
| `LiteralInvalid` | Literal mismatch |
| `LengthInvalid` | Length out of bounds |
| `DatetimeInvalid` | Bad datetime string |
| `DateInvalid` | Bad date string |
| `InInvalid` | Value not in container |
| `NotInInvalid` | Value in disallowed container |
| `ExactSequenceInvalid` | Sequence length or element mismatch |
| `NotEnoughValid` | Too few validators passed in `SomeOf` |
| `TooManyValid` | Too many validators passed in `SomeOf` |

## Consequences
Callers can catch `Invalid` broadly or a specific leaf class. `MultipleInvalid` is the primary raised type from `Schema.__call__`.
