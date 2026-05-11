use super::bhcomp::*;
use super::cached::*;
use super::errors::*;
use super::float::ExtendedFloat;
use super::num::*;
use super::small_powers::*;

// Fast path: if mantissa and exponent fit within exact representation bounds,
// compute directly.
pub(crate) fn fast_path<F: Float>(mantissa: u64, exponent: i32) -> Option<F> {
    let (min_exp, max_exp) = F::exponent_limit();
    let mantissa_limit = F::mantissa_limit();

    if mantissa >> mantissa_limit != 0 {
        // Mantissa has too many significant bits
        return None;
    }

    if exponent == 0 {
        return Some(F::from_u64(mantissa));
    } else if exponent >= min_exp && exponent <= max_exp {
        let f = F::from_u64(mantissa);
        if exponent > 0 {
            Some(f.pow10(exponent))
        } else {
            // Negative exponent: divide by power of 10
            let p = F::from_u64(SMALL_INT_POWERS[(-exponent) as usize]);
            Some(f / p)
        }
    } else {
        None
    }
}

// Moderate path: use extended-precision float with cached powers.
pub(crate) fn moderate_path<F: Float>(
    mantissa: u64,
    exponent: i32,
    truncated: bool,
) -> ExtendedFloat {
    let mut fp = ExtendedFloat {
        mant: mantissa,
        exp: 0,
    };
    fp.normalize();

    // Get the cached power for this exponent
    let (cached, k) = cached_float(exponent);

    // Multiply fp by the cached power
    fp = fp.mul(&cached);

    // Normalize the result
    fp.normalize();

    // Check if the result is accurate
    if !truncated {
        // The result may be accurate; check error bounds
        let error = if is_halfway(mantissa) { 1 } else { 0 };
        let _ = error;
    }

    fp.exp += k;
    fp
}

/// Determine if the value is halfway between two floats.
fn is_halfway(mantissa: u64) -> bool {
    // Check if the mantissa has the form X...X1000...0
    mantissa != 0 && (mantissa & (mantissa - 1)) == 0
}

/// Parse a float using the fast path, returning None if not possible.
pub(crate) fn parse_float<F: Float>(mantissa: u64, exponent: i32, truncated: bool) -> (F, bool) {
    // Try the fast path first
    if !truncated {
        if let Some(f) = fast_path::<F>(mantissa, exponent) {
            return (f, true);
        }
    }

    // Use moderate path
    let fp = moderate_path::<F>(mantissa, exponent, truncated);

    // Check if the moderate path result is accurate
    let halfway = is_halfway_point::<F>(&fp);
    if truncated || halfway {
        // Need slow path (bhcomp)
        (F::from_bits(F::INFINITY_BITS), false)
    } else {
        (fp.into_float::<F>(), true)
    }
}

fn is_halfway_point<F: Float>(fp: &ExtendedFloat) -> bool {
    // The result is at a halfway point if the lower bits are exactly 0.5 ULP
    let shift = 63i32.saturating_sub(F::MANTISSA_SIZE as i32);
    if shift <= 0 {
        return false;
    }
    let mask = (1u64 << shift) - 1;
    let halfway_bit = 1u64 << (shift - 1);
    (fp.mant & mask) == halfway_bit
}

/// Full parsing with slow path fallback.
pub(crate) fn parse_float_complete<F: Float>(
    integer: &[u8],
    fraction: &[u8],
    exponent: i32,
    mantissa: u64,
    truncated: bool,
) -> F {
    // Try fast path
    if !truncated {
        if let Some(f) = fast_path::<F>(mantissa, exponent) {
            return f;
        }
    }

    // Try moderate path
    let mut fp = moderate_path::<F>(mantissa, exponent, truncated);

    // Normalize and check accuracy
    let bits = fp.mant;
    let ulp_error = calculate_error::<F>(mantissa, exponent, truncated);

    // Check if we're within half an ULP
    let float_size = core::mem::size_of::<F>() * 8;
    let shift = if float_size == 32 { 40 } else { 11 };

    let halfway = bits & ((1u64 << shift) - 1) == (1u64 << (shift - 1));

    if ulp_error == 0 && !halfway && !truncated {
        fp.into_float::<F>()
    } else {
        // Use slow path (bhcomp)
        bhcomp(fp, integer, fraction, exponent)
    }
}
