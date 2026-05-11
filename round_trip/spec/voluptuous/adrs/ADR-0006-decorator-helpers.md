# ADR-0006: message, raises, validate Decorators

## Status
Accepted

## Context
Simple validator functions written with `@message` and `@truth` need a concise way to attach custom error messages and exception classes without repeating boilerplate.

## Decision
Three decorator factories are defined in `schema_builder`:

1. `message(msg, cls=None)` — wraps a validator function so that any `Invalid` raised at depth ≤ 1 is replaced with `(cls or Invalid)(msg)`. Used as `@message('expected boolean', cls=BooleanInvalid)`.
2. `raises(exc, msg=None, cls=None)` — wraps a validator so that a named exception type `exc` is caught and re-raised as `(cls or Invalid)(msg or str(e))`.
3. `validate(*args, **kwargs)` — decorator that wraps a function so its arguments and/or return value are validated by schemas provided as positional or keyword arguments. Schema arguments correspond to the wrapped function's parameters by position/name; a special `__return__` key validates the return value.

These are importable from the top-level package.

## Consequences
Validator authors can write plain Python functions and annotate them with `@message`/`@raises` rather than writing try/except blocks manually.
