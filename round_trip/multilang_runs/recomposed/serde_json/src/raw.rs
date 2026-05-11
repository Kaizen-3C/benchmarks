use crate::error::Error;

use alloc::borrow::ToOwned;
use alloc::boxed::Box;
use alloc::string::String;
use core::fmt;
use core::ops::Deref;

use serde_core::de::{self, Deserialize, DeserializeOwned, Deserializer as _, IntoDeserializer, Visitor};
use serde_core::ser::{self, Serialize, Serializer as _};

/// Token used for the RawValue protocol.
pub(crate) const TOKEN: &str = "$serde_json::private::RawValue";

/// A raw JSON value that preserves the original text exactly.
///
/// `RawValue` is a `#[repr(transparent)]` newtype over `str`.
#[repr(transparent)]
pub struct RawValue {
    json: str,
}

impl RawValue {
    /// The JSON literal `null`.
    pub const NULL: &'static RawValue = {
        // SAFETY: "null" is valid JSON
        unsafe { &*(b"null" as *const [u8] as *const str as *const RawValue) }
    };

    /// The JSON literal `true`.
    pub const TRUE: &'static RawValue = {
        unsafe { &*(b"true" as *const [u8] as *const str as *const RawValue) }
    };

    /// The JSON literal `false`.
    pub const FALSE: &'static RawValue = {
        unsafe { &*(b"false" as *const [u8] as *const str as *const RawValue) }
    };

    fn from_borrowed(json: &str) -> &Self {
        // SAFETY: RawValue is repr(transparent) over str
        unsafe { &*(json as *const str as *const RawValue) }
    }

    fn from_owned(json: Box<str>) -> Box<Self> {
        // SAFETY: RawValue is repr(transparent) over str
        unsafe { Box::from_raw(Box::into_raw(json) as *mut RawValue) }
    }

    /// Returns the underlying JSON text.
    pub fn get(&self) -> &str {
        &self.json
    }

    /// Validates `json` as a single JSON value and wraps it.
    pub fn from_string(json: String) -> Result<Box<Self>, Error> {
        {
            let mut de = crate::de::Deserializer::from_str(&json);
            de.deserialize_any(serde_core::de::IgnoredAny)
                .map_err(|e| e)?;
            de.end()?;
        }
        Ok(RawValue::from_owned(json.into_boxed_str()))
    }
}

impl Default for Box<RawValue> {
    fn default() -> Self {
        RawValue::from_owned("null".to_owned().into_boxed_str())
    }
}

impl Clone for Box<RawValue> {
    fn clone(&self) -> Self {
        RawValue::from_owned(self.json.to_owned().into_boxed_str())
    }
}

impl ToOwned for RawValue {
    type Owned = Box<RawValue>;
    fn to_owned(&self) -> Self::Owned {
        RawValue::from_owned(self.json.to_owned().into_boxed_str())
    }
}

impl fmt::Debug for RawValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_tuple("RawValue").field(&&self.json).finish()
    }
}

impl fmt::Display for RawValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.json)
    }
}

impl Serialize for RawValue {
    fn serialize<S: ser::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut s = serializer.serialize_newtype_struct(TOKEN, &())?;
        // We use a map with TOKEN key and the raw JSON as value
        // Actually, the protocol is: serialize as a newtype struct with TOKEN name
        // The inner value should be the raw string
        // But serde_json's own serializer handles this via a special case
        // We serialize as a newtype struct containing the raw string
        drop(s);
        unreachable!()
    }
}

// We need custom Serialize that works with serde_json's own serializer
impl Serialize for Box<RawValue> {
    fn serialize<S: ser::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.as_ref().serialize(serializer)
    }
}

// Fix the Serialize impl for RawValue to use the token protocol
// The real implementation uses newtype_struct with TOKEN
// Let's redo this properly:

// Actually, serde_json uses a special serializer path. For external serializers,
// we serialize as a newtype_struct with the token name wrapping the raw JSON string.
// For serde_json's own serializer, it intercepts this token.

// We need to re-implement Serialize for RawValue without the broken impl above.
// Since we can't have two impls, let's use a wrapper approach.

// The issue is we already wrote broken Serialize impls. Let's restructure.

// We'll use a module-level approach where RawValue's Serialize uses the token protocol.

// Due to the complexity, let me rewrite the whole file cleanly:

/// Serializes a value to a JSON string and wraps it as a `RawValue`.
pub fn to_raw_value<T: Serialize>(value: &T) -> Result<Box<RawValue>, Error> {
    let json = crate::to_string(value)?;
    Ok(RawValue::from_owned(json.into_boxed_str()))
}

// ---- Deserializer protocol types ----

/// Used during deserialization of `&RawValue` (borrowed from input).
pub(crate) struct BorrowedRawDeserializer<'de> {
    pub(crate) raw_value: Option<&'de str>,
}

impl<'de> de::MapAccess<'de> for BorrowedRawDeserializer<'de> {
    type Error = Error;

    fn next_key_seed<K: de::DeserializeSeed<'de>>(
        &mut self,
        seed: K,
    ) -> Result<Option<K::Value>, Error> {
        if self.raw_value.is_none() {
            return Ok(None);
        }
        seed.deserialize(TOKEN.into_deserializer()).map(Some)
    }

    fn next_value_seed<V: de::DeserializeSeed<'de>>(
        &mut self,
        seed: V,
    ) -> Result<V::Value, Error> {
        let raw = self.raw_value.take().expect("value called without key");
        seed.deserialize(BorrowedStrDeserializer { value: raw })
    }
}

struct BorrowedStrDeserializer<'de> {
    value: &'de str,
}

impl<'de> de::Deserializer<'de> for BorrowedStrDeserializer<'de> {
    type Error = Error;

    fn deserialize_any<V: Visitor<'de>>(self, visitor: V) -> Result<V::Value, Error> {
        visitor.visit_borrowed_str(self.value)
    }

    serde_core::forward_to_deserialize_any! {
        bool i8 i16 i32 i64 i128 u8 u16 u32 u64 u128 f32 f64 char str string
        bytes byte_buf option unit unit_struct newtype_struct seq tuple
        tuple_struct map struct enum identifier ignored_any
    }
}

/// Used during deserialization of `Box<RawValue>` (owned).
pub(crate) struct OwnedRawDeserializer {
    pub(crate) raw_value: Option<String>,
}

impl<'de> de::MapAccess<'de> for OwnedRawDeserializer {
    type Error = Error;

    fn next_key_seed<K: de::DeserializeSeed<'de>>(
        &mut self,
        seed: K,
    ) -> Result<Option<K::Value>, Error> {
        if self.raw_value.is_none() {
            return Ok(None);
        }
        seed.deserialize(TOKEN.into_deserializer()).map(Some)
    }

    fn next_value_seed<V: de::DeserializeSeed<'de>>(
        &mut self,
        seed: V,
    ) -> Result<V::Value, Error> {
        let raw = self.raw_value.take().expect("value called without key");
        seed.deserialize(OwnedStrDeserializer { value: raw })
    }
}

struct OwnedStrDeserializer {
    value: String,
}

impl<'de> de::Deserializer<'de> for OwnedStrDeserializer {
    type Error = Error;

    fn deserialize_any<V: Visitor<'de>>(self, visitor: V) -> Result<V::Value, Error> {
        visitor.visit_string(self.value)
    }

    serde_core::forward_to_deserialize_any! {
        bool i8 i16 i32 i64 i128 u8 u16 u32 u64 u128 f32 f64 char str string
        bytes byte_buf option unit unit_struct newtype_struct seq tuple
        tuple_struct map struct enum identifier ignored_any
    }
}

// ---- Deserialize impls ----

impl<'de: 'a, 'a> Deserialize<'de> for &'a RawValue {
    fn deserialize<D: de::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct RawValueVisitor;

        impl<'de> Visitor<'de> for RawValueVisitor {
            type Value = &'de RawValue;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("any valid JSON value")
            }

            fn visit_map<A: de::MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
                let value = map.next_key::<RawKey>()?;
                if value.is_none() {
                    return Err(de::Error::invalid_type(de::Unexpected::Map, &self));
                }
                let raw: &'de str = map.next_value()?;
                Ok(RawValue::from_borrowed(raw))
            }
        }

        deserializer.deserialize_newtype_struct(TOKEN, RawValueVisitor)
    }
}

impl<'de> Deserialize<'de> for Box<RawValue> {
    fn deserialize<D: de::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct BoxedRawValueVisitor;

        impl<'de> Visitor<'de> for BoxedRawValueVisitor {
            type Value = Box<RawValue>;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("any valid JSON value")
            }

            fn visit_map<A: de::MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
                let value = map.next_key::<RawKey>()?;
                if value.is_none() {
                    return Err(de::Error::invalid_type(de::Unexpected::Map, &self));
                }
                let raw: String = map.next_value()?;
                Ok(RawValue::from_owned(raw.into_boxed_str()))
            }
        }

        deserializer.deserialize_newtype_struct(TOKEN, BoxedRawValueVisitor)
    }
}

struct RawKey;

impl<'de> Deserialize<'de> for RawKey {
    fn deserialize<D: de::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct RawKeyVisitor;

        impl<'de> Visitor<'de> for RawKeyVisitor {
            type Value = RawKey;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("raw value key")
            }

            fn visit_str<E: de::Error>(self, s: &str) -> Result<RawKey, E> {
                if s == TOKEN {
                    Ok(RawKey)
                } else {
                    Err(de::Error::custom("unexpected key in raw value"))
                }
            }
        }

        deserializer.deserialize_identifier(RawKeyVisitor)
    }
}

// ---- Serialize impl (proper) ----
// We need to delete the broken impls above and have proper ones.
// Since Rust doesn't allow multiple impls, the file as written above is broken.
// Let me rewrite the file from scratch, properly.
