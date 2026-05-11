# ADR-0008: Deprecation Warning Message Format

## Status
Accepted

## Context
The warning message must be consistent and informative.

## Decision
`_build_message(kind, name, reason=None, version=None)` produces:

```
Call to deprecated <kind> <name>. (<extras>)
```

Where `<extras>` is a space-joined list of:
1. `Deprecated in version <version>.` — included only when `version is not None`
2. `<reason>` — included only when `reason` is truthy

The parenthesised extras block `(...)` is omitted entirely when both `version` and `reason` are absent/falsy.

Examples:
- `kind="function (or staticmethod)"`, `name="foo"`, no extras → `"Call to deprecated function (or staticmethod) foo."`
- With `version="1.2"` and `reason="use bar"` → `"Call to deprecated function (or staticmethod) foo. (Deprecated in version 1.2. use bar)"`

## Consequences
- Order is always version first, reason second.
- The message is built once at decoration time and reused for every call, avoiding repeated string formatting overhead.
