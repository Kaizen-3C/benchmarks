//! Mathematical operations for big integers (limb arithmetic).

use super::large_powers;
use super::num::*;
use super::small_powers::*;

// Re-export Limb and Wide types based on target architecture
#[cfg(fast_arithmetic = "64")]
pub type Limb = u64;

#[cfg(fast_arithmetic = "64")]
pub type Wide = u128;

#[cfg(fast_arithmetic = "32")]
pub type Limb = u32;

#[cfg(fast_arithmetic = "32")]
pub type Wide = u64;

// Fallback for when neither cfg is set (e.g., during doc builds)
#[cfg(not(any(fast_arithmetic = "64", fast_arithmetic = "32")))]
pub type Limb = u32;

#[cfg(not(any(fast_arithmetic = "64", fast_arithmetic = "32")))]
pub type Wide = u64;

/// Number of bits in a limb.
pub const LIMB_BITS: usize = core::mem::size_of::<Limb>() * 8;

/// Trait for operations on a vector of limbs (little-endian, least significant first).
pub trait Math: Sized {
    /// Get the underlying data slice.
    fn data(&self) -> &[Limb];

    /// Get the underlying data as mutable.
    fn data_mut(&mut self) -> &mut Vec<Limb>;

    /// Check if the value is empty (zero).
    fn is_empty(&self) -> bool {
        self.data().is_empty()
    }

    /// Get the length in limbs.
    fn len(&self) -> usize {
        self.data().len()
    }

    /// Check if the value is zero.
    fn is_zero(&self) -> bool {
        self.data().iter().all(|&x| x == 0)
    }

    /// Get the number of leading zero bits.
    fn leading_zeros(&self) -> u32 {
        match self.data().last() {
            Some(&v) => v.leading_zeros(),
            None => 0,
        }
    }

    /// Get the bit length.
    fn bit_length(&self) -> u32 {
        let len = self.len();
        if len == 0 {
            return 0;
        }
        let last = self.data()[len - 1];
        ((len as u32) - 1) * LIMB_BITS as u32 + (LIMB_BITS as u32 - last.leading_zeros())
    }

    /// Multiply by a small (single-limb) value.
    fn imul_small(&mut self, y: Limb) {
        let mut carry: Wide = 0;
        for x in self.data_mut().iter_mut() {
            let result = (*x as Wide) * (y as Wide) + carry;
            *x = result as Limb;
            carry = result >> LIMB_BITS;
        }
        if carry != 0 {
            self.data_mut().push(carry as Limb);
        }
    }

    /// Add a small (single-limb) value.
    fn iadd_small(&mut self, y: Limb) {
        let mut carry = y;
        for x in self.data_mut().iter_mut() {
            let (result, overflow) = x.overflowing_add(carry);
            *x = result;
            if overflow {
                carry = 1;
            } else {
                carry = 0;
                break;
            }
        }
        if carry != 0 {
            self.data_mut().push(carry);
        }
    }

    /// Multiply by a power of two (shift left by bits).
    fn ishl_bits(&mut self, n: usize) {
        if n == 0 || self.is_empty() {
            return;
        }
        debug_assert!(n < LIMB_BITS);
        let rshift = LIMB_BITS - n;
        let mut carry: Limb = 0;
        for x in self.data_mut().iter_mut() {
            let new_carry = *x >> rshift;
            *x = (*x << n) | carry;
            carry = new_carry;
        }
        if carry != 0 {
            self.data_mut().push(carry);
        }
    }

    /// Shift left by whole limbs.
    fn ishl_limbs(&mut self, n: usize) {
        if n == 0 || self.is_empty() {
            return;
        }
        let len = self.data().len();
        self.data_mut().resize(len + n, 0);
        // Move elements up
        let data = self.data_mut();
        for i in (0..len).rev() {
            data[i + n] = data[i];
        }
        for i in 0..n {
            data[i] = 0;
        }
    }

    /// Shift left by n bits.
    fn ishl(&mut self, n: usize) {
        let limbs = n / LIMB_BITS;
        let bits = n % LIMB_BITS;
        if limbs != 0 {
            self.ishl_limbs(limbs);
        }
        if bits != 0 {
            self.ishl_bits(bits);
        }
    }

    /// Multiply in-place by a big integer (result stored in self).
    fn imul_large(&mut self, y: &[Limb]) {
        if y.is_empty() || self.is_empty() {
            self.data_mut().clear();
            return;
        }
        let x_len = self.len();
        let y_len = y.len();
        let result_len = x_len + y_len;
        let mut result = vec![0 as Limb; result_len];

        for (i, &xi) in self.data().iter().enumerate() {
            let mut carry: Wide = 0;
            for (j, &yj) in y.iter().enumerate() {
                let idx = i + j;
                let cur = result[idx] as Wide + (xi as Wide) * (yj as Wide) + carry;
                result[idx] = cur as Limb;
                carry = cur >> LIMB_BITS;
            }
            if carry != 0 {
                let idx = i + y_len;
                let cur = result[idx] as Wide + carry;
                result[idx] = cur as Limb;
                // carry from here should be zero by construction
            }
        }

        // Remove trailing zeros
        while result.last() == Some(&0) {
            result.pop();
        }

        *self.data_mut() = result;
    }

    /// Add a big integer in place.
    fn iadd_large(&mut self, y: &[Limb]) {
        if y.is_empty() {
            return;
        }
        if self.data().len() < y.len() {
            self.data_mut().resize(y.len(), 0);
        }
        let mut carry: bool = false;
        let data = self.data_mut();
        for (i, &yi) in y.iter().enumerate() {
            let (r1, o1) = data[i].overflowing_add(yi);
            let (r2, o2) = r1.overflowing_add(carry as Limb);
            data[i] = r2;
            carry = o1 || o2;
        }
        let mut i = y.len();
        while carry {
            if i < data.len() {
                let (r, o) = data[i].overflowing_add(1);
                data[i] = r;
                carry = o;
            } else {
                data.push(1);
                carry = false;
            }
            i += 1;
        }
    }

    /// Compare self to y, returning Ordering.
    fn compare(&self, y: &[Limb]) -> core::cmp::Ordering {
        let xlen = self.len();
        let ylen = y.len();
        if xlen != ylen {
            return xlen.cmp(&ylen);
        }
        for (&xi, &yi) in self.data().iter().zip(y.iter()).rev() {
            match xi.cmp(&yi) {
                core::cmp::Ordering::Equal => continue,
                other => return other,
            }
        }
        core::cmp::Ordering::Equal
    }

    /// Karatsuba multiplication helper.
    fn imul_karatsuba(&mut self, y: &[Limb]) {
        // Use simple long multiplication for small sizes
        let x_len = self.len();
        let y_len = y.len();
        // Karatsuba threshold
        if x_len < 32 || y_len < 32 {
            self.imul_large(y);
            return;
        }

        let m = x_len.min(y_len) / 2;

        let x_data = self.data().to_vec();
        let (x_lo, x_hi) = x_data.split_at(m.min(x_data.len()));
        let (y_lo, y_hi) = y.split_at(m.min(y.len()));

        // z0 = x_lo * y_lo
        let mut z0 = x_lo.to_vec();
        imul_large_vec(&mut z0, y_lo);

        // z2 = x_hi * y_hi
        let mut z2 = x_hi.to_vec();
        imul_large_vec(&mut z2, y_hi);

        // z1 = (x_lo + x_hi) * (y_lo + y_hi) - z0 - z2
        let mut x_sum = x_lo.to_vec();
        iadd_large_vec(&mut x_sum, x_hi);
        let mut y_sum = y_lo.to_vec();
        iadd_large_vec(&mut y_sum, y_hi);
        let mut z1 = x_sum;
        imul_large_vec(&mut z1, &y_sum);

        // z1 = z1 - z0 - z2
        isub_large_vec(&mut z1, &z0);
        isub_large_vec(&mut z1, &z2);

        // result = z0 + z1 * B^m + z2 * B^(2m)
        let result_len = x_len + y_len;
        let mut result = vec![0 as Limb; result_len];

        // Add z0
        for (i, &v) in z0.iter().enumerate() {
            let cur = result[i] as Wide + v as Wide;
            result[i] = cur as Limb;
            let carry = (cur >> LIMB_BITS) as Limb;
            if carry != 0 && i + 1 < result_len {
                result[i + 1] += carry;
            }
        }

        // Add z1 * B^m
        let mut carry: Wide = 0;
        for (j, &v) in z1.iter().enumerate() {
            let i = j + m;
            if i < result_len {
                let cur = result[i] as Wide + v as Wide + carry;
                result[i] = cur as Limb;
                carry = cur >> LIMB_BITS;
            }
        }
        let mut i = m + z1.len();
        while carry != 0 && i < result_len {
            let cur = result[i] as Wide + carry;
            result[i] = cur as Limb;
            carry = cur >> LIMB_BITS;
            i += 1;
        }

        // Add z2 * B^(2m)
        carry = 0;
        for (j, &v) in z2.iter().enumerate() {
            let i = j + 2 * m;
            if i < result_len {
                let cur = result[i] as Wide + v as Wide + carry;
                result[i] = cur as Limb;
                carry = cur >> LIMB_BITS;
            }
        }
        let mut i = 2 * m + z2.len();
        while carry != 0 && i < result_len {
            let cur = result[i] as Wide + carry;
            result[i] = cur as Limb;
            carry = cur >> LIMB_BITS;
            i += 1;
        }

        while result.last() == Some(&0) {
            result.pop();
        }

        *self.data_mut() = result;
    }

    /// Multiply by 10^n using precomputed powers.
    fn imul_pow10(&mut self, n: u32) {
        // Use small powers table for small n
        let small_powers = get_small_powers_of_10();
        let large_powers_table = large_powers::get_large_powers();

        if n == 0 {
            return;
        }

        // Split into small and large power components
        let small_step = small_powers.len() as u32 - 1;
        let large_step = large_powers_table.step;

        // Apply large powers first
        let mut remaining = n;
        let mut large_idx = 0usize;
        let large_count = remaining / large_step;
        remaining %= large_step;

        for _ in 0..large_count {
            if large_idx < large_powers_table.data.len() {
                let power = large_powers_table.data[large_idx];
                self.imul_large(power);
                large_idx += 1;
            }
        }

        // Apply small powers
        while remaining >= small_step {
            let p = small_powers[small_step as usize];
            self.imul_small(p);
            remaining -= small_step;
        }
        if remaining > 0 {
            let p = small_powers[remaining as usize];
            self.imul_small(p);
        }
    }

    /// Multiply by 2^n.
    fn imul_pow2(&mut self, n: usize) {
        self.ishl(n);
    }

    /// Normalize by removing trailing zeros.
    fn normalize(&mut self) {
        while self.data_mut().last() == Some(&0) {
            self.data_mut().pop();
        }
    }
}

// Helper free functions for karatsuba (work on Vec<Limb> directly)

fn imul_large_vec(x: &mut Vec<Limb>, y: &[Limb]) {
    if y.is_empty() || x.is_empty() {
        x.clear();
        return;
    }
    let x_len = x.len();
    let y_len = y.len();
    let result_len = x_len + y_len;
    let mut result = vec![0 as Limb; result_len];

    for (i, &xi) in x.iter().enumerate() {
        let mut carry: Wide = 0;
        for (j, &yj) in y.iter().enumerate() {
            let idx = i + j;
            let cur = result[idx] as Wide + (xi as Wide) * (yj as Wide) + carry;
            result[idx] = cur as Limb;
            carry = cur >> LIMB_BITS;
        }
        if carry != 0 {
            let idx = i + y_len;
            if idx < result_len {
                result[idx] = result[idx].wrapping_add(carry as Limb);
            }
        }
    }

    while result.last() == Some(&0) {
        result.pop();
    }

    *x = result;
}

fn iadd_large_vec(x: &mut Vec<Limb>, y: &[Limb]) {
    if y.is_empty() {
        return;
    }
    if x.len() < y.len() {
        x.resize(y.len(), 0);
    }
    let mut carry = false;
    for (i, &yi) in y.iter().enumerate() {
        let (r1, o1) = x[i].overflowing_add(yi);
        let (r2, o2) = r1.overflowing_add(carry as Limb);
        x[i] = r2;
        carry = o1 || o2;
    }
    let mut i = y.len();
    while carry {
        if i < x.len() {
            let (r, o) = x[i].overflowing_add(1);
            x[i] = r;
            carry = o;
        } else {
            x.push(1);
            carry = false;
        }
        i += 1;
    }
}

fn isub_large_vec(x: &mut Vec<Limb>, y: &[Limb]) {
    // Subtract y from x in place (assumes x >= y)
    let mut borrow = false;
    for (i, &yi) in y.iter().enumerate() {
        if i < x.len() {
            let (r1, o1) = x[i].overflowing_sub(yi);
            let (r2, o2) = r1.overflowing_sub(borrow as Limb);
            x[i] = r2;
            borrow = o1 || o2;
        }
    }
    let mut i = y.len();
    while borrow {
        if i < x.len() {
            let (r, o) = x[i].overflowing_sub(1);
            x[i] = r;
            borrow = o;
        } else {
            break;
        }
        i += 1;
    }
    while x.last() == Some(&0) {
        x.pop();
    }
}

/// Get the small powers of 10 table.
fn get_small_powers_of_10() -> &'static [Limb] {
    #[cfg(any(fast_arithmetic = "64", not(any(fast_arithmetic = "64", fast_arithmetic = "32"))))]
    {
        &SMALL_POWERS_OF_10_64
    }
    #[cfg(fast_arithmetic = "32")]
    {
        &SMALL_POWERS_OF_10_32
    }
}

#[cfg(any(fast_arithmetic = "64", not(any(fast_arithmetic = "64", fast_arithmetic = "32"))))]
static SMALL_POWERS_OF_10_64: [u64; 20] = [
    1,                    // 10^0
    10,                   // 10^1
    100,                  // 10^2
    1000,                 // 10^3
    10000,                // 10^4
    100000,               // 10^5
    1000000,              // 10^6
    10000000,             // 10^7
    100000000,            // 10^8
    1000000000,           // 10^9
    10000000000,          // 10^10
    100000000000,         // 10^11
    1000000000000,        // 10^12
    10000000000000,       // 10^13
    100000000000000,      // 10^14
    1000000000000000,     // 10^15
    10000000000000000,    // 10^16
    100000000000000000,   // 10^17
    1000000000000000000,  // 10^18
    10000000000000000000, // 10^19
];

#[cfg(fast_arithmetic = "32")]
static SMALL_POWERS_OF_10_32: [u32; 10] = [
    1,          // 10^0
    10,         // 10^1
    100,        // 10^2
    1000,       // 10^3
    10000,      // 10^4
    100000,     // 10^5
    1000000,    // 10^6
    10000000,   // 10^7
    100000000,  // 10^8
    1000000000, // 10^9
];

/// Struct for large power table access.
pub struct LargePowerTable {
    pub data: &'static [&'static [Limb]],
    pub step: u32,
}

/// Multiply two big-integer slices and return the result.
pub fn mul_slices(x: &[Limb], y: &[Limb]) -> Vec<Limb> {
    if x.is_empty() || y.is_empty() {
        return Vec::new();
    }
    let x_len = x.len();
    let y_len = y.len();
    let result_len = x_len + y_len;
    let mut result = vec![0 as Limb; result_len];

    for (i, &xi) in x.iter().enumerate() {
        let mut carry: Wide = 0;
        for (j, &yj) in y.iter().enumerate() {
            let idx = i + j;
            let cur = result[idx] as Wide + (xi as Wide) * (yj as Wide) + carry;
            result[idx] = cur as Limb;
            carry = cur >> LIMB_BITS;
        }
        if carry != 0 {
            let idx = i + y_len;
            if idx < result_len {
                let cur = result[idx] as Wide + carry;
                result[idx] = cur as Limb;
            }
        }
    }

    while result.last() == Some(&0) {
        result.pop();
    }

    result
}

/// Shift right by n bits (in place).
pub fn ishr_bits(data: &mut Vec<Limb>, n: usize) {
    if n == 0 || data.is_empty() {
        return;
    }
    let limb_shift = n / LIMB_BITS;
    let bit_shift = n % LIMB_BITS;

    if limb_shift >= data.len() {
        data.clear();
        return;
    }

    if limb_shift > 0 {
        data.drain(0..limb_shift);
    }

    if bit_shift > 0 {
        let lshift = LIMB_BITS - bit_shift;
        let mut carry: Limb = 0;
        for x in data.iter_mut().rev() {
            let new_carry = *x << lshift;
            *x = (*x >> bit_shift) | carry;
            carry = new_carry;
        }
        while data.last() == Some(&0) {
            data.pop();
        }
    }
}

/// Compute the hi limb after multiplication to check rounding.
pub fn hi64(data: &[Limb]) -> (u64, bool) {
    if data.is_empty() {
        return (0, false);
    }

    #[cfg(any(fast_arithmetic = "64", not(any(fast_arithmetic = "64", fast_arithmetic = "32"))))]
    {
        let len = data.len();
        if len == 1 {
            let v = data[len - 1];
            let shift = v.leading_zeros() as usize;
            if shift == 0 {
                (v, false)
            } else {
                (v << shift, false)
            }
        } else {
            let hi = data[len - 1];
            let lo = data[len - 2];
            let shift = hi.leading_zeros() as usize;
            if shift == 0 {
                (hi, lo != 0)
            } else {
                let v = (hi << shift) | (lo >> (64 - shift));
                let truncated = (lo << shift) != 0
                    || data[..len - 2].iter().any(|&x| x != 0);
                (v, truncated)
            }
        }
    }

    #[cfg(fast_arithmetic = "32")]
    {
        let len = data.len();
        if len == 1 {
            let v = data[len - 1] as u64;
            let shift = v.leading_zeros() as usize;
            (v << shift, false)
        } else if len == 2 {
            let hi = data[len - 1] as u64;
            let lo = data[len - 2] as u64;
            let v = (hi << 32) | lo;
            let shift = v.leading_zeros() as usize;
            if shift == 0 {
                (v, false)
            } else {
                (v << shift, false)
            }
        } else {
            let hi = data[len - 1] as u64;
            let lo = data[len - 2] as u64;
            let v = (hi << 32) | lo;
            let shift = v.leading_zeros() as usize;
            if shift == 0 {
                (v, data[..len - 2].iter().any(|&x| x != 0))
            } else {
                let extra = data[len - 3] as u64;
                let v2 = (v << shift) | (extra >> (64 - shift));
                let truncated = (extra << shift) != 0
                    || data[..len - 3].iter().any(|&x| x != 0);
                (v2, truncated)
            }
        }
    }
}
