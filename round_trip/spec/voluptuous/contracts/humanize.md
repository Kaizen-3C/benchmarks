# Contract: voluptuous.humanize

Not re-exported from package top-level. Must be imported as `from voluptuous.humanize import ...`.

## `humanize_error(data, validation_error: Invalid, max_sub_error_length: int = 500) -> str`
Returns a multi-line string. Each line corresponds to one error. Lines have format `"<str(error)>. Got <repr(value)>"` when the offending value can be extracted, or just `str(error)` otherwise. Values longer than `max_sub_error_length` are truncated. See ADR-0011.

## `validate_with_humanized_errors(data, schema: Schema, max_sub_error_length: int = 500) -> Any`
Calls `schema(data)`. On `Invalid`, raises `Invalid(humanize_error(...))`. See ADR-0011.
