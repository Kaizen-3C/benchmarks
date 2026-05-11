# Contract: voluptuous.schema_builder

See ADR-0002, ADR-0003, ADR-0004, ADR-0005, ADR-0006, ADR-0008, ADR-0010, ADR-0015.

## Constants
- `PREVENT_EXTRA: int = 0`
- `ALLOW_EXTRA: int = 1`
- `REMOVE_EXTRA: int = 2`

## `Undefined`
Class and singleton. `bool(UNDEFINED) == False`. `repr(UNDEFINED) == '...'`.

## `default_factory(value) -> DefaultFactory`
If `value is UNDEFINED` → return `UNDEFINED`. If `callable(value)` and not `Undefined` instance → return as-is. Else → return `lambda: value`.

## `Extra(_) -> None`
Sentinel function. Returns `None`. Used as schema key or sequence element.

`extra` is an alias for `Extra`.

## `Self`
Sentinel object enabling recursive schemas.

## `Schema`
**Constructor:** `Schema(schema: Schemable, required: bool = False, extra: int = PREVENT_EXTRA)`

| Attribute | Type | Description |
|---|---|---|
| `schema` | `Any` | The raw schema passed in |
| `required` | `bool` | Whether bare keys default to required |
| `extra` | `int` | Extra-key policy (0/1/2) |

**`__call__(data) -> Any`** — validates `data` against schema; raises `MultipleInvalid` on failure.

**`__eq__(other)`** — True iff `other` is `Schema` and `other.schema == self.schema`.

**`__str__`** — `str(self.schema)`.

**`__repr__`** — `'<Schema(...) object at 0x...>'`.

**`infer(cls, data, **kwargs) -> Schema`** — classmethod; builds a schema by inspecting the structure of `data` (dicts become `{Required(k): infer(v)}`, lists become `[infer(v)]` or `list`, scalars become `type(v)`).

**`extend(schema, required=None, extra=None) -> Schema`** — returns new merged schema. See ADR-0010.

## `Marker`
**Constructor:** `Marker(schema_: Schemable, msg: Optional[str] = None, description: Any = None)`

Slots: `schema`, `_schema`, `msg`, `description`.

**`__call__(v)`** — validates `v` against inner schema; if `msg` is set and error path depth ≤ 1, re-raises as `Invalid(self.msg)`.

**`__lt__(other)`** — compares inner schema values for sorting.

## `Required(Marker)`
Additional attribute: `default` (from `default_factory`).
**Constructor:** `Required(schema_, msg=None, description=None, default=UNDEFINED)`

## `Optional(Marker)`
Additional attribute: `default` (from `default_factory`).
**Constructor:** `Optional(schema_, msg=None, description=None, default=UNDEFINED)`

## `Exclusive(Marker)`
**Constructor:** `Exclusive(schema_, group_of_exclusion: str, msg=None, description=None)`
Attribute: `group_of_exclusion: str`.

## `Inclusive(Marker)`
**Constructor:** `Inclusive(schema_, group_of_inclusion: str, msg=None, description=None)`
Attribute: `group_of_inclusion: str`.

## `Remove(Marker)`
Keys matching `Remove` schema are excluded from output if they validate.

## `Object(dict)`
**Constructor:** `Object(schema: Any, cls: object = UNDEFINED)`
Attribute: `cls`.

## `VirtualPathComponent(str)`
`__str__` → `'<' + self + '>'`. See ADR-0015.

## `Msg`
**Constructor:** `Msg(schema: Schemable, msg: str, cls: Optional[Type[Error]] = None)`
**`__call__(v)`** — validates `v`; replaces any shallow `Invalid` with `(cls or Invalid)(msg)`.

## `message(msg: str, cls=None)`
Decorator factory. See ADR-0006.

## `raises(exc, msg=None, cls=None)`
Decorator factory. See ADR-0006.

## `validate(*args, **kwargs)`
Decorator factory. See ADR-0006.

## `VirtualPathComponent`
Already described above.
