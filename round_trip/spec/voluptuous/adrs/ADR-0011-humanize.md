# ADR-0011: Human-Readable Error Messages via humanize module

## Status
Accepted

## Context
Default `str(MultipleInvalid)` provides path and message but not the offending value, which is often the most useful debugging information.

## Decision
`voluptuous.humanize` (not re-exported from top-level `__init__`) provides two functions:

1. `humanize_error(data, validation_error, max_sub_error_length=500)` — for each error in the `MultipleInvalid` (or single `Invalid`), walks `data` along `error.path` to extract the offending value, appends `Got <repr>` to the message. Values longer than `max_sub_error_length` chars are truncated with `...`. `VirtualPathComponent` in a path causes value extraction to be skipped for that error.
2. `validate_with_humanized_errors(data, schema, max_sub_error_length=500)` — calls `schema(data)` and on `Invalid`, re-raises as `Invalid(humanize_error(...))`.

## Consequences
`humanize` is a separate module that must be imported explicitly. It depends on `voluptuous.schema_builder.VirtualPathComponent`.
