#![deny(clippy::all)]

pub mod de;
pub mod error;
pub mod map;
pub mod ser;
pub mod value;

mod io;
#[cfg(feature = "std")]
mod iter;
#[cfg(feature = "float_roundtrip")]
mod lexical;
mod macros;
mod number;
#[cfg(feature = "raw_value")]
mod raw;
mod read;

pub use crate::de::from_slice;
pub use crate::de::from_str;
pub use crate::de::Deserializer;
pub use crate::de::StreamDeserializer;
pub use crate::error::Error;
pub use crate::error::Result;
pub use crate::ser::to_string;
pub use crate::ser::to_string_pretty;
pub use crate::ser::to_vec;
pub use crate::ser::to_vec_pretty;
pub use crate::ser::Serializer;
pub use crate::value::from_value;
pub use crate::value::to_value;
pub use crate::value::Map;
pub use crate::value::Number;
pub use crate::value::Value;

#[cfg(feature = "std")]
pub use crate::de::from_reader;
#[cfg(feature = "std")]
pub use crate::ser::to_writer;
#[cfg(feature = "std")]
pub use crate::ser::to_writer_pretty;
