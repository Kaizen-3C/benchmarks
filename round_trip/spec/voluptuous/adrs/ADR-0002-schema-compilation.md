# ADR-0002: Schema Compilation Strategy

## Status
Accepted

## Context
Schemas may be called many times against different data. Reinterpreting the schema structure on every call would be slow and complex.

## Decision
`Schema.__init__` immediately compiles the schema into a callable `_compiled(path, data) -> data` via `Schema._compile`. Compilation is recursive and dispatches on schema type:

- Has `__voluptuous_compile__` attribute → call it with the Schema instance (allows validators to hook compilation).
- Is the sentinel `Extra` → pass-through lambda.
- Is the sentinel `Self` → forward to `self._compiled` (enables recursive schemas).
- Is a `Marker` subclass → compile the marker's inner schema.
- Is a `Schema` instance → use its `_compiled` directly.
- Is an `Object` → `_compile_object`.
- Is a `collections.abc.Mapping` → `_compile_dict`.
- Is a `list` → `_compile_list`.
- Is a `tuple` → `_compile_tuple`.
- Is a `set` or `frozenset` → `_compile_set`.
- Anything else → `_compile_scalar`.

`_compile_scalar` further dispatches:
- `isinstance(schema, type)` → type-check validator.
- `callable(schema)` → callable validator (wraps `ValueError`→`ValueInvalid`, `TypeError`→`TypeInvalid`).
- Literal value → equality check (with strict type check for primitive types).

## Consequences
Each `Schema` object is callable after construction. Compilation cost is paid once. Recursive schemas require `Self` sentinel to avoid infinite recursion.
