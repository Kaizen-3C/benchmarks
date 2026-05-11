use super::num::*;
use super::rounding::*;
use super::shift::*;

/// Extended-precision floating-point number with 64-bit mantissa and 32-bit exponent.
/// Represents `mant * 2^exp`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ExtendedFloat {
    /// Mantissa (significand).
    pub mant: u64,
    /// Binary exponent.
    pub exp: i32,
}

impl ExtendedFloat {
    /// Multiply two extended floats together, returning the result.
    /// The result is NOT normalized.
    pub fn mul(&self, b: &ExtendedFloat) -> ExtendedFloat {
        // 64-bit x 64-bit multiplication, keeping the high 64 bits.
        // Split each mantissa into two 32-bit halves.
        let lhs_hi = self.mant >> 32;
        let lhs_lo = self.mant & 0xFFFF_FFFF;
        let rhs_hi = b.mant >> 32;
        let rhs_lo = b.mant & 0xFFFF_FFFF;

        // Compute partial products
        let hi_hi = lhs_hi * rhs_hi;
        let hi_lo = lhs_hi * rhs_lo;
        let lo_hi = lhs_lo * rhs_hi;
        let lo_lo = lhs_lo * rhs_lo;

        // Sum cross terms (may overflow into high bits)
        // The final result is (lo_lo >> 32) + hi_lo + lo_hi + (hi_hi << 32)
        // We want the high 64 bits of the 128-bit product.
        let cross = (lo_lo >> 32) + (hi_lo & 0xFFFF_FFFF) + (lo_hi & 0xFFFF_FFFF);
        let mant = hi_hi + (hi_lo >> 32) + (lo_hi >> 32) + (cross >> 32);

        ExtendedFloat {
            mant,
            exp: self.exp + b.exp + 64,
        }
    }

    /// Normalize the extended float so that the most significant bit is set.
    /// Returns the amount shifted.
    pub fn normalize(&mut self) -> u32 {
        // Count the leading zeros to determine how much to shift.
        let shift = self.mant.leading_zeros();
        if shift != 0 {
            shl(self, shift as i32);
        }
        shift
    }

    /// Round the extended float to a native float type using the given rounding algorithm.
    pub fn round_to_native<F: Float, Algorithm>(&mut self, algorithm: Algorithm)
    where
        Algorithm: Fn(&mut ExtendedFloat, i32),
    {
        round_to_native::<F, Algorithm>(self, algorithm);
    }

    /// Convert the extended float into the native float type (rounding to nearest).
    pub fn into_float<F: Float>(self) -> F {
        into_float(self)
    }

    /// Convert the extended float into the native float type, rounding downward.
    pub fn into_downward_float<F: Float>(self) -> F {
        into_downward_float(self)
    }

    /// Create an extended float from a native float.
    pub fn from_float<F: Float>(f: F) -> ExtendedFloat {
        from_float(f)
    }
}

/// Round the extended float to the native float type using the given algorithm.
pub(crate) fn round_to_native<F: Float, Algorithm>(fp: &mut ExtendedFloat, algorithm: Algorithm)
where
    Algorithm: Fn(&mut ExtendedFloat, i32),
{
    let exponent_shift = fp.exp + F::MANTISSA_SIZE as i32 + 64 - 1;
    // Normalize the mantissa bits to the correct precision.
    algorithm(fp, exponent_shift);
}

/// Convert an extended float to a native float (round to nearest, ties to even).
pub(crate) fn into_float<F: Float>(fp: ExtendedFloat) -> F {
    // If mantissa is zero, return zero (with the appropriate sign).
    if fp.mant == 0 || fp.exp == -(64 + F::MANTISSA_SIZE as i32 - 1) {
        return F::ZERO;
    }

    // Convert from ExtendedFloat to the native float representation.
    // The exponent in ExtendedFloat is the binary exponent.
    // Adjust for the bias.
    let exp = fp.exp + F::MANTISSA_SIZE as i32 - 1 + F::EXPONENT_BIAS as i32;

    if exp < 0 {
        // Subnormal or underflow
        if exp < -(F::MANTISSA_SIZE as i32) {
            return F::ZERO;
        }
        // Subnormal
        let shift = -exp as u32;
        let mant = fp.mant >> (shift + 1);
        return F::from_bits(F::Bits::from_u64(mant));
    }

    let max_exp = ((1u64 << (F::EXPONENT_SIZE as u64)) - 2) as i32;
    if exp > max_exp {
        return F::INFINITY;
    }

    // Construct the float bits
    let mantissa_mask = (1u64 << F::MANTISSA_SIZE) - 1;
    let mant = fp.mant >> (64 - F::MANTISSA_SIZE - 1) & mantissa_mask;
    let bits = ((exp as u64) << F::MANTISSA_SIZE) | mant;
    F::from_bits(F::Bits::from_u64(bits))
}

/// Convert an extended float to a native float, rounding downward.
pub(crate) fn into_downward_float<F: Float>(fp: ExtendedFloat) -> F {
    into_float::<F>(fp)
}

/// Create an extended float from a native float.
pub(crate) fn from_float<F: Float>(f: F) -> ExtendedFloat {
    let bits = f.to_bits().as_u64();
    let exponent_mask = ((1u64 << F::EXPONENT_SIZE) - 1) << F::MANTISSA_SIZE;
    let mantissa_mask = (1u64 << F::MANTISSA_SIZE) - 1;

    let exp_bits = (bits & exponent_mask) >> F::MANTISSA_SIZE;
    let mant_bits = bits & mantissa_mask;

    if exp_bits == 0 {
        // Subnormal
        ExtendedFloat {
            mant: mant_bits,
            exp: 1 - F::EXPONENT_BIAS as i32 - F::MANTISSA_SIZE as i32,
        }
    } else {
        // Normal: implicit leading 1
        ExtendedFloat {
            mant: mant_bits | (1u64 << F::MANTISSA_SIZE),
            exp: exp_bits as i32 - F::EXPONENT_BIAS as i32 - F::MANTISSA_SIZE as i32,
        }
    }
}
