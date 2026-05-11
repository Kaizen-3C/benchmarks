# ADR-0002: Early-Exit Validation with Lazy Full-Failure Collection

## Status
Accepted

## Context
Validation of large nested objects can be expensive. Users sometimes want just
the first error (throw/assert path) but sometimes want all errors.

## Decision
`run()` is a generator that yields failures lazily. `validate()` reads the
first tuple; if it is a failure it constructs a `StructError` whose `failures()`
method resumes the same generator to collect all remaining failures. This means
full traversal only happens when `error.failures()` is explicitly called.

The `StructError` caches the result of `failures()` after the first call.

## Consequences
- `assert` and `is` exit after the first failure — O(1) for invalid data.
- `error.failures()` triggers complete traversal — O(n) on demand.
- Refiners are skipped entirely if any validator in the subtree failed (status
  `not_valid`). Refiners run if only refinements of children failed
  (`not_refined`).
