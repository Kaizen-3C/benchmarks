use super::Value;
use crate::map::Map;
use crate::number::Number;

impl From<()> for Value {
    fn from(_: ()) -> Self {
        Value::Null
    }
}

impl From<bool> for Value {
    fn from(b: bool) -> Self {
        Value::Bool(b)
    }
}

impl From<i8> for Value {
    fn from(n: i8) -> Self {
        Value::Number(Number::from(n))
    }
}

impl From<i16> for Value {
    fn from(n: i16) -> Self {
        Value::Number(Number::from(n))
    }
}

impl From<i32> for Value {
    fn from(n: i32) -> Self {
        Value::Number(Number::from(n))
    }
}

impl From<i64> for Value {
    fn from(n: i64) -> Self {
        Value::Number(Number::from(n))
    }
}

impl From<isize> for Value {
    fn from(n: isize) -> Self {
        Value::Number(Number::from(n))
    }
}

impl From<u8> for Value {
    fn from(n: u8) -> Self {
        Value::Number(Number::from(n))
    }
}

impl From<u16> for Value {
    fn from(n: u16) -> Self {
        Value::Number(Number::from(n))
    }
}

impl From<u32> for Value {
    fn from(n: u32) -> Self {
        Value::Number(Number::from(n))
    }
}

impl From<u64> for Value {
    fn from(n: u64) -> Self {
        Value::Number(Number::from(n))
    }
}

impl From<usize> for Value {
    fn from(n: usize) -> Self {
        Value::Number(Number::from(n))
    }
}

impl From<f32> for Value {
    fn from(f: f32) -> Self {
        Number::from_f64(f as f64)
            .map(Value::Number)
            .unwrap_or(Value::Null)
    }
}

impl From<f64> for Value {
    fn from(f: f64) -> Self {
        Number::from_f64(f)
            .map(Value::Number)
            .unwrap_or(Value::Null)
    }
}

impl From<Number> for Value {
    fn from(n: Number) -> Self {
        Value::Number(n)
    }
}

impl From<alloc::string::String> for Value {
    fn from(s: alloc::string::String) -> Self {
        Value::String(s)
    }
}

impl<'a> From<&'a str> for Value {
    fn from(s: &'a str) -> Self {
        Value::String(alloc::string::String::from(s))
    }
}

impl<'a> From<alloc::borrow::Cow<'a, str>> for Value {
    fn from(s: alloc::borrow::Cow<'a, str>) -> Self {
        Value::String(s.into_owned())
    }
}

impl From<Map<alloc::string::String, Value>> for Value {
    fn from(m: Map<alloc::string::String, Value>) -> Self {
        Value::Object(m)
    }
}

impl<T: Into<Value>> From<alloc::vec::Vec<T>> for Value {
    fn from(v: alloc::vec::Vec<T>) -> Self {
        Value::Array(v.into_iter().map(Into::into).collect())
    }
}

impl<'a, T: Clone + Into<Value>> From<&'a [T]> for Value {
    fn from(s: &'a [T]) -> Self {
        Value::Array(s.iter().cloned().map(Into::into).collect())
    }
}

impl<T: Into<Value>> FromIterator<T> for Value {
    fn from_iter<I: IntoIterator<Item = T>>(iter: I) -> Self {
        Value::Array(iter.into_iter().map(Into::into).collect())
    }
}

impl<K: Into<alloc::string::String>, V: Into<Value>> FromIterator<(K, V)> for Value {
    fn from_iter<I: IntoIterator<Item = (K, V)>>(iter: I) -> Self {
        Value::Object(
            iter.into_iter()
                .map(|(k, v)| (k.into(), v.into()))
                .collect(),
        )
    }
}

impl From<Option<Value>> for Value {
    fn from(opt: Option<Value>) -> Self {
        match opt {
            Some(v) => v,
            None => Value::Null,
        }
    }
}
