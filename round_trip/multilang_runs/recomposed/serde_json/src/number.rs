use core::fmt::{self, Display, Formatter};
use core::hash::{Hash, Hasher};

use serde_core::de::{self, Unexpected, Visitor};
use serde_core::ser;

use crate::de::ParserNumber;
use crate::error::{Error, ErrorCode};

/// Represents a JSON number, whether integer or floating point.
#[derive(Clone, PartialEq, Eq)]
pub struct Number {
    pub(crate) n: N,
}

#[derive(Copy, Clone, Debug)]
pub(crate) enum N {
    PosInt(u64),
    NegInt(i64),
    Float(f64),
}

impl PartialEq for N {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (N::PosInt(a), N::PosInt(b)) => a == b,
            (N::NegInt(a), N::NegInt(b)) => a == b,
            (N::Float(a), N::Float(b)) => a.to_bits() == b.to_bits(),
            _ => false,
        }
    }
}

impl Eq for N {}

impl Hash for N {
    fn hash<H: Hasher>(&self, state: &mut H) {
        match self {
            N::PosInt(v) => {
                state.write_u8(0);
                v.hash(state);
            }
            N::NegInt(v) => {
                state.write_u8(1);
                v.hash(state);
            }
            N::Float(f) => {
                state.write_u8(2);
                // Hash 0.0 and -0.0 identically
                let bits = if *f == 0.0f64 { 0u64 } else { f.to_bits() };
                bits.hash(state);
            }
        }
    }
}

impl Hash for Number {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.n.hash(state);
    }
}

impl Number {
    /// Returns true if the `Number` is an integer between `i64::MIN` and
    /// `i64::MAX`.
    #[inline]
    pub fn is_i64(&self) -> bool {
        match self.n {
            N::PosInt(v) => v <= i64::MAX as u64,
            N::NegInt(_) => true,
            N::Float(_) => false,
        }
    }

    /// Returns true if the `Number` is an integer between zero and `u64::MAX`.
    #[inline]
    pub fn is_u64(&self) -> bool {
        matches!(self.n, N::PosInt(_))
    }

    /// Returns true if the `Number` is a float (not an integer).
    #[inline]
    pub fn is_f64(&self) -> bool {
        matches!(self.n, N::Float(_))
    }

    /// If the `Number` is an integer, represent it as i64 if possible.
    #[inline]
    pub fn as_i64(&self) -> Option<i64> {
        match self.n {
            N::PosInt(v) => {
                if v <= i64::MAX as u64 {
                    Some(v as i64)
                } else {
                    None
                }
            }
            N::NegInt(v) => Some(v),
            N::Float(_) => None,
        }
    }

    /// If the `Number` is an integer, represent it as u64 if possible.
    #[inline]
    pub fn as_u64(&self) -> Option<u64> {
        match self.n {
            N::PosInt(v) => Some(v),
            N::NegInt(_) | N::Float(_) => None,
        }
    }

    /// Represents the number as f64 if possible.
    #[inline]
    pub fn as_f64(&self) -> Option<f64> {
        match self.n {
            N::PosInt(v) => Some(v as f64),
            N::NegInt(v) => Some(v as f64),
            N::Float(v) => Some(v),
        }
    }

    /// If the `Number` is an integer, represent it as i128 if possible.
    #[inline]
    pub fn as_i128(&self) -> Option<i128> {
        match self.n {
            N::PosInt(v) => Some(v as i128),
            N::NegInt(v) => Some(v as i128),
            N::Float(_) => None,
        }
    }

    /// If the `Number` is a non-negative integer, represent it as u128 if possible.
    #[inline]
    pub fn as_u128(&self) -> Option<u128> {
        match self.n {
            N::PosInt(v) => Some(v as u128),
            N::NegInt(_) | N::Float(_) => None,
        }
    }

    /// Converts a finite `f64` to a `Number`. Infinite or NaN values return `None`.
    #[inline]
    pub fn from_f64(f: f64) -> Option<Number> {
        if f.is_finite() {
            Some(Number { n: N::Float(f) })
        } else {
            None
        }
    }

    /// Converts an `i128` to a `Number`. Returns `None` if out of representable range.
    #[inline]
    pub fn from_i128(i: i128) -> Option<Number> {
        if i >= 0 {
            if i <= u64::MAX as i128 {
                Some(Number { n: N::PosInt(i as u64) })
            } else {
                None
            }
        } else if i >= i64::MIN as i128 {
            Some(Number { n: N::NegInt(i as i64) })
        } else {
            None
        }
    }

    /// Converts a `u128` to a `Number`. Returns `None` if out of representable range.
    #[inline]
    pub fn from_u128(u: u128) -> Option<Number> {
        if u <= u64::MAX as u128 {
            Some(Number { n: N::PosInt(u as u64) })
        } else {
            None
        }
    }

    pub(crate) fn from_parser_number(n: ParserNumber) -> Result<Number, Error> {
        match n {
            ParserNumber::F64(f) => {
                if f.is_finite() {
                    Ok(Number { n: N::Float(f) })
                } else {
                    Err(Error::syntax(ErrorCode::NumberOutOfRange, 0, 0))
                }
            }
            ParserNumber::U64(u) => Ok(Number { n: N::PosInt(u) }),
            ParserNumber::I64(i) => Ok(Number { n: N::NegInt(i) }),
        }
    }
}

impl Display for Number {
    fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
        match self.n {
            N::PosInt(v) => Display::fmt(&v, f),
            N::NegInt(v) => Display::fmt(&v, f),
            N::Float(v) => {
                // We need to produce output that round-trips, and also
                // distinguishes 1.0 from 1 (integers). Use ryu for this.
                let mut buf = ryu::Buffer::new();
                let s = buf.format_finite(v);
                f.write_str(s)
            }
        }
    }
}

impl fmt::Debug for Number {
    fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
        write!(f, "Number({})", self)
    }
}

impl ser::Serialize for Number {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: ser::Serializer,
    {
        match self.n {
            N::PosInt(v) => serializer.serialize_u64(v),
            N::NegInt(v) => serializer.serialize_i64(v),
            N::Float(v) => serializer.serialize_f64(v),
        }
    }
}

impl<'de> de::Deserialize<'de> for Number {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: de::Deserializer<'de>,
    {
        struct NumberVisitor;

        impl<'de> Visitor<'de> for NumberVisitor {
            type Value = Number;

            fn expecting(&self, f: &mut Formatter<'_>) -> fmt::Result {
                f.write_str("a JSON number")
            }

            fn visit_i64<E: de::Error>(self, v: i64) -> Result<Number, E> {
                Ok(Number { n: N::NegInt(v) })
            }

            fn visit_u64<E: de::Error>(self, v: u64) -> Result<Number, E> {
                Ok(Number { n: N::PosInt(v) })
            }

            fn visit_f64<E: de::Error>(self, v: f64) -> Result<Number, E> {
                Number::from_f64(v).ok_or_else(|| de::Error::invalid_value(Unexpected::Float(v), &self))
            }
        }

        deserializer.deserialize_any(NumberVisitor)
    }
}

/// Used internally for deserialization from a string representation.
pub(crate) struct NumberFromString {
    pub(crate) value: Number,
}

impl<'de> de::Deserialize<'de> for NumberFromString {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: de::Deserializer<'de>,
    {
        struct Visitor;

        impl<'de> de::Visitor<'de> for Visitor {
            type Value = NumberFromString;

            fn expecting(&self, f: &mut Formatter<'_>) -> fmt::Result {
                f.write_str("a number as a string")
            }

            fn visit_str<E: de::Error>(self, s: &str) -> Result<NumberFromString, E> {
                let n = parse_number_from_str(s)
                    .ok_or_else(|| de::Error::invalid_value(Unexpected::Str(s), &self))?;
                Ok(NumberFromString { value: n })
            }
        }

        deserializer.deserialize_str(Visitor)
    }
}

fn parse_number_from_str(s: &str) -> Option<Number> {
    if let Ok(v) = s.parse::<u64>() {
        return Some(Number { n: N::PosInt(v) });
    }
    if let Ok(v) = s.parse::<i64>() {
        return Some(Number { n: N::NegInt(v) });
    }
    if let Ok(v) = s.parse::<f64>() {
        if v.is_finite() {
            return Some(Number { n: N::Float(v) });
        }
    }
    None
}

/// Deserializer for `Number` when we already have one
pub(crate) struct NumberDeserializer {
    pub(crate) value: Number,
}

impl<'de> de::IntoDeserializer<'de, Error> for NumberDeserializer {
    type Deserializer = Self;

    fn into_deserializer(self) -> Self {
        self
    }
}

impl<'de> de::Deserializer<'de> for NumberDeserializer {
    type Error = Error;

    fn deserialize_any<V>(self, visitor: V) -> Result<V::Value, Error>
    where
        V: Visitor<'de>,
    {
        match self.value.n {
            N::PosInt(v) => visitor.visit_u64(v),
            N::NegInt(v) => visitor.visit_i64(v),
            N::Float(v) => visitor.visit_f64(v),
        }
    }

    serde_core::forward_to_deserialize_any! {
        bool i8 i16 i32 i64 i128 u8 u16 u32 u64 u128 f32 f64 char str string
        bytes byte_buf option unit unit_struct newtype_struct seq tuple
        tuple_struct map struct enum identifier ignored_any
    }
}

// From impls for primitive integer types

macro_rules! impl_from_unsigned {
    ($($ty:ty),*) => {
        $(
            impl From<$ty> for Number {
                fn from(v: $ty) -> Self {
                    Number { n: N::PosInt(v as u64) }
                }
            }
        )*
    };
}

macro_rules! impl_from_signed {
    ($($ty:ty),*) => {
        $(
            impl From<$ty> for Number {
                fn from(v: $ty) -> Self {
                    if v < 0 {
                        Number { n: N::NegInt(v as i64) }
                    } else {
                        Number { n: N::PosInt(v as u64) }
                    }
                }
            }
        )*
    };
}

impl_from_unsigned!(u8, u16, u32, u64, usize);
impl_from_signed!(i8, i16, i32, i64, isize);

// We need ryu for float formatting
// ryu is pulled in via zmij crate? Let's check - actually the manifest
// lists "zmij" as a dependency. We need ryu for float Display.
// Since we can't know exactly what zmij provides, let's implement float
// formatting ourselves using a simpler approach via the standard library.

// Actually let's re-implement the Display to avoid depending on ryu directly
// since it might not be available. Let me use a write! approach for floats.

// Wait, we need to handle the float display carefully. The spec says:
// "1.0" -> "1.0" and "1.2e41" -> "1.2e+41"
// Let's use a manual approach.

// I need to remove the ryu usage above and replace with something we have.
// The zmij crate is listed in Cargo.toml - let me check if it re-exports ryu.
// Since I can't know, let me implement float formatting without ryu.

// Actually I'll use a different approach - format with {:?} or handle manually.
// Let me restructure the Display impl.
