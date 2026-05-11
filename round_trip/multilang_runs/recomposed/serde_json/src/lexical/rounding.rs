use super::float::ExtendedFloat;
use super::num::*;
use super::shift::*;

// Rounding modes for floating-point conversion.

/// Round an extended float to the nearest native float, breaking ties to even.
pub(crate) fn round_nearest_tie_even<F: Float>(fp: &mut ExtendedFloat, shift: i32)
where
    u64: AsPrimitive<F>,
{
    let (mut is_above, mut is_halfway) = round_nearest(fp, shift);

    // Tie-breaking: round to even (check least significant bit of result).
    if is_halfway {
        let is_odd = (fp.mant & 1) != 0;
        if !is_odd {
            is_above = false;
        }
    }

    if is_above {
        fp.mant += 1;
    }
}

/// Round an extended float downward (toward zero / floor).
pub(crate) fn round_downward<F: Float>(fp: &mut ExtendedFloat, shift: i32)
where
    u64: AsPrimitive<F>,
{
    // Simply shift without rounding up.
    let shift = shift as u32;
    if shift < 64 {
        fp.mant >>= shift;
    } else {
        fp.mant = 0;
    }
    fp.exp += shift as i32;
}

/// Determine if the bits to be shifted off are above the halfway point,
/// at the halfway point, or below, returning (is_above, is_halfway).
pub(crate) fn round_nearest(fp: &mut ExtendedFloat, shift: i32) -> (bool, bool) {
    // Mask of bits being shifted off.
    let mask: u64 = if shift == 64 {
        u64::MAX
    } else if shift > 64 || shift < 0 {
        0
    } else {
        (1u64 << shift) - 1
    };

    // The halfway bit is the highest bit being shifted off.
    let halfway_bit: u64 = if shift == 0 || shift > 64 {
        0
    } else {
        1u64 << (shift - 1)
    };

    let truncated = fp.mant & mask;
    let is_above = truncated > halfway_bit;
    let is_halfway = truncated == halfway_bit;

    // Perform the shift.
    let shift = shift as u32;
    if shift < 64 {
        fp.mant >>= shift;
    } else {
        fp.mant = 0;
    }
    fp.exp += shift as i32;

    (is_above, is_halfway)
}

/// Shift the mantissa to the native float representation and check for overflow.
pub(crate) fn shift_to_native<F: Float>(fp: &mut ExtendedFloat) {
    let shift = -fp.exp - F::MANTISSA_SIZE;
    if shift > 0 {
        shr(fp, shift as u32);
    }
}

/// Round an extended float to a native float type, with the given rounding algorithm.
pub(crate) fn round_to_native<F: Float, Algorithm>(fp: &mut ExtendedFloat, algorithm: Algorithm)
where
    Algorithm: Fn(&mut ExtendedFloat, i32),
    u64: AsPrimitive<F>,
{
    // Calculate the shift required to bring the mantissa into the right range.
    // We need to shift the mantissa so the implicit bit is in the right place.
    let mantissa_size = F::MANTISSA_SIZE as i32;

    // Normalize the exponent.
    // fp.exp is the binary exponent such that value = fp.mant * 2^fp.exp.
    // We need fp.mant to have exactly (mantissa_size + 1) significant bits
    // after rounding (the +1 is for the implicit leading 1 bit).
    // Currently fp.mant has 64 significant bits (after normalize).
    // We need to shift right by (64 - mantissa_size - 1).
    let shift = 64 - mantissa_size - 1;

    if shift > 0 {
        algorithm(fp, shift);
    } else if shift < 0 {
        shl(fp, (-shift) as u32);
    }
}

/// Tie-breaking round to even for use as a round_to_native algorithm callback.
pub(crate) fn tie_even_round(fp: &mut ExtendedFloat, shift: i32) {
    let (is_above, is_halfway) = round_nearest(fp, shift);
    let round_up = if is_halfway {
        // round to even
        (fp.mant & 1) != 0
    } else {
        is_above
    };
    if round_up {
        fp.mant += 1;
    }
}

/// Downward (truncating) round for use as a round_to_native algorithm callback.
pub(crate) fn downward_round(fp: &mut ExtendedFloat, shift: i32) {
    let shift = shift as u32;
    if shift < 64 {
        fp.mant >>= shift;
    } else {
        fp.mant = 0;
    }
    fp.exp += shift as i32;
}
