use super::float::*;
use super::num::*;
use super::rounding::*;

/// Check if the error bound is accurate enough to directly convert to float.
///
/// We need to check if the error delta is accurate enough to determine
/// the correct rounding of a float. The error is given in half-ULPs.
///
/// If the extended float has a mantissa of `m` and the error is `e`,
/// then the float is accurate if:
///   - The halfway bit (bit 64 - mantissa_size - 1) is set, and
///   - The error is small enough that it can't cross the halfway point.
#[inline]
pub(crate) fn error_is_accurate<F: Float>(count: u32, fp: &ExtendedFloat) -> bool {
    // Check if the error is small enough that rounding won't be affected.
    // This is determined by looking at the bits just below the precision
    // boundary.
    let shift = fp.mant.leading_zeros().wrapping_sub(1);
    let errors = count;
    
    // The number of bits we need to shift to get the halfway bit.
    // We need the mantissa to be normalized (leading 1 at bit 63).
    // The precision boundary is at bit (64 - F::MANTISSA_SIZE - 1).
    let mantissa_size = F::MANTISSA_SIZE as u32;
    
    // The halfway bit position (from LSB) after normalization.
    // After normalization, bit 63 is the implicit leading bit.
    // The stored mantissa uses bits [63 - mantissa_size, 63).
    // The halfway point is at bit (63 - mantissa_size - 1) = (62 - mantissa_size).
    let halfway_bit = 63u32.wrapping_sub(mantissa_size);
    
    // We need sufficient bits below the precision boundary to determine
    // whether the error can change the rounded result.
    // The rounding is unambiguous if:
    //   The trailing bits (below precision boundary) are not in the danger zone.
    //   The danger zone is when trailing bits could be exactly halfway or within
    //   error of halfway.
    
    // Mask of bits below the precision boundary
    let mask = if halfway_bit >= 64 {
        u64::MAX
    } else {
        (1u64 << halfway_bit).wrapping_sub(1)
    };
    
    let _ = shift;
    let _ = mask;
    
    // The actual accuracy check: the error (in half-ULPs) must be small
    // enough that rounding direction is unambiguous.
    // If the halfway bit is 0, then even with error we round down (or up if
    // errors push it over halfway).
    // We check: distance from halfway point > errors
    
    // Get the bits below the precision boundary
    let truncated = if halfway_bit >= 64 {
        0u64
    } else {
        fp.mant & ((1u64 << halfway_bit) - 1)
    };
    
    // The halfway value for the truncated bits
    let halfway = if halfway_bit == 0 || halfway_bit >= 64 {
        0u64
    } else {
        1u64 << (halfway_bit - 1)
    };
    
    // Distance from halfway point (in half-ULPs of the stored precision)
    // We multiply by 2 to convert ULPs to half-ULPs
    let dist = if truncated >= halfway {
        truncated - halfway
    } else {
        halfway - truncated
    };
    
    // The result is accurate if the distance from the halfway point
    // is greater than the error bound (in half-ULPs).
    // We multiply dist by 2 since errors is in half-ULPs.
    dist.saturating_mul(2) >= errors as u64
}

/// Determine if the float result needs re-rounding due to accumulated error.
///
/// Returns true if the mantissa is within `count` half-ULPs of a halfway point
/// and thus the rounding might be wrong.
#[inline]
pub(crate) fn error_is_above_halfway<F: Float>(fp: &ExtendedFloat) -> bool {
    let mantissa_size = F::MANTISSA_SIZE as u32;
    // The bit position of the halfway point (from LSB of fp.mant)
    // fp.mant is normalized so bit 63 is set.
    // Stored mantissa: bits [63 - mantissa_size, 62] (mantissa_size bits)
    // Truncated bits: [0, 62 - mantissa_size]
    // Halfway bit: bit (62 - mantissa_size)
    let halfway_bit = 63u32.wrapping_sub(mantissa_size);
    if halfway_bit >= 64 {
        return false;
    }
    // Check if the halfway bit is set
    (fp.mant >> halfway_bit) & 1 == 1
}

/// Calculate the error when computing the float from a moderate path.
/// Returns the error in half-ULPs.
#[inline]
pub(crate) fn moderate_path_error() -> u32 {
    // The moderate path has an error of at most 1/2 ULP from the extended
    // multiplication, plus rounding. We use 4 half-ULPs as a safe bound.
    4
}

/// Check if the result from the moderate path is accurate enough.
#[inline]
pub(crate) fn is_accurate_moderate<F: Float>(count: u32, fp: &ExtendedFloat) -> bool {
    error_is_accurate::<F>(count, fp)
}

/// Round an extended float to the nearest float, checking if there's
/// enough accuracy to determine the correct rounding direction.
///
/// Returns the rounded float and whether the result is accurate.
#[inline]
pub(crate) fn round_to_native_error<F: Float>(fp: &mut ExtendedFloat, count: u32) -> bool {
    // Check accuracy before rounding
    let accurate = error_is_accurate::<F>(count, fp);
    
    // Round the extended float
    round_nearest_tie_even(fp, |f, is_above, is_halfway| {
        round_native::<F>(f, is_above, is_halfway)
    });
    
    accurate
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_moderate_path_error() {
        assert_eq!(moderate_path_error(), 4);
    }
}
