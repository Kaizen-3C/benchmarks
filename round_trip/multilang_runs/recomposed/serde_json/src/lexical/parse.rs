use super::algorithm::*;
use super::bhcomp::*;
use super::digit::*;
use super::exponent::*;
use super::num::*;

/// Parse a float from a concise representation: mantissa × 10^mant_exp.
///
/// Used when the entire decimal representation fits in a u64 mantissa.
pub fn parse_concise_float<F: Float>(mantissa: u64, mant_exp: i32) -> F {
    // Try the fast path first.
    if let Some(f) = fast_path::<F>(mantissa, mant_exp) {
        return f;
    }
    // Fall back to moderate/slow path.
    moderate_path::<F>(mantissa, mant_exp, false)
}

/// Parse a float from separate integer-part bytes, fraction-part bytes, and an exponent.
///
/// Trailing zeros in the fraction are stripped. Used when the mantissa overflowed u64 during parsing.
pub fn parse_truncated_float<F: Float>(integer: &[u8], fraction: &[u8], exponent: i32) -> F {
    // Strip trailing zeros from fraction.
    let fraction = trim_trailing_zeros(fraction);

    // Try to reconstruct a mantissa from the truncated representation.
    // We use the slow path (bhcomp) directly since the mantissa overflowed.
    let (mantissa, mantissa_exponent, truncated) =
        parse_mantissa_and_exponent(integer, fraction, exponent);

    if truncated {
        // Use the big-integer comparison path.
        bhcomp::<F>(mantissa, mantissa_exponent, integer, fraction, exponent)
    } else {
        // Try fast/moderate path with reconstructed mantissa.
        if let Some(f) = fast_path::<F>(mantissa, mantissa_exponent) {
            return f;
        }
        moderate_path::<F>(mantissa, mantissa_exponent, false)
    }
}

/// Strip trailing zeros from a byte slice.
fn trim_trailing_zeros(s: &[u8]) -> &[u8] {
    let end = s.iter().rposition(|&b| b != b'0').map(|i| i + 1).unwrap_or(0);
    &s[..end]
}

/// Parse mantissa and combined exponent from integer/fraction/exponent parts.
/// Returns (mantissa, mantissa_exponent, truncated).
fn parse_mantissa_and_exponent(
    integer: &[u8],
    fraction: &[u8],
    exponent: i32,
) -> (u64, i32, bool) {
    let mut mantissa: u64 = 0;
    let mut truncated = false;
    let mut digits_processed: i32 = 0;

    // Process integer digits.
    for &b in integer {
        let digit = to_digit(b) as u64;
        if digits_processed < F64_MAX_DIGITS {
            if let Some(m) = mantissa.checked_mul(10).and_then(|m| m.checked_add(digit)) {
                mantissa = m;
                digits_processed += 1;
            } else {
                truncated = true;
                break;
            }
        } else {
            truncated = true;
            break;
        }
    }

    // How many integer digits were non-leading-zero (count all for exponent calc).
    let int_len = integer.len() as i32;
    let frac_len = fraction.len() as i32;

    if !truncated {
        // Process fraction digits.
        for &b in fraction {
            let digit = to_digit(b) as u64;
            if digits_processed < F64_MAX_DIGITS {
                if let Some(m) = mantissa.checked_mul(10).and_then(|m| m.checked_add(digit)) {
                    mantissa = m;
                    digits_processed += 1;
                } else {
                    truncated = true;
                    break;
                }
            } else {
                truncated = true;
                break;
            }
        }
    }

    // The mantissa exponent: we consumed (digits_processed) digits total,
    // of which int_len are before the decimal point (if not truncated mid-integer).
    // Adjust: mantissa * 10^(mantissa_exponent) = original value.
    // original = integer.fraction * 10^exponent
    // mantissa = integer||fraction (first digits_processed digits)
    // We need: mantissa * 10^adj = original
    // adj = exponent - frac_len (fraction digits shift decimal left)
    let frac_consumed = if truncated && digits_processed <= int_len {
        0
    } else if truncated {
        digits_processed - int_len
    } else {
        frac_len
    };

    let mantissa_exponent = exponent - frac_consumed;

    (mantissa, mantissa_exponent, truncated)
}

// Maximum number of significant digits for f64.
const F64_MAX_DIGITS: i32 = 19;
