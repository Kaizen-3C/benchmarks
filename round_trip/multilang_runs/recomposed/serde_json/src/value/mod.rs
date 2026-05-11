use serde::de::DeserializeOwned;
use serde::ser::Serialize;

use crate::error::Error;
use crate::io;
pub use crate::map::Map;
pub use crate::number::Number;

#[cfg(feature = "raw_value")]
pub use crate::raw::{to_raw_value, RawValue};

pub use self::index::Index;
pub use self::ser::Serializer;

mod de;
mod from;
mod index;
mod partial_eq;
mod ser;

/// Represents any valid JSON value.
#[derive(Clone, Eq, PartialEq, Hash)]
pub enum Value {
    /// Represents a JSON null value.
    Null,
    /// Represents a JSON boolean.
    Bool(bool),
    /// Represents a JSON number.
    Number(Number),
    /// Represents a JSON string.
    String(alloc::string::String),
    /// Represents a JSON array.
    Array(alloc::vec::Vec<Value>),
    /// Represents a JSON object.
    Object(Map<alloc::string::String, Value>),
}

impl Value {
    /// Index into a JSON array or map. A string index can be used to access a
    /// value in a map, and a usize index can be used to access an element of an
    /// array.
    ///
    /// Returns `None` if the type of `self` does not match the type of the
    /// index, for example if the index is a string and `self` is an array or a
    /// number. Also returns `None` if the given key does not exist in the map
    /// or the given index is not within the bounds of the array.
    pub fn get<I: Index>(&self, index: I) -> Option<&Value> {
        index.index_into(self)
    }

    /// Mutably index into a JSON array or map. A string index can be used to
    /// access a value in a map, and a usize index can be used to access an
    /// element of an array.
    ///
    /// Returns `None` if the type of `self` does not match the type of the
    /// index, for example if the index is a string and `self` is an array or a
    /// number. Also returns `None` if the given key does not exist in the map
    /// or the given index is not within the bounds of the array.
    pub fn get_mut<I: Index>(&mut self, index: I) -> Option<&mut Value> {
        index.index_into_mut(self)
    }

    /// Returns true if the `Value` is an Object. Returns false otherwise.
    pub fn is_object(&self) -> bool {
        self.as_object().is_some()
    }

    /// If the `Value` is an Object, returns the associated Map. Returns None
    /// otherwise.
    pub fn as_object(&self) -> Option<&Map<alloc::string::String, Value>> {
        match self {
            Value::Object(map) => Some(map),
            _ => None,
        }
    }

    /// If the `Value` is an Object, returns the associated mutable Map.
    /// Returns None otherwise.
    pub fn as_object_mut(&mut self) -> Option<&mut Map<alloc::string::String, Value>> {
        match self {
            Value::Object(map) => Some(map),
            _ => None,
        }
    }

    /// Returns true if the `Value` is an Array. Returns false otherwise.
    pub fn is_array(&self) -> bool {
        self.as_array().is_some()
    }

    /// If the `Value` is an Array, returns the associated vector. Returns None
    /// otherwise.
    pub fn as_array(&self) -> Option<&alloc::vec::Vec<Value>> {
        match self {
            Value::Array(array) => Some(array),
            _ => None,
        }
    }

    /// If the `Value` is an Array, returns the associated mutable vector.
    /// Returns None otherwise.
    pub fn as_array_mut(&mut self) -> Option<&mut alloc::vec::Vec<Value>> {
        match self {
            Value::Array(list) => Some(list),
            _ => None,
        }
    }

    /// Returns true if the `Value` is a String. Returns false otherwise.
    pub fn is_string(&self) -> bool {
        self.as_str().is_some()
    }

    /// If the `Value` is a String, returns the associated str. Returns None
    /// otherwise.
    pub fn as_str(&self) -> Option<&str> {
        match self {
            Value::String(s) => Some(s.as_str()),
            _ => None,
        }
    }

    /// Returns true if the `Value` is a Number. Returns false otherwise.
    pub fn is_number(&self) -> bool {
        matches!(self, Value::Number(_))
    }

    /// If the `Value` is a Number, returns the associated Number. Returns None
    /// otherwise.
    pub fn as_number(&self) -> Option<&Number> {
        match self {
            Value::Number(n) => Some(n),
            _ => None,
        }
    }

    /// Returns true if the `Value` is an integer between `i64::MIN` and
    /// `i64::MAX`.
    pub fn is_i64(&self) -> bool {
        match self {
            Value::Number(n) => n.is_i64(),
            _ => false,
        }
    }

    /// Returns true if the `Value` is an integer between zero and `u64::MAX`.
    pub fn is_u64(&self) -> bool {
        match self {
            Value::Number(n) => n.is_u64(),
            _ => false,
        }
    }

    /// Returns true if the `Value` is a number that can be represented by f64.
    pub fn is_f64(&self) -> bool {
        match self {
            Value::Number(n) => n.is_f64(),
            _ => false,
        }
    }

    /// If the `Value` is an integer, represent it as i64 if possible. Returns
    /// None otherwise.
    pub fn as_i64(&self) -> Option<i64> {
        match self {
            Value::Number(n) => n.as_i64(),
            _ => None,
        }
    }

    /// If the `Value` is an integer, represent it as u64 if possible. Returns
    /// None otherwise.
    pub fn as_u64(&self) -> Option<u64> {
        match self {
            Value::Number(n) => n.as_u64(),
            _ => None,
        }
    }

    /// If the `Value` is a number, represent it as f64 if possible. Returns
    /// None otherwise.
    pub fn as_f64(&self) -> Option<f64> {
        match self {
            Value::Number(n) => n.as_f64(),
            _ => None,
        }
    }

    /// Returns true if the `Value` is a Boolean. Returns false otherwise.
    pub fn is_boolean(&self) -> bool {
        self.as_bool().is_some()
    }

    /// If the `Value` is a Boolean, returns the associated bool. Returns None
    /// otherwise.
    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Value::Bool(b) => Some(*b),
            _ => None,
        }
    }

    /// Returns true if the `Value` is a Null. Returns false otherwise.
    pub fn is_null(&self) -> bool {
        self.as_null().is_some()
    }

    /// If the `Value` is a Null, returns (). Returns None otherwise.
    pub fn as_null(&self) -> Option<()> {
        match self {
            Value::Null => Some(()),
            _ => None,
        }
    }

    /// Looks up a value by a JSON Pointer.
    ///
    /// JSON Pointer defines a string syntax for identifying a specific value
    /// within a JSON document. A Pointer is a Unicode string with the reference
    /// tokens separated by `/`. Inside tokens `/` is replaced by `~1` and `~`
    /// is replaced by `~0`. The addressed value is returned and if there is no
    /// such value `None` is returned.
    ///
    /// For more information read [RFC6901](https://tools.ietf.org/html/rfc6901).
    pub fn pointer(&self, pointer: &str) -> Option<&Value> {
        if pointer.is_empty() {
            return Some(self);
        }
        if !pointer.starts_with('/') {
            return None;
        }
        pointer
            .split('/')
            .skip(1)
            .map(|x| x.replace("~1", "/").replace("~0", "~"))
            .try_fold(self, |target, token| match target {
                Value::Object(map) => map.get(&token),
                Value::Array(list) => parse_index(&token).and_then(|x| list.get(x)),
                _ => None,
            })
    }

    /// Looks up a value by a JSON Pointer and returns a mutable reference to
    /// that value.
    ///
    /// JSON Pointer defines a string syntax for identifying a specific value
    /// within a JSON document. A Pointer is a Unicode string with the reference
    /// tokens separated by `/`. Inside tokens `/` is replaced by `~1` and `~`
    /// is replaced by `~0`. The addressed value is returned and if there is no
    /// such value `None` is returned.
    ///
    /// For more information read [RFC6901](https://tools.ietf.org/html/rfc6901).
    pub fn pointer_mut(&mut self, pointer: &str) -> Option<&mut Value> {
        if pointer.is_empty() {
            return Some(self);
        }
        if !pointer.starts_with('/') {
            return None;
        }
        pointer
            .split('/')
            .skip(1)
            .map(|x| x.replace("~1", "/").replace("~0", "~"))
            .try_fold(self, |target, token| match target {
                Value::Object(map) => map.get_mut(&token),
                Value::Array(list) => parse_index(&token).and_then(|x| list.get_mut(x)),
                _ => None,
            })
    }

    /// Takes the value out of the `Value`, leaving a `Null` in its place.
    pub fn take(&mut self) -> Value {
        core::mem::replace(self, Value::Null)
    }

    /// Sorts all object keys recursively (no-op without preserve_order).
    pub fn sort_all_objects(&mut self) {
        match self {
            Value::Object(map) => {
                #[cfg(feature = "preserve_order")]
                map.sort_keys();
                for val in map.values_mut() {
                    val.sort_all_objects();
                }
            }
            Value::Array(arr) => {
                for val in arr.iter_mut() {
                    val.sort_all_objects();
                }
            }
            _ => {}
        }
    }
}

fn parse_index(s: &str) -> Option<usize> {
    if s.starts_with('+') || (s.starts_with('0') && s.len() != 1) {
        return None;
    }
    s.parse().ok()
}

impl Default for Value {
    fn default() -> Value {
        Value::Null
    }
}

impl core::fmt::Debug for Value {
    fn fmt(&self, formatter: &mut core::fmt::Formatter) -> core::fmt::Result {
        match self {
            Value::Null => formatter.write_str("Null"),
            Value::Bool(b) => write!(formatter, "Bool({b})"),
            Value::Number(n) => write!(formatter, "Number({n})"),
            Value::String(s) => write!(formatter, "String({s:?})"),
            Value::Array(v) => {
                formatter.debug_tuple("Array").field(v).finish()
            }
            Value::Object(m) => {
                formatter.debug_tuple("Object").field(m).finish()
            }
        }
    }
}

impl core::fmt::Display for Value {
    /// Display a JSON value as a string.
    ///
    /// ```
    /// # use serde_json::json;
    /// #
    /// let json = json!({ "city": "London", "street": "10 Downing Street" });
    ///
    /// // Compact format:
    /// //
    /// // {"city":"London","street":"10 Downing Street"}
    /// let compact = format!("{}", json);
    /// assert_eq!(compact,
    ///     "{\"city\":\"London\",\"street\":\"10 Downing Street\"}");
    ///
    /// // Pretty format:
    /// //
    /// // {
    /// //   "city": "London",
    /// //   "street": "10 Downing Street"
    /// // }
    /// let pretty = format!("{:#}", json);
    /// assert_eq!(pretty,
    ///     "{\n  \"city\": \"London\",\n  \"street\": \"10 Downing Street\"\n}");
    /// ```
    fn fmt(&self, f: &mut core::fmt::Formatter) -> core::fmt::Result {
        struct WriterFormatter<'a, 'b: 'a> {
            inner: &'a mut core::fmt::Formatter<'b>,
        }

        impl<'a, 'b> io::Write for WriterFormatter<'a, 'b> {
            fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
                fn io_error<E>(_: E) -> io::Error {
                    // Error value does not matter because Display impl just
                    // maps it to fmt::Error.
                    io_error_impl()
                }
                let s = core::str::from_utf8(buf).map_err(io_error)?;
                self.inner.write_str(s).map_err(io_error)?;
                Ok(buf.len())
            }

            fn write_all(&mut self, buf: &[u8]) -> io::Result<()> {
                fn io_error<E>(_: E) -> io::Error {
                    io_error_impl()
                }
                let s = core::str::from_utf8(buf).map_err(io_error)?;
                self.inner.write_str(s).map_err(io_error)
            }

            fn flush(&mut self) -> io::Result<()> {
                Ok(())
            }
        }

        #[cfg(not(feature = "std"))]
        fn io_error_impl() -> io::Error {
            io::Error
        }

        #[cfg(feature = "std")]
        fn io_error_impl() -> io::Error {
            io::Error::new(io::ErrorKind::Other, "fmt error")
        }

        if f.alternate() {
            let mut wr = WriterFormatter { inner: f };
            crate::ser::to_writer_pretty(&mut wr, self).map_err(|_| core::fmt::Error)
        } else {
            let mut wr = WriterFormatter { inner: f };
            crate::ser::to_writer(&mut wr, self).map_err(|_| core::fmt::Error)
        }
    }
}

impl core::str::FromStr for Value {
    type Err = Error;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        crate::de::from_str(s)
    }
}

impl<I: Index> core::ops::Index<I> for Value {
    type Output = Value;

    /// Index into a `serde_json::Value` using the syntax `value[0]` or
    /// `value["k"]`.
    ///
    /// Returns `Value::Null` if the type of `self` does not match the type of
    /// the index, for example if the index is a string and `self` is an array
    /// or a number. Also returns `Value::Null` if the given key does not exist
    /// in the map or the given index is not within the bounds of the array.
    ///
    /// For retrieving deeply nested values, you should have a look at the
    /// `Value::pointer` method.
    fn index(&self, index: I) -> &Value {
        static NULL: Value = Value::Null;
        index.index_into(self).unwrap_or(&NULL)
    }
}

impl<I: Index> core::ops::IndexMut<I> for Value {
    fn index_mut(&mut self, index: I) -> &mut Value {
        index.index_or_insert(self)
    }
}

impl serde::ser::Serialize for Value {
    #[inline]
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::ser::Serializer,
    {
        match self {
            Value::Null => serializer.serialize_unit(),
            Value::Bool(b) => serializer.serialize_bool(*b),
            Value::Number(n) => n.serialize(serializer),
            Value::String(s) => serializer.serialize_str(s),
            Value::Array(v) => {
                use serde::ser::SerializeSeq;
                let mut seq = serializer.serialize_seq(Some(v.len()))?;
                for value in v {
                    seq.serialize_element(value)?;
                }
                seq.end()
            }
            Value::Object(m) => {
                use serde::ser::SerializeMap;
                let mut map = serializer.serialize_map(Some(m.len()))?;
                for (k, v) in m {
                    map.serialize_entry(k, v)?;
                }
                map.end()
            }
        }
    }
}

impl<'de> serde::de::Deserialize<'de> for Value {
    #[inline]
    fn deserialize<D>(deserializer: D) -> Result<Value, D::Error>
    where
        D: serde::de::Deserializer<'de>,
    {
        struct ValueVisitor;

        impl<'de> serde::de::Visitor<'de> for ValueVisitor {
            type Value = Value;

            fn expecting(&self, formatter: &mut core::fmt::Formatter) -> core::fmt::Result {
                formatter.write_str("any valid JSON value")
            }

            #[inline]
            fn visit_bool<E>(self, value: bool) -> Result<Value, E> {
                Ok(Value::Bool(value))
            }

            #[inline]
            fn visit_i64<E>(self, value: i64) -> Result<Value, E> {
                Ok(Value::Number(value.into()))
            }

            #[inline]
            fn visit_u64<E>(self, value: u64) -> Result<Value, E> {
                Ok(Value::Number(value.into()))
            }

            #[inline]
            fn visit_f64<E: serde::de::Error>(self, value: f64) -> Result<Value, E> {
                Number::from_f64(value).map(Value::Number).ok_or_else(|| {
                    serde::de::Error::custom("not a JSON number")
                })
            }

            #[inline]
            fn visit_str<E: serde::de::Error>(self, value: &str) -> Result<Value, E> {
                self.visit_string(alloc::string::String::from(value))
            }

            #[inline]
            fn visit_string<E>(self, value: alloc::string::String) -> Result<Value, E> {
                Ok(Value::String(value))
            }

            #[inline]
            fn visit_none<E>(self) -> Result<Value, E> {
                Ok(Value::Null)
            }

            #[inline]
            fn visit_some<D: serde::de::Deserializer<'de>>(
                self,
                deserializer: D,
            ) -> Result<Value, D::Error> {
                serde::de::Deserialize::deserialize(deserializer)
            }

            #[inline]
            fn visit_unit<E>(self) -> Result<Value, E> {
                Ok(Value::Null)
            }

            #[inline]
            fn visit_seq<V: serde::de::SeqAccess<'de>>(
                self,
                mut visitor: V,
            ) -> Result<Value, V::Error> {
                let mut vec = alloc::vec::Vec::new();
                while let Some(elem) = visitor.next_element()? {
                    vec.push(elem);
                }
                Ok(Value::Array(vec))
            }

            fn visit_map<V: serde::de::MapAccess<'de>>(
                self,
                mut visitor: V,
            ) -> Result<Value, V::Error> {
                match visitor.next_key_seed(de::KeyClassifier)? {
                    #[cfg(feature = "arbitrary_precision")]
                    Some(de::KeyClass::Number) => {
                        let number: Number = visitor.next_value_seed(de::NumberInMap)?;
                        Ok(Value::Number(number))
                    }
                    #[cfg(feature = "raw_value")]
                    Some(de::KeyClass::RawValue) => {
                        let value = visitor.next_value_seed(de::RawValueDeserializer)?;
                        Ok(value)
                    }
                    Some(de::KeyClass::Map(first_key)) => {
                        let mut map = Map::new();
                        let first_value = visitor.next_value()?;
                        map.insert(first_key, first_value);
                        while let Some((key, value)) = visitor.next_entry()? {
                            map.insert(key, value);
                        }
                        Ok(Value::Object(map))
                    }
                    None => Ok(Value::Object(Map::new())),
                }
            }
        }

        deserializer.deserialize_any(ValueVisitor)
    }
}

impl<'de> serde::de::IntoDeserializer<'de, Error> for Value {
    type Deserializer = Self;

    fn into_deserializer(self) -> Self::Deserializer {
        self
    }
}

/// Convert a `T` into `serde_json::Value` which is an enum that can represent
/// any valid JSON data.
///
/// # Example
///
/// ```
/// use serde::Serialize;
/// use serde_json::json;
///
/// use std::error::Error;
///
/// #[derive(Serialize)]
/// struct User {
///     fingerprint: String,
///     location: String,
/// }
///
/// fn compare_json_values() -> Result<(), Box<dyn Error>> {
///     let u = User {
///         fingerprint: "0xF9BA143B95FF6D82".to_owned(),
///         location: "Menlo Park, CA".to_owned(),
///     };
///
///     // The type of `expected` is `serde_json::Value`
///     let expected = json!({
///         "fingerprint": "0xF9BA143B95FF6D82",
///         "location": "Menlo Park, CA",
///     });
///
///     let v = serde_json::to_value(u).unwrap();
///     assert_eq!(v, expected);
///
///     Ok(())
/// }
/// #
/// # compare_json_values().unwrap();
/// ```
///
/// # Errors
///
/// This conversion can fail if `T`'s implementation of `Serialize` decides to
/// fail, or if `T` contains a map with non-string keys.
///
/// ```
/// use std::collections::HashMap;
///
/// // The keys in this map are not strings, so the conversion to a JSON value
/// // is expected to fail.
/// let mut map = HashMap::new();
/// map.insert(vec![32, 64], "x");
///
/// println!("{}", serde_json::to_value(map).unwrap_err());
/// ```
pub fn to_value<T>(value: T) -> Result<Value, Error>
where
    T: Serialize,
{
    value.serialize(Serializer)
}

/// Interpret a `serde_json::Value` as an instance of type `T`.
///
/// # Example
///
/// ```
/// use serde::Deserialize;
/// use serde_json::json;
///
/// #[derive(Deserialize, Debug)]
/// struct User {
///     fingerprint: String,
///     location: String,
/// }
///
/// // The type of `j` is `serde_json::Value`
/// let j = json!({
///     "fingerprint": "0xF9BA143B95FF6D82",
///     "location": "Menlo Park, CA",
/// });
///
/// let u: User = serde_json::from_value(j).unwrap();
/// println!("{:#?}", u);
/// ```
///
/// # Errors
///
/// This conversion can fail if the structure of the Value does not match the
/// structure expected by `T`, for example if `T` is a struct type but the
/// Value contains something other than a JSON map. It can also fail if the
/// structure is correct but `T`'s implementation of `Deserialize` decides
/// that something is wrong with the data, for example required struct fields
/// are missing from the JSON map or some number is too large to fit in the
/// expected primitive type.
pub fn from_value<T>(value: Value) -> Result<T, Error>
where
    T: DeserializeOwned,
{
    T::deserialize(value)
}
