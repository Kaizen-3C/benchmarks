use super::cached_float80;
use super::float::ExtendedFloat;

/// A array of cached extended-precision floats.
pub(crate) type ExtendedFloatArray = &'static [ExtendedFloat];

/// Cached powers structure for the moderate path algorithm.
pub(crate) struct ModeratePathPowers {
    /// Pre-computed small powers of 10.
    pub small: ExtendedFloatArray,
    /// Pre-computed large powers of 10.
    pub large: ExtendedFloatArray,
    /// Step between large powers (how many small powers fit in one large power step).
    pub step: i32,
    /// Exponent bias for the large powers table.
    pub bias: i32,
    /// Exponent for the smallest large power.
    pub large_exponent_min: i32,
    /// Exponent step between consecutive large powers.
    pub large_exponent_step: i32,
}

/// Get the pre-computed powers for base-10 extended floats (float80).
pub(crate) fn get_powers() -> &'static ModeratePathPowers {
    cached_float80::get_powers()
}

/// Get a cached extended-precision float for a given power of 10.
///
/// Returns `(value, exponent)` where `value` is the cached `ExtendedFloat`
/// corresponding to `10^exponent` as closely as possible.
///
/// This is used by the moderate path algorithm to quickly compute approximate
/// floating-point values.
pub(crate) fn cached_pow10(exp: i32) -> (ExtendedFloat, i32) {
    let powers = get_powers();
    // Determine the index into the large powers table.
    // The large table covers exponents from `large_exponent_min` in steps of `large_exponent_step`.
    let step = powers.large_exponent_step;
    let min_exp = powers.large_exponent_min;

    // Compute which large power to use.
    // We need to find an index such that large_powers[index] is close to 10^exp.
    let large_len = powers.large.len() as i32;

    // Clamp the index
    let idx = ((exp - min_exp) / step).max(0).min(large_len - 1) as usize;
    let large_pow = &powers.large[idx];
    let large_exp = min_exp + (idx as i32) * step;

    // The actual decimal exponent represented by this cached power.
    let cached_exp = large_exp;

    (*large_pow, cached_exp)
}
