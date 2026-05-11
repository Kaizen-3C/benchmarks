//! Numeric trait definitions for the lexical float-parsing algorithm.

/// Trait for primitive numeric types used in the lexical algorithm.
pub trait AsPrimitive<T: Copy>: Copy {
    fn as_cast(self) -> T;
}

macro_rules! impl_as_primitive {
    ($from:ty => $($to:ty),+) => {
        $(
            impl AsPrimitive<$to> for $from {
                #[inline]
                fn as_cast(self) -> $to {
                    self as $to
                }
            }
        )+
    };
}

impl_as_primitive!(u8 => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(u16 => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(u32 => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(u64 => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(u128 => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(usize => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(i8 => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(i16 => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(i32 => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(i64 => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(i128 => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(isize => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(f32 => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);
impl_as_primitive!(f64 => u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize, f32, f64);

/// Trait for integer types used in the lexical algorithm.
pub trait Integer:
    Copy
    + Clone
    + core::fmt::Debug
    + core::ops::Add<Output = Self>
    + core::ops::Sub<Output = Self>
    + core::ops::Mul<Output = Self>
    + core::ops::Div<Output = Self>
    + core::ops::Rem<Output = Self>
    + core::ops::BitAnd<Output = Self>
    + core::ops::BitOr<Output = Self>
    + core::ops::BitXor<Output = Self>
    + core::ops::Shl<u32, Output = Self>
    + core::ops::Shr<u32, Output = Self>
    + core::ops::Not<Output = Self>
    + core::ops::AddAssign
    + core::ops::SubAssign
    + core::ops::MulAssign
    + core::ops::BitOrAssign
    + core::ops::BitAndAssign
    + core::ops::ShrAssign<u32>
    + core::ops::ShlAssign<u32>
    + PartialEq
    + Eq
    + PartialOrd
    + Ord
    + AsPrimitive<u8>
    + AsPrimitive<u32>
    + AsPrimitive<u64>
    + AsPrimitive<usize>
{
    const ZERO: Self;
    const ONE: Self;
    const MAX: Self;
    const BITS: usize;

    fn leading_zeros(self) -> u32;
    fn trailing_zeros(self) -> u32;
    fn count_ones(self) -> u32;
    fn wrapping_add(self, rhs: Self) -> Self;
    fn wrapping_mul(self, rhs: Self) -> Self;
    fn checked_add(self, rhs: Self) -> Option<Self>;
    fn checked_mul(self, rhs: Self) -> Option<Self>;
    fn overflowing_add(self, rhs: Self) -> (Self, bool);
    fn overflowing_mul(self, rhs: Self) -> (Self, bool);
    fn from_u32(n: u32) -> Self;
    fn from_u64(n: u64) -> Self;
    fn is_zero(self) -> bool {
        self == Self::ZERO
    }
}

macro_rules! impl_integer {
    ($($t:ty),+) => {
        $(
            impl Integer for $t {
                const ZERO: Self = 0;
                const ONE: Self = 1;
                const MAX: Self = <$t>::MAX;
                const BITS: usize = <$t>::BITS as usize;

                #[inline]
                fn leading_zeros(self) -> u32 { self.leading_zeros() }
                #[inline]
                fn trailing_zeros(self) -> u32 { self.trailing_zeros() }
                #[inline]
                fn count_ones(self) -> u32 { self.count_ones() }
                #[inline]
                fn wrapping_add(self, rhs: Self) -> Self { self.wrapping_add(rhs) }
                #[inline]
                fn wrapping_mul(self, rhs: Self) -> Self { self.wrapping_mul(rhs) }
                #[inline]
                fn checked_add(self, rhs: Self) -> Option<Self> { self.checked_add(rhs) }
                #[inline]
                fn checked_mul(self, rhs: Self) -> Option<Self> { self.checked_mul(rhs) }
                #[inline]
                fn overflowing_add(self, rhs: Self) -> (Self, bool) { self.overflowing_add(rhs) }
                #[inline]
                fn overflowing_mul(self, rhs: Self) -> (Self, bool) { self.overflowing_mul(rhs) }
                #[inline]
                fn from_u32(n: u32) -> Self { n as $t }
                #[inline]
                fn from_u64(n: u64) -> Self { n as $t }
            }
        )+
    };
}

impl_integer!(u8, u16, u32, u64, u128, usize, i8, i16, i32, i64, i128, isize);
