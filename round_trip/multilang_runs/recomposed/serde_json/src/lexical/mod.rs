//! Lexical float parsing for the `float_roundtrip` feature.
//!
//! This module provides accurate decimal-to-float conversion using a
//! three-tier approach: fast path, moderate path (extended precision),
//! and slow path (big integer comparison).

pub mod algorithm;
mod bhcomp;
mod bignum;
mod cached;
mod cached_float80;
mod digit;
mod errors;
pub mod exponent;
pub mod float;
mod large_powers;
pub mod math;
pub mod num;
pub mod parse;
pub mod rounding;
mod shift;
mod small_powers;
mod large_powers32;
mod large_powers64;

use self::float::Float;
use self::parse::{parse_concise_float_impl, parse_truncated_float_impl};

/// Parse a float from mantissa × 10^mant_exp.
///
/// Used when the entire decimal representation fits in a u64 mantissa.
pub fn parse_concise_float<F: Float>(mantissa: u64, mant_exp: i32) -> F {
    parse_concise_float_impl::<F>(mantissa, mant_exp)
}

/// Parse a float from separate integer-part bytes, fraction-part bytes,
/// and an exponent.
///
/// Used when the mantissa overflowed u64 during parsing.
pub fn parse_truncated_float<F: Float>(integer: &[u8], fraction: &[u8], exponent: i32) -> F {
    parse_truncated_float_impl::<F>(integer, fraction, exponent)
}
