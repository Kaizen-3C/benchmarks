# ADR-0004: Arbitrary Precision Numbers via `arbitrary_precision` Feature

## Status
Accepted

## Context
Standard JSON numbers are stored as `u64`, `i64`, or `f64`. Some applications require lossless representation of numbers like `0.1` or very large integers.

## Decision
When `arbitrary_precision` is enabled, `Number`'s inner type `N` becomes `String` instead of a `Copy` enum. The `TOKEN = "$serde_json::private::Number"` sentinel is used in a newtype struct serialization protocol so that `Number` can be serialized/deserialized through any Serde-compatible format that supports maps. `ParserNumber::String(String)` variant is added when the feature is enabled.

## Consequences
The `Number` type gains `as_str() -> &str`. Hashing and equality are string-based. Interoperability with formats that don't support this protocol requires `arbitrary_precision` to be disabled.
