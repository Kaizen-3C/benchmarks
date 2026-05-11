# Contract: voluptuous.error

All classes in this module are exception types. None have methods beyond what is documented here.

## `Error(Exception)`
Base class. No additional attributes.

## `SchemaError(Error)`
Raised when a schema definition is invalid. No additional attributes.

## `Invalid(Error)`
Raised when data fails validation.

**Constructor:** `Invalid(message: str, path: Optional[List[Hashable]] = None, error_message: Optional[str] = None, error_type: Optional[str] = None)`

| Property/Attribute | Type | Description |
|---|---|---|
| `msg` | `str` | First `args` element (the message string) |
| `path` | `List[Hashable]` | List of keys/indices leading to the invalid value |
| `error_message` | `str` | Secondary message (defaults to `message`) |
| `error_type` | `Optional[str]` | Contextual label (e.g. `'dictionary value'`) |

**`prepend(path: List[Hashable]) -> None`** — prepends `path` to `self._path`.

**`__str__`** — returns `"<message> for <error_type> @ data[<path>]"` with absent parts omitted.

**`__repr__`** — returns `"ClassName(<msg!r>)"`.

## `MultipleInvalid(Invalid)`
Aggregates multiple `Invalid` errors.

**Constructor:** `MultipleInvalid(errors: Optional[List[Invalid]] = None)`

| Attribute | Type | Description |
|---|---|---|
| `errors` | `List[Invalid]` | All collected errors |

Properties `msg`, `path`, `error_message` delegate to `errors[0]`.

**`add(error: Invalid) -> None`** — appends to `errors`.

**`prepend(path: List[Hashable]) -> None`** — calls `prepend` on each error, then updates own path/message from `errors[0]`.

## Leaf exception classes
All inherit from `Invalid`. No additional attributes or methods unless noted.

`RequiredFieldInvalid`, `ObjectInvalid`, `DictInvalid`, `ExclusiveInvalid`, `InclusiveInvalid`, `SequenceTypeInvalid`, `TypeInvalid`, `ValueInvalid`, `ContainsInvalid`, `ScalarInvalid`, `CoerceInvalid`, `AnyInvalid`, `AllInvalid`, `MatchInvalid`, `RangeInvalid`, `TrueInvalid`, `FalseInvalid`, `BooleanInvalid`, `UrlInvalid`, `EmailInvalid`, `FileInvalid`, `DirInvalid`, `PathInvalid`, `LiteralInvalid`, `LengthInvalid`, `DatetimeInvalid`, `DateInvalid`, `InInvalid`, `NotInInvalid`, `ExactSequenceInvalid`, `NotEnoughValid`, `TooManyValid`
