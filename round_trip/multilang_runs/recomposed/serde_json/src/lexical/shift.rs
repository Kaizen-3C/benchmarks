use super::float::ExtendedFloat;

/// Shift the ExtendedFloat left by `shift` bits.
#[inline]
pub(crate) fn shl(fp: &mut ExtendedFloat, shift: i32) {
    fp.mant <<= shift as u32;
    fp.exp -= shift;
}

/// Shift the ExtendedFloat right by `shift` bits.
#[inline]
pub(crate) fn shr(fp: &mut ExtendedFloat, shift: i32) {
    fp.mant >>= shift as u32;
    fp.exp += shift;
}

/// Shift the ExtendedFloat right by `shift` bits, rounding the result.
/// If the truncated bits are >= half, round up.
#[inline]
pub(crate) fn shr_round(fp: &mut ExtendedFloat, shift: i32) {
    if shift == 0 {
        return;
    }
    let mask = if shift == 64 {
        u64::MAX
    } else {
        (1u64 << shift) - 1
    };
    let halfway = 1u64 << (shift - 1);
    let truncated = fp.mant & mask;
    fp.mant >>= shift as u32;
    fp.exp += shift;
    if truncated >= halfway {
        fp.mant = fp.mant.saturating_add(1);
    }
}
