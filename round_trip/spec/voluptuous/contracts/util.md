# Contract: voluptuous.util

## `Lower(v: str) -> str`
Returns `str(v).lower()`.

## `Upper(v: str) -> str`
Returns `str(v).upper()`.

## `Capitalize(v: str) -> str`
Returns `str(v).capitalize()`.

## `Title(v: str) -> str`
Returns `str(v).title()`.

## `Strip(v: str) -> str`
Returns `str(v).strip()`.

## `DefaultTo(default_value, msg=None)`
**`__call__(v)`** — if `v is None`, returns `self.default_value()`; else returns `v`. `default_value` is stored via `default_factory`.

## `SetTo(value)`
**`__call__(v)`** — always returns `self.value()` (ignores input). `value` is stored via `default_factory`.

## `Set(msg=None)`
**`__call__(v)`** — returns `set(v)`; raises `TypeInvalid` on failure.

## `Literal(lit)`
**`__call__(value, msg=None)`** — raises `LiteralInvalid` if `self.lit != value`; else returns `self.lit`.
