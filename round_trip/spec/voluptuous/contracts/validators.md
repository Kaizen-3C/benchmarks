# Contract: voluptuous.validators

See ADR-0007, ADR-0012, ADR-0013, ADR-0014.

## `truth(f: Callable) -> Callable`
Decorator. Wraps `f` so that a falsy return raises `Invalid('not a valid value')`.

## `Coerce(type, msg=None)`
**`__call__(v)`** — returns `type(v)`; raises `CoerceInvalid` on `ValueError`, `TypeError`, `InvalidOperation`. See ADR-0014.

## `IsTrue(v)`
Decorated with `@message('value was not true', cls=TrueInvalid)` and `@truth`. Raises `TrueInvalid` if `v` is falsy.

## `IsFalse(v)`
Raises `FalseInvalid` if `v` is truthy.

## `Boolean(v)`
Accepts strings `'1','true','yes','on','enable'` → `True`; `'0','false','no','off','disable'` → `False`. Other strings raise `BooleanInvalid`. Non-strings: `bool(v)`.

## `Any(*validators, msg=None)` / `Or`
Returns result of first passing validator. Raises `AnyInvalid` if all fail. Supports `discriminant` kwarg (unused by `Any`). See ADR-0007.

## `All(*validators, msg=None)` / `And`
Chains validators; result flows left to right. Raises first `Invalid` encountered (or `AllInvalid` if `msg` set). See ADR-0007.

## `Union(*validators, msg=None, discriminant=None)` / `Switch`
Like `Any` but accepts `discriminant(value, validators) -> filtered_validators`. See ADR-0007.

## `SomeOf(validators, min_valid=None, max_valid=None, msg=None)`
Counts passing validators. Requires at least one of `min_valid`/`max_valid`. Raises `NotEnoughValid` or `TooManyValid`. See ADR-0007.

## `Match(pattern, msg=None)`
**`__call__(v)`** — `pattern.match(v)`; raises `MatchInvalid` on no match or `TypeError`.

## `Replace(pattern, substitution, msg=None)`
**`__call__(v)`** — returns `pattern.sub(substitution, v)`.

## `Email(v)`
Validates email format. Raises `EmailInvalid`. See ADR-0013.

## `FqdnUrl(v)`
Validates fully-qualified-domain URL. Raises `UrlInvalid`. See ADR-0013.

## `Url(v)`
Validates URL (scheme + netloc). Raises `UrlInvalid`. See ADR-0013.

## `IsFile(v)`
Raises `FileInvalid` if `os.path.isfile(v)` is falsy.

## `IsDir(v)`
Raises `DirInvalid` if `os.path.isdir(v)` is falsy.

## `PathExists(v)`
Raises `PathInvalid` if `v is None` or `os.path.exists(v)` is false.

## `Maybe(validator, msg=None)`
Equivalent to `Any(None, validator, msg=msg)`. Accepts `None` or anything the validator accepts.

## `Range(min=None, max=None, min_included=True, max_included=True, msg=None)`
**`__call__(v)`** — checks bounds; raises `RangeInvalid`. NaN always raises. Boundaries are inclusive by default.

## `Clamp(min=None, max=None, msg=None)`
**`__call__(v)`** — clips `v` to `[min, max]`; raises `RangeInvalid` on `TypeError`.

## `Length(min=None, max=None, msg=None)`
**`__call__(v)`** — checks `len(v)`; raises `LengthInvalid`; raises `RangeInvalid` on `TypeError`.

## `Datetime(format=None, msg=None)`
Default format: `'%Y-%m-%dT%H:%M:%S.%fZ'`. Raises `DatetimeInvalid`.

## `Date(format=None, msg=None)`
Default format: `'%Y-%m-%d'`. Raises `DateInvalid`.

## `In(container, msg=None)`
**`__call__(v)`** — raises `InInvalid` if `v not in container`.

## `NotIn(container, msg=None)`
**`__call__(v)`** — raises `NotInInvalid` if `v in container`.

## `Contains(item, msg=None)`
**`__call__(v)`** — raises `ContainsInvalid` if `item not in v`.

## `ExactSequence(validators, msg=None, **kwargs)`
**`__call__(v)`** — requires `isinstance(v, (list, tuple))` and `len(v) == len(validators)`. Validates element `i` against `validators[i]`. See ADR-0009.

## `Unique(msg=None)`
**`__call__(v)`** — raises `Invalid` if `v` contains duplicates; raises `TypeInvalid` if unhashable.

## `Equal(target, msg=None)`
**`__call__(v)`** — raises `Invalid` if `v != target`.

## `Unordered(validators, msg=None, **kwargs)`
**`__call__(v)`** — each element must match at least one unused validator. See ADR-0009.

## `Number(precision=None, scale=None, msg=None, yield_decimal=False)`
See ADR-0012.
