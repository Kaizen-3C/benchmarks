# ADR-0010: Schema.extend for Incremental Schema Building

## Status
Accepted

## Context
Users need to derive a new schema from an existing one by adding or overriding fields.

## Decision
`Schema.extend(schema, required=None, extra=None)` merges a new schema dict into a copy of the existing schema dict. Rules:

- Both `self.schema` and the argument must be dicts (or a `Schema` wrapping a dict); raises `SchemaError` otherwise.
- Key identity for matching uses the inner schema value for `Marker` keys, bare value otherwise.
- If both old and new values are dicts, they are recursively merged via `Schema(old_value).extend(new_value)`.
- Otherwise the new value replaces the old.
- New keys not present in the old schema are added.
- `required` and `extra` default to the original schema's values if not specified.
- Returns a new `Schema` instance of the same class.

## Consequences
`extend` enables schema inheritance without mutation. Marker keys are matched by their inner schema value, so `Required('x')` and `Optional('x')` are considered the same key identity.
