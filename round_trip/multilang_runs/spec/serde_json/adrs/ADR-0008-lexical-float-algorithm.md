# ADR-0008: Lexical Float Parsing Algorithm

## Status
Accepted

## Context
Accurate decimal-to-float conversion is non-trivial. The `lexical` sub-crate (adapted from `rust-lexical` by @Alexhuszagh) provides a three-tier approach.

## Decision
1. **Fast path** (`fast_path`): if the mantissa and exponent fit within exact representation bounds for the float type, compute directly using `pow10`.
2. **Moderate path** (`moderate_path`): multiply an extended-precision (80-bit, `ExtendedFloat { mant: u64, exp: i32 }`) float by cached powers from `cached_float80.rs`. Check if the result is accurate within error bounds.
3. **Slow path** (`bhcomp`): compare the actual mantissa (as a big integer) with the midpoint `b+h` of adjacent floats using `Bigint` arithmetic with Karatsuba multiplication.

Pre-computed tables in `cached_float80.rs` store 66 large powers of 10 (every 10th power from 10^-350 to 10^300) plus 10 small powers.

## Consequences
The algorithm is adapted from a proven implementation and prioritizes correctness over simplicity. The big-integer path is only reached for pathological inputs.
