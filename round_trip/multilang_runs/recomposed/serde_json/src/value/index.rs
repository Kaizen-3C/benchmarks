use super::Value;
use crate::map::Map;

use core::fmt;
use core::ops;

/// A type that can be used to index into a `serde_json::Value`.
///
/// The [`get`] and [`get_mut`] methods of `Value` accept any type that
/// implements `Index`, as does the [square-bracket indexing operator]. This
/// trait is implemented for strings which are used as the index into a JSON
/// map, and for `usize` which is used as the index into a JSON array.
///
/// [`get`]: Value::get
/// [`get_mut`]: Value::get_mut
/// [square-bracket indexing operator]: Value#impl-Index<I>
pub trait Index: private::Sealed {
    /// Return None if the key is not already in the array or object.
    #[doc(hidden)]
    fn index_into<'v>(&self, v: &'v Value) -> Option<&'v Value>;

    /// Return None if the key is not already in the array or object.
    #[doc(hidden)]
    fn index_into_mut<'v>(&self, v: &'v mut Value) -> Option<&'v mut Value>;

    /// Panic if array index out of bounds. If key is not in the object,
    /// insert it with a null value. Panic if `v` is neither an array nor
    /// an object.
    #[doc(hidden)]
    fn index_or_insert<'v>(&self, v: &'v mut Value) -> &'v mut Value;
}

impl Index for usize {
    fn index_into<'v>(&self, v: &'v Value) -> Option<&'v Value> {
        match v {
            Value::Array(vec) => vec.get(*self),
            _ => None,
        }
    }

    fn index_into_mut<'v>(&self, v: &'v mut Value) -> Option<&'v mut Value> {
        match v {
            Value::Array(vec) => vec.get_mut(*self),
            _ => None,
        }
    }

    fn index_or_insert<'v>(&self, v: &'v mut Value) -> &'v mut Value {
        match v {
            Value::Array(vec) => {
                let len = vec.len();
                vec.get_mut(*self).unwrap_or_else(|| {
                    panic!(
                        "cannot access index {} of JSON array of length {}",
                        self, len
                    )
                })
            }
            _ => panic!("cannot index into a non-array JSON value with a usize"),
        }
    }
}

impl Index for str {
    fn index_into<'v>(&self, v: &'v Value) -> Option<&'v Value> {
        match v {
            Value::Object(map) => map.get(self),
            _ => None,
        }
    }

    fn index_into_mut<'v>(&self, v: &'v mut Value) -> Option<&'v mut Value> {
        match v {
            Value::Object(map) => map.get_mut(self),
            _ => None,
        }
    }

    fn index_or_insert<'v>(&self, v: &'v mut Value) -> &'v mut Value {
        match v {
            Value::Object(map) => map
                .entry(self.to_owned())
                .or_insert(Value::Null),
            _ => panic!("cannot index into a non-object JSON value with a string key"),
        }
    }
}

impl Index for String {
    fn index_into<'v>(&self, v: &'v Value) -> Option<&'v Value> {
        self[..].index_into(v)
    }

    fn index_into_mut<'v>(&self, v: &'v mut Value) -> Option<&'v mut Value> {
        self[..].index_into_mut(v)
    }

    fn index_or_insert<'v>(&self, v: &'v mut Value) -> &'v mut Value {
        self[..].index_or_insert(v)
    }
}

impl<'a, T> Index for &'a T
where
    T: ?Sized + Index,
{
    fn index_into<'v>(&self, v: &'v Value) -> Option<&'v Value> {
        (**self).index_into(v)
    }

    fn index_into_mut<'v>(&self, v: &'v mut Value) -> Option<&'v mut Value> {
        (**self).index_into_mut(v)
    }

    fn index_or_insert<'v>(&self, v: &'v mut Value) -> &'v mut Value {
        (**self).index_or_insert(v)
    }
}

mod private {
    pub trait Sealed {}
    impl Sealed for usize {}
    impl Sealed for str {}
    impl Sealed for String {}
    impl<'a, T: ?Sized + Sealed> Sealed for &'a T {}
}

/// Used in panic messages when indexing fails.
struct Type<'a>(&'a Value);

impl<'a> fmt::Display for Type<'a> {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self.0 {
            Value::Null => f.write_str("null"),
            Value::Bool(_) => f.write_str("boolean"),
            Value::Number(_) => f.write_str("number"),
            Value::String(_) => f.write_str("string"),
            Value::Array(_) => f.write_str("array"),
            Value::Object(_) => f.write_str("object"),
        }
    }
}

impl<I: Index> ops::Index<I> for Value {
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

impl<I: Index> ops::IndexMut<I> for Value {
    /// Write into a `serde_json::Value` using the syntax `value[0] = ...` or
    /// `value["k"] = ...`.
    ///
    /// If the index is a number, the value must be an array of length bigger
    /// than the index. Indexing into a value that is not an array or an array
    /// that is too small will panic.
    ///
    /// If the index is a string, the value must be an object or null which is
    /// treated like an empty object. If the key is not already present in the
    /// object, it will be inserted with a value of null. Indexing into a value
    /// that is neither an object nor null will panic.
    fn index_mut(&mut self, index: I) -> &mut Value {
        index.index_or_insert(self)
    }
}
