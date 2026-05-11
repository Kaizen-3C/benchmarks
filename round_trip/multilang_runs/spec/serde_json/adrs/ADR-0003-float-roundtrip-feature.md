# ADR-0003: Optional Accurate Float Round-Trip via `float_roundtrip` Feature

## Status
Accepted

## Context
Parsing floats from JSON using naive `f64` arithmetic can produce 1-ULP errors. The `float_roundtrip` feature enables a more accurate but ~2x slower algorithm based on the `lexical` sub-crate.

## Decision
When `float_roundtrip` is disabled, `f64_from_parts` uses a simple table-based multiplication approach (with a static `POW10` table in `de.rs`). When enabled, it delegates to `lexical::parse_concise_float` and `lexical::parse_truncated_float`, which use the extended-precision moderate/slow path algorithm. The `single_precision` field on `Deserializer` (only present under `float_roundtrip`) enables f32 parsing via the same infrastructure.

## Consequences
Users who need `f64 → JSON → f64` identity must opt in. The `lexical` module is only compiled under `float_roundtrip`.
