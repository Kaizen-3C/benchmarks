use crate::error::{Error, ErrorCode, Result};
use crate::map::Map;
use crate::value::{to_value, Value};
use alloc::borrow::ToOwned;
use alloc::string::{String, ToString};
use alloc::vec::Vec;
use serde_core::ser::{self, Serialize};

pub struct Serializer;

impl serde_core::Serializer for Serializer {
    type Ok = Value;
    type Error = Error;

    type SerializeSeq = SerializeVec;
    type SerializeTuple = SerializeVec;
    type SerializeTupleStruct = SerializeVec;
    type SerializeTupleVariant = SerializeTupleVariant;
    type SerializeMap = SerializeMap;
    type SerializeStruct = SerializeMap;
    type SerializeStructVariant = SerializeStructVariant;

    #[inline]
    fn serialize_bool(self, value: bool) -> Result<Value> {
        Ok(Value::Bool(value))
    }

    #[inline]
    fn serialize_i8(self, value: i8) -> Result<Value> {
        self.serialize_i64(value as i64)
    }

    #[inline]
    fn serialize_i16(self, value: i16) -> Result<Value> {
        self.serialize_i64(value as i64)
    }

    #[inline]
    fn serialize_i32(self, value: i32) -> Result<Value> {
        self.serialize_i64(value as i64)
    }

    fn serialize_i64(self, value: i64) -> Result<Value> {
        Ok(Value::Number(value.into()))
    }

    fn serialize_i128(self, value: i128) -> Result<Value> {
        #[cfg(feature = "arbitrary_precision")]
        {
            Ok(Value::Number(value.into()))
        }
        #[cfg(not(feature = "arbitrary_precision"))]
        {
            if let Ok(i) = i64::try_from(value) {
                Ok(Value::Number(i.into()))
            } else if let Ok(u) = u64::try_from(value) {
                Ok(Value::Number(u.into()))
            } else {
                Err(Error::syntax(ErrorCode::NumberOutOfRange, 0, 0))
            }
        }
    }

    #[inline]
    fn serialize_u8(self, value: u8) -> Result<Value> {
        self.serialize_u64(value as u64)
    }

    #[inline]
    fn serialize_u16(self, value: u16) -> Result<Value> {
        self.serialize_u64(value as u64)
    }

    #[inline]
    fn serialize_u32(self, value: u32) -> Result<Value> {
        self.serialize_u64(value as u64)
    }

    #[inline]
    fn serialize_u64(self, value: u64) -> Result<Value> {
        Ok(Value::Number(value.into()))
    }

    fn serialize_u128(self, value: u128) -> Result<Value> {
        #[cfg(feature = "arbitrary_precision")]
        {
            Ok(Value::Number(value.into()))
        }
        #[cfg(not(feature = "arbitrary_precision"))]
        {
            if let Ok(u) = u64::try_from(value) {
                Ok(Value::Number(u.into()))
            } else {
                Err(Error::syntax(ErrorCode::NumberOutOfRange, 0, 0))
            }
        }
    }

    #[inline]
    fn serialize_f32(self, value: f32) -> Result<Value> {
        self.serialize_f64(value as f64)
    }

    #[inline]
    fn serialize_f64(self, value: f64) -> Result<Value> {
        Ok(crate::number::Number::from_f64(value)
            .map(Value::Number)
            .unwrap_or(Value::Null))
    }

    #[inline]
    fn serialize_char(self, value: char) -> Result<Value> {
        let mut s = String::new();
        s.push(value);
        Ok(Value::String(s))
    }

    #[inline]
    fn serialize_str(self, value: &str) -> Result<Value> {
        Ok(Value::String(value.to_owned()))
    }

    fn serialize_bytes(self, value: &[u8]) -> Result<Value> {
        let vec = value.iter().map(|&b| Value::Number(b.into())).collect();
        Ok(Value::Array(vec))
    }

    #[inline]
    fn serialize_unit(self) -> Result<Value> {
        Ok(Value::Null)
    }

    #[inline]
    fn serialize_unit_struct(self, _name: &'static str) -> Result<Value> {
        self.serialize_unit()
    }

    #[inline]
    fn serialize_unit_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
    ) -> Result<Value> {
        self.serialize_str(variant)
    }

    #[inline]
    fn serialize_newtype_struct<T>(self, _name: &'static str, value: &T) -> Result<Value>
    where
        T: ?Sized + Serialize,
    {
        value.serialize(self)
    }

    fn serialize_newtype_variant<T>(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
        value: &T,
    ) -> Result<Value>
    where
        T: ?Sized + Serialize,
    {
        let mut values = Map::new();
        values.insert(String::from(variant), to_value(value)?);
        Ok(Value::Object(values))
    }

    #[inline]
    fn serialize_none(self) -> Result<Value> {
        self.serialize_unit()
    }

    #[inline]
    fn serialize_some<T>(self, value: &T) -> Result<Value>
    where
        T: ?Sized + Serialize,
    {
        value.serialize(self)
    }

    fn serialize_seq(self, len: Option<usize>) -> Result<Self::SerializeSeq> {
        Ok(SerializeVec {
            vec: Vec::with_capacity(len.unwrap_or(0)),
        })
    }

    fn serialize_tuple(self, len: usize) -> Result<Self::SerializeTuple> {
        self.serialize_seq(Some(len))
    }

    fn serialize_tuple_struct(
        self,
        _name: &'static str,
        len: usize,
    ) -> Result<Self::SerializeTupleStruct> {
        self.serialize_seq(Some(len))
    }

    fn serialize_tuple_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
        len: usize,
    ) -> Result<Self::SerializeTupleVariant> {
        Ok(SerializeTupleVariant {
            name: String::from(variant),
            vec: Vec::with_capacity(len),
        })
    }

    fn serialize_map(self, _len: Option<usize>) -> Result<Self::SerializeMap> {
        Ok(SerializeMap::Map {
            map: Map::new(),
            next_key: None,
        })
    }

    fn serialize_struct(self, name: &'static str, len: usize) -> Result<Self::SerializeStruct> {
        match name {
            #[cfg(feature = "arbitrary_precision")]
            crate::number::TOKEN => Ok(SerializeMap::Number { out_value: None }),
            #[cfg(feature = "raw_value")]
            crate::raw::TOKEN => Ok(SerializeMap::RawValue { out_value: None }),
            _ => self.serialize_map(Some(len)),
        }
    }

    fn serialize_struct_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeStructVariant> {
        Ok(SerializeStructVariant {
            name: String::from(variant),
            map: Map::new(),
        })
    }
}

pub struct SerializeVec {
    vec: Vec<Value>,
}

pub struct SerializeTupleVariant {
    name: String,
    vec: Vec<Value>,
}

pub enum SerializeMap {
    Map {
        map: Map<String, Value>,
        next_key: Option<String>,
    },
    #[cfg(feature = "arbitrary_precision")]
    Number { out_value: Option<Value> },
    #[cfg(feature = "raw_value")]
    RawValue { out_value: Option<Value> },
}

pub struct SerializeStructVariant {
    name: String,
    map: Map<String, Value>,
}

impl ser::SerializeSeq for SerializeVec {
    type Ok = Value;
    type Error = Error;

    fn serialize_element<T>(&mut self, value: &T) -> Result<()>
    where
        T: ?Sized + Serialize,
    {
        self.vec.push(to_value(value)?);
        Ok(())
    }

    fn end(self) -> Result<Value> {
        Ok(Value::Array(self.vec))
    }
}

impl ser::SerializeTuple for SerializeVec {
    type Ok = Value;
    type Error = Error;

    fn serialize_element<T>(&mut self, value: &T) -> Result<()>
    where
        T: ?Sized + Serialize,
    {
        ser::SerializeSeq::serialize_element(self, value)
    }

    fn end(self) -> Result<Value> {
        ser::SerializeSeq::end(self)
    }
}

impl ser::SerializeTupleStruct for SerializeVec {
    type Ok = Value;
    type Error = Error;

    fn serialize_field<T>(&mut self, value: &T) -> Result<()>
    where
        T: ?Sized + Serialize,
    {
        ser::SerializeSeq::serialize_element(self, value)
    }

    fn end(self) -> Result<Value> {
        ser::SerializeSeq::end(self)
    }
}

impl ser::SerializeTupleVariant for SerializeTupleVariant {
    type Ok = Value;
    type Error = Error;

    fn serialize_field<T>(&mut self, value: &T) -> Result<()>
    where
        T: ?Sized + Serialize,
    {
        self.vec.push(to_value(value)?);
        Ok(())
    }

    fn end(self) -> Result<Value> {
        let mut object = Map::new();
        object.insert(self.name, Value::Array(self.vec));
        Ok(Value::Object(object))
    }
}

impl ser::SerializeMap for SerializeMap {
    type Ok = Value;
    type Error = Error;

    fn serialize_key<T>(&mut self, key: &T) -> Result<()>
    where
        T: ?Sized + Serialize,
    {
        match self {
            SerializeMap::Map { next_key, .. } => {
                *next_key = Some(key.serialize(MapKeySerializer)?);
                Ok(())
            }
            #[cfg(feature = "arbitrary_precision")]
            SerializeMap::Number { .. } => Err(Error::syntax(ErrorCode::Message(
                "unexpected call to serialize_key for Number".into(),
            ), 0, 0)),
            #[cfg(feature = "raw_value")]
            SerializeMap::RawValue { .. } => Err(Error::syntax(ErrorCode::Message(
                "unexpected call to serialize_key for RawValue".into(),
            ), 0, 0)),
        }
    }

    fn serialize_value<T>(&mut self, value: &T) -> Result<()>
    where
        T: ?Sized + Serialize,
    {
        match self {
            SerializeMap::Map { map, next_key } => {
                let key = next_key.take();
                let key = key.expect("serialize_value called before serialize_key");
                map.insert(key, to_value(value)?);
                Ok(())
            }
            #[cfg(feature = "arbitrary_precision")]
            SerializeMap::Number { .. } => Err(Error::syntax(ErrorCode::Message(
                "unexpected call to serialize_value for Number".into(),
            ), 0, 0)),
            #[cfg(feature = "raw_value")]
            SerializeMap::RawValue { .. } => Err(Error::syntax(ErrorCode::Message(
                "unexpected call to serialize_value for RawValue".into(),
            ), 0, 0)),
        }
    }

    fn end(self) -> Result<Value> {
        match self {
            SerializeMap::Map { map, .. } => Ok(Value::Object(map)),
            #[cfg(feature = "arbitrary_precision")]
            SerializeMap::Number { out_value, .. } => {
                out_value.ok_or_else(|| Error::syntax(ErrorCode::Message("expected number".into()), 0, 0))
            }
            #[cfg(feature = "raw_value")]
            SerializeMap::RawValue { out_value, .. } => {
                out_value.ok_or_else(|| Error::syntax(ErrorCode::Message("expected raw value".into()), 0, 0))
            }
        }
    }
}

impl ser::SerializeStruct for SerializeMap {
    type Ok = Value;
    type Error = Error;

    fn serialize_field<T>(&mut self, key: &'static str, value: &T) -> Result<()>
    where
        T: ?Sized + Serialize,
    {
        match self {
            SerializeMap::Map { .. } => ser::SerializeMap::serialize_entry(self, key, value),
            #[cfg(feature = "arbitrary_precision")]
            SerializeMap::Number { out_value } => {
                if key == crate::number::TOKEN {
                    *out_value = Some(value.serialize(NumberValueEmitter)?);
                    Ok(())
                } else {
                    Err(Error::syntax(ErrorCode::Message("unexpected field in Number".into()), 0, 0))
                }
            }
            #[cfg(feature = "raw_value")]
            SerializeMap::RawValue { out_value } => {
                if key == crate::raw::TOKEN {
                    *out_value = Some(value.serialize(RawValueEmitter)?);
                    Ok(())
                } else {
                    Err(Error::syntax(ErrorCode::Message("unexpected field in RawValue".into()), 0, 0))
                }
            }
        }
    }

    fn end(self) -> Result<Value> {
        ser::SerializeMap::end(self)
    }
}

impl ser::SerializeStructVariant for SerializeStructVariant {
    type Ok = Value;
    type Error = Error;

    fn serialize_field<T>(&mut self, key: &'static str, value: &T) -> Result<()>
    where
        T: ?Sized + Serialize,
    {
        self.map.insert(String::from(key), to_value(value)?);
        Ok(())
    }

    fn end(self) -> Result<Value> {
        let mut object = Map::new();
        object.insert(self.name, Value::Object(self.map));
        Ok(Value::Object(object))
    }
}

struct MapKeySerializer;

fn key_must_be_a_string() -> Error {
    Error::syntax(ErrorCode::KeyMustBeAString, 0, 0)
}

impl serde_core::Serializer for MapKeySerializer {
    type Ok = String;
    type Error = Error;

    type SerializeSeq = ser::Impossible<String, Error>;
    type SerializeTuple = ser::Impossible<String, Error>;
    type SerializeTupleStruct = ser::Impossible<String, Error>;
    type SerializeTupleVariant = ser::Impossible<String, Error>;
    type SerializeMap = ser::Impossible<String, Error>;
    type SerializeStruct = ser::Impossible<String, Error>;
    type SerializeStructVariant = ser::Impossible<String, Error>;

    #[inline]
    fn serialize_unit_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
    ) -> Result<String> {
        Ok(variant.to_owned())
    }

    #[inline]
    fn serialize_newtype_struct<T>(self, _name: &'static str, value: &T) -> Result<String>
    where
        T: ?Sized + Serialize,
    {
        value.serialize(self)
    }

    fn serialize_bool(self, _value: bool) -> Result<String> {
        Err(key_must_be_a_string())
    }

    fn serialize_i8(self, value: i8) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_i16(self, value: i16) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_i32(self, value: i32) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_i64(self, value: i64) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_i128(self, value: i128) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_u8(self, value: u8) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_u16(self, value: u16) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_u32(self, value: u32) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_u64(self, value: u64) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_u128(self, value: u128) -> Result<String> {
        Ok(value.to_string())
    }

    fn serialize_f32(self, _value: f32) -> Result<String> {
        Err(key_must_be_a_string())
    }

    fn serialize_f64(self, _value: f64) -> Result<String> {
        Err(key_must_be_a_string())
    }

    fn serialize_char(self, value: char) -> Result<String> {
        Ok({
            let mut s = String::new();
            s.push(value);
            s
        })
    }

    #[inline]
    fn serialize_str(self, value: &str) -> Result<String> {
        Ok(value.to_owned())
    }

    fn serialize_bytes(self, _value: &[u8]) -> Result<String> {
        Err(key_must_be_a_string())
    }

    fn serialize_unit(self) -> Result<String> {
        Err(key_must_be_a_string())
    }

    fn serialize_unit_struct(self, _name: &'static str) -> Result<String> {
        Err(key_must_be_a_string())
    }

    fn serialize_newtype_variant<T>(
        self,
        _name: &'static str,
        _variant_index: u32,
        _variant: &'static str,
        _value: &T,
    ) -> Result<String>
    where
        T: ?Sized + Serialize,
    {
        Err(key_must_be_a_string())
    }

    fn serialize_none(self) -> Result<String> {
        Err(key_must_be_a_string())
    }

    fn serialize_some<T>(self, _value: &T) -> Result<String>
    where
        T: ?Sized + Serialize,
    {
        Err(key_must_be_a_string())
    }

    fn serialize_seq(self, _len: Option<usize>) -> Result<Self::SerializeSeq> {
        Err(key_must_be_a_string())
    }

    fn serialize_tuple(self, _len: usize) -> Result<Self::SerializeTuple> {
        Err(key_must_be_a_string())
    }

    fn serialize_tuple_struct(
        self,
        _name: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeTupleStruct> {
        Err(key_must_be_a_string())
    }

    fn serialize_tuple_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        _variant: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeTupleVariant> {
        Err(key_must_be_a_string())
    }

    fn serialize_map(self, _len: Option<usize>) -> Result<Self::SerializeMap> {
        Err(key_must_be_a_string())
    }

    fn serialize_struct(self, _name: &'static str, _len: usize) -> Result<Self::SerializeStruct> {
        Err(key_must_be_a_string())
    }

    fn serialize_struct_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        _variant: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeStructVariant> {
        Err(key_must_be_a_string())
    }
}

#[cfg(feature = "arbitrary_precision")]
struct NumberValueEmitter;

#[cfg(feature = "arbitrary_precision")]
impl serde_core::Serializer for NumberValueEmitter {
    type Ok = Value;
    type Error = Error;

    type SerializeSeq = ser::Impossible<Value, Error>;
    type SerializeTuple = ser::Impossible<Value, Error>;
    type SerializeTupleStruct = ser::Impossible<Value, Error>;
    type SerializeTupleVariant = ser::Impossible<Value, Error>;
    type SerializeMap = ser::Impossible<Value, Error>;
    type SerializeStruct = ser::Impossible<Value, Error>;
    type SerializeStructVariant = ser::Impossible<Value, Error>;

    fn serialize_str(self, value: &str) -> Result<Value> {
        let n = value.parse::<crate::number::Number>()
            .map_err(|_| Error::syntax(ErrorCode::Message("invalid number string".into()), 0, 0))?;
        Ok(Value::Number(n))
    }

    fn serialize_bool(self, _: bool) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_i8(self, _: i8) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_i16(self, _: i16) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_i32(self, _: i32) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_i64(self, _: i64) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_u8(self, _: u8) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_u16(self, _: u16) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_u32(self, _: u32) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_u64(self, _: u64) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_f32(self, _: f32) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_f64(self, _: f64) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_char(self, _: char) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_bytes(self, _: &[u8]) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_unit(self) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_unit_struct(self, _: &'static str) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_unit_variant(self, _: &'static str, _: u32, _: &'static str) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_newtype_struct<T: ?Sized + Serialize>(self, _: &'static str, _: &T) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_newtype_variant<T: ?Sized + Serialize>(self, _: &'static str, _: u32, _: &'static str, _: &T) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_none(self) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_some<T: ?Sized + Serialize>(self, _: &T) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_seq(self, _: Option<usize>) -> Result<Self::SerializeSeq> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_tuple(self, _: usize) -> Result<Self::SerializeTuple> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_tuple_struct(self, _: &'static str, _: usize) -> Result<Self::SerializeTupleStruct> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_tuple_variant(self, _: &'static str, _: u32, _: &'static str, _: usize) -> Result<Self::SerializeTupleVariant> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_map(self, _: Option<usize>) -> Result<Self::SerializeMap> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_struct(self, _: &'static str, _: usize) -> Result<Self::SerializeStruct> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_struct_variant(self, _: &'static str, _: u32, _: &'static str, _: usize) -> Result<Self::SerializeStructVariant> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
}

#[cfg(feature = "raw_value")]
struct RawValueEmitter;

#[cfg(feature = "raw_value")]
impl serde_core::Serializer for RawValueEmitter {
    type Ok = Value;
    type Error = Error;

    type SerializeSeq = ser::Impossible<Value, Error>;
    type SerializeTuple = ser::Impossible<Value, Error>;
    type SerializeTupleStruct = ser::Impossible<Value, Error>;
    type SerializeTupleVariant = ser::Impossible<Value, Error>;
    type SerializeMap = ser::Impossible<Value, Error>;
    type SerializeStruct = ser::Impossible<Value, Error>;
    type SerializeStructVariant = ser::Impossible<Value, Error>;

    fn serialize_str(self, value: &str) -> Result<Value> {
        crate::from_str(value)
    }

    fn serialize_bool(self, _: bool) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_i8(self, _: i8) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_i16(self, _: i16) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_i32(self, _: i32) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_i64(self, _: i64) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_u8(self, _: u8) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_u16(self, _: u16) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_u32(self, _: u32) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_u64(self, _: u64) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_f32(self, _: f32) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_f64(self, _: f64) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_char(self, _: char) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_bytes(self, _: &[u8]) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_unit(self) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_unit_struct(self, _: &'static str) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_unit_variant(self, _: &'static str, _: u32, _: &'static str) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_newtype_struct<T: ?Sized + Serialize>(self, _: &'static str, _: &T) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_newtype_variant<T: ?Sized + Serialize>(self, _: &'static str, _: u32, _: &'static str, _: &T) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_none(self) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_some<T: ?Sized + Serialize>(self, _: &T) -> Result<Value> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_seq(self, _: Option<usize>) -> Result<Self::SerializeSeq> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_tuple(self, _: usize) -> Result<Self::SerializeTuple> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_tuple_struct(self, _: &'static str, _: usize) -> Result<Self::SerializeTupleStruct> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_tuple_variant(self, _: &'static str, _: u32, _: &'static str, _: usize) -> Result<Self::SerializeTupleVariant> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_map(self, _: Option<usize>) -> Result<Self::SerializeMap> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_struct(self, _: &'static str, _: usize) -> Result<Self::SerializeStruct> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
    fn serialize_struct_variant(self, _: &'static str, _: u32, _: &'static str, _: usize) -> Result<Self::SerializeStructVariant> { Err(Error::syntax(ErrorCode::Message("expected str".into()), 0, 0)) }
}
