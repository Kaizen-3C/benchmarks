# ADR-0010: Internal Number Representation

## Status
Accepted

## Context
JSON numbers can be positive integers, negative integers, or floats.

## Decision
Without `arbitrary_precision`, `Number` stores a `Copy` enum `N { PosInt(u64), NegInt(i64), Float(f64) }`. Float values are always finite (NaN/Inf are rejected). The `ParserNumber` enum in `de.rs` mirrors this for parsed values. During parsing: integers that fit in `u64` are stored as `PosInt`; negative numbers are stored as `NegInt(i64)` if they fit, otherwise converted to float; overflow triggers the long-integer float path. `-0` and underflowing negatives are stored as `Float`.

## Consequences
`Number` is `Copy` (without `arbitrary_precision`), `PartialEq`, `Eq`, `Hash`. Float `0.0` and `-0.0` are hashed identically (both as `0.0f64.to_bits()`).
