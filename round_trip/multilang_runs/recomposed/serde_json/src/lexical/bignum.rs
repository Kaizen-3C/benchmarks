use super::math::*;

/// A big integer type backed by a vector of limbs.
///
/// Used in the slow path (bhcomp) for exact decimal-to-float comparison.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Bigint {
    /// The limbs of the big integer, stored in little-endian order.
    pub data: Vec<Limb>,
}

impl Bigint {
    /// Create a new, empty (zero) Bigint.
    #[inline]
    pub fn new() -> Self {
        Bigint { data: Vec::new() }
    }

    /// Create a Bigint from a single limb value.
    #[inline]
    pub fn from_u64(value: u64) -> Self {
        let mut bigint = Bigint::new();
        bigint.data.push_u64(value);
        bigint
    }

    /// Create a Bigint from a u32 value.
    #[inline]
    pub fn from_u32(value: u32) -> Self {
        Self::from_u64(value as u64)
    }

    /// Return true if the value is zero.
    #[inline]
    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }

    /// Get the number of limbs.
    #[inline]
    pub fn len(&self) -> usize {
        self.data.len()
    }

    /// Compare this Bigint to another, returning an `Ordering`.
    pub fn compare(&self, other: &Bigint) -> core::cmp::Ordering {
        self.data.compare(&other.data)
    }

    /// Multiply the big integer by a small (limb-sized) power of 2.
    pub fn imul_pow2(&mut self, n: u32) {
        self.data.ishl_bits(n as usize);
    }

    /// Multiply the big integer by a power of 5.
    pub fn imul_pow5(&mut self, n: u32) {
        self.data.imul_pow5(n);
    }

    /// Multiply the big integer by 10^n.
    pub fn imul_pow10(&mut self, n: u32) {
        self.imul_pow5(n);
        self.imul_pow2(n);
    }

    /// Multiply in-place by a limb value.
    pub fn imul_small(&mut self, y: Limb) {
        self.data.imul_small(y);
    }

    /// Add a small (limb-sized) value in-place.
    pub fn iadd_small(&mut self, y: Limb) {
        self.data.iadd_small(y);
    }

    /// Shift left by n bits in-place.
    pub fn ishl(&mut self, n: usize) {
        self.data.ishl_bits(n);
    }

    /// Multiply two Bigints together, returning a new Bigint.
    pub fn mul(&self, other: &Bigint) -> Bigint {
        let mut result = Bigint::new();
        result.data = self.data.mul_large(&other.data);
        result
    }
}

/// Helper trait extension for Vec<Limb> to add u64 push convenience.
trait VecLimbExt {
    fn push_u64(&mut self, value: u64);
}

impl VecLimbExt for Vec<Limb> {
    #[inline]
    fn push_u64(&mut self, value: u64) {
        #[cfg(fast_arithmetic = "64")]
        {
            if value != 0 {
                self.push(value as Limb);
            }
        }
        #[cfg(fast_arithmetic = "32")]
        {
            let lo = value as u32;
            let hi = (value >> 32) as u32;
            if lo != 0 || hi != 0 {
                self.push(lo as Limb);
                if hi != 0 {
                    self.push(hi as Limb);
                }
            }
        }
    }
}
