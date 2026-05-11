# ADR-0008: Object Schema Validation

## Status
Accepted

## Context
Some data arrives as Python objects (instances with attributes) rather than dicts. The library must support attribute-based validation with the same marker system as dicts.

## Decision
`Object(schema_dict, cls=UNDEFINED)` is a `dict` subclass that carries a `cls` attribute. When `Schema._compile` encounters an `Object`, it calls `_compile_object`:

- Optionally checks `isinstance(data, schema.cls)` if `cls` is not `UNDEFINED`.
- Iterates the object's attributes via `_iterate_object`, which yields `(key, value)` pairs from `__slots__` (if present) then `__dict__`, avoiding duplicates.
- Validates the pairs with the mapping validator.
- Writes validated values back via `setattr(data, key, value)`.
- Returns the mutated object.

`_iterate_object` handles both slot-based and dict-based objects.

## Consequences
`Object` schemas validate Python objects in-place and return the same object.
