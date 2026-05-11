# ADR-0012: Number Validator — Decimal Precision and Scale

## Status
Accepted

## Context
Financial and scientific applications need to validate that numeric strings have specific precision (total significant digits) and scale (digits after decimal point).

## Decision
`Number(precision=None, scale=None, msg=None, yield_decimal=False)` converts the input to `decimal.Decimal` via `str(v)` first (preserving trailing zeros), then uses `Decimal.as_tuple()` to extract `(sign, digits, exponent)`.

Precision and scale are computed as:
- If `exponent >= 0`: `scale = 0`, `precision = len(digits) + exponent`.
- If `exponent < 0`: `scale = -exponent`, `precision = len(digits)`.

Validation fails if `precision` param is set and computed precision differs, or if `scale` param is set and computed scale differs. If both are set and both differ, a combined error message is used.

If `yield_decimal=True`, returns the `Decimal` object; otherwise returns the original value unchanged.

## Consequences
`Number` accepts strings and numeric types. It does not coerce; use `Coerce` first if needed.
