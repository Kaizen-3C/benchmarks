//! Big-integer comparison for the slow path of float parsing.
//!
//! This module implements the "b + h" comparison algorithm:
//! compare the actual decimal mantissa (as a bignum) against the
//! midpoint between two adjacent floating-point values to determine
//! the correct rounding direction.

use super::bignum::*;
use super::digit::*;
use super::exponent::*;
use super::float::*;
use super::math::*;
use super::num::*;
use super::rounding::*;

/// Calculate `b` (the float value as a bignum scaled to the same exponent).
fn bignum_from_float<F: Float>(exponent: i32, mantissa: u64) -> Bigint {
    let mut result = Bigint::new();
    result.data.push(mantissa as Limb);
    #[cfg(not(fast_arithmetic = "64"))]
    {
        if mantissa > u32::MAX as u64 {
            result.data.push((mantissa >> 32) as Limb);
        }
    }

    if exponent > 0 {
        // Multiply by 2^exponent
        result.imul_pow2(exponent as u32);
    } else if exponent < 0 {
        // This case should not occur in normal usage since we scale appropriately
    }
    result
}

/// Calculate the number of digits in the mantissa representation.
fn count_digits(digits: &[u8]) -> usize {
    digits.len()
}

/// Multiply a bigint by 10^exp.
fn bigint_mul_pow10(bigint: &mut Bigint, exp: usize) {
    if exp != 0 {
        bigint.imul_pow10(exp as u32);
    }
}

/// Multiply a bigint by 2^exp.
fn bigint_mul_pow2(bigint: &mut Bigint, exp: u32) {
    if exp != 0 {
        bigint.imul_pow2(exp);
    }
}

/// Compare a decimal value (integer + fraction digits with given exponent)
/// to a floating-point midpoint `b + h`.
///
/// Returns the ordering of the decimal value relative to `b + h`.
///
/// # Arguments
/// * `integer` - integer part digits (ASCII bytes)
/// * `fraction` - fraction part digits (ASCII bytes)  
/// * `exponent` - the base-10 exponent of the full value
/// * `fp` - the extended float representing the lower bound `b`
pub fn bhcomp<F: Float>(
    b: ExtendedFloat,
    integer: &[u8],
    fraction: &[u8],
    exponent: i32,
) -> core::cmp::Ordering {
    // We want to compare:
    //   decimal_value  vs  b + h
    //
    // where b is the float we've chosen and h = 0.5 ULP of b.
    //
    // We scale both sides to integers by multiplying by appropriate powers of 2 and 10.

    let mantissa = b.mant;
    let raw_exp = b.exp;

    // The float b has value: mantissa * 2^raw_exp
    // The ULP of b is 2^raw_exp, so h = 2^(raw_exp - 1)
    // b + h = mantissa * 2^raw_exp + 2^(raw_exp-1)
    //       = (2*mantissa + 1) * 2^(raw_exp - 1)

    // Count total decimal digits
    let integer_len = integer.len();
    let fraction_len = fraction.len();

    // The decimal value = (integer_digits * 10^fraction_len + fraction_digits) * 10^(exponent - fraction_len... adjusted)
    // More precisely:
    //   decimal_value = N * 10^e
    // where N is the concatenated integer+fraction as an integer, and
    //   e = exponent - fraction_len (since fraction_len digits are after the decimal point)

    // Build bignum for the decimal mantissa N
    let mut decimal = Bigint::new();
    // Add integer digits
    for &byte in integer.iter() {
        let digit = char_to_digit(byte) as Limb;
        decimal.imul_small(10);
        decimal.iadd_small(digit);
    }
    // Add fraction digits
    for &byte in fraction.iter() {
        let digit = char_to_digit(byte) as Limb;
        decimal.imul_small(10);
        decimal.iadd_small(digit);
    }

    // The decimal exponent after accounting for fraction:
    // decimal_value = decimal * 10^(exponent - fraction_len)
    // But exponent here is already the overall exponent (e.g., from "1.5e10" exponent=10 means 1.5*10^10)
    // Actually, the exponent passed in is the raw exponent, and fraction digits shift it.
    // decimal_value = N * 10^e where e = exponent - (int)fraction_len
    let decimal_exp = exponent - fraction_len as i32;

    // b + h = (2*mantissa + 1) * 2^(raw_exp - 1)
    // Build bignum for b + h numerator: bh_num = 2*mantissa + 1
    let bh_mantissa = 2 * mantissa + 1;
    let mut bh = Bigint::new();
    #[cfg(fast_arithmetic = "64")]
    {
        bh.data.push(bh_mantissa as Limb);
    }
    #[cfg(not(fast_arithmetic = "64"))]
    {
        bh.data.push(bh_mantissa as u32 as Limb);
        if bh_mantissa > u32::MAX as u64 {
            bh.data.push((bh_mantissa >> 32) as Limb);
        }
    }

    // bh_exp = raw_exp - 1 (power of 2)
    let bh_exp = raw_exp - 1;

    // We want to compare:
    //   decimal * 10^decimal_exp   vs   bh * 2^bh_exp
    //
    // Scale both to integers.
    // If decimal_exp >= 0 and bh_exp >= 0:
    //   decimal * 10^decimal_exp vs bh * 2^bh_exp
    //   multiply decimal by 10^decimal_exp, multiply bh by 2^bh_exp
    //
    // If decimal_exp < 0:
    //   multiply bh by 10^(-decimal_exp) to cancel the decimal's denominator
    //
    // If bh_exp < 0:
    //   multiply decimal by 2^(-bh_exp) to cancel bh's denominator

    // After scaling:
    // lhs = decimal * 10^max(decimal_exp,0) * 2^max(-bh_exp, 0)
    // rhs = bh * 2^max(bh_exp,0) * 10^max(-decimal_exp, 0)

    if decimal_exp >= 0 {
        bigint_mul_pow10(&mut decimal, decimal_exp as usize);
    } else {
        bigint_mul_pow10(&mut bh, (-decimal_exp) as usize);
    }

    if bh_exp >= 0 {
        bigint_mul_pow2(&mut bh, bh_exp as u32);
    } else {
        bigint_mul_pow2(&mut decimal, (-bh_exp) as u32);
    }

    // Now compare decimal vs bh
    decimal.compare(&bh)
}

/// Determine the correct rounding for a float given the slow-path big-integer comparison.
///
/// Returns true if we should round up (away from zero).
pub fn round_nearest_tie_even_bhcomp<F: Float>(
    b: ExtendedFloat,
    integer: &[u8],
    fraction: &[u8],
    exponent: i32,
) -> bool {
    let ord = bhcomp::<F>(b, integer, fraction, exponent);
    match ord {
        core::cmp::Ordering::Greater => true,
        core::cmp::Ordering::Less => false,
        core::cmp::Ordering::Equal => {
            // Exactly at midpoint: round to even
            // b.mant is even => round down, odd => round up
            (b.mant & 1) != 0
        }
    }
}

/// Slow path: use big-integer arithmetic to determine the correct float rounding.
///
/// Called when the moderate path fails (result is ambiguous within error bounds).
pub fn slow_path_bhcomp<F: Float>(
    b: ExtendedFloat,
    integer: &[u8],
    fraction: &[u8],
    exponent: i32,
) -> ExtendedFloat {
    let should_round_up = round_nearest_tie_even_bhcomp::<F>(b, integer, fraction, exponent);

    let mut result = b;
    if should_round_up {
        // Round up: increment mantissa
        result.mant += 1;
        // Check for mantissa overflow
        let mantissa_size = F::MANTISSA_SIZE as u32 + 1;
        if result.mant >= (1u64 << mantissa_size) {
            result.mant >>= 1;
            result.exp += 1;
        }
    }
    result
}
