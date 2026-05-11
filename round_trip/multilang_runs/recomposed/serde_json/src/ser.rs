use crate::error::{Error, ErrorCode, Result};
use crate::io;

use alloc::string::String;
use alloc::vec::Vec;
use core::fmt::{self, Display};
use core::num::FpCategory;

use serde_core::ser::{self, Serialize};

/// Serializes `value` to a writer using compact JSON formatting.
#[cfg(feature = "std")]
pub fn to_writer<W: io::Write, T: Serialize + ?Sized>(writer: W, value: &T) -> Result<()> {
    let mut ser = Serializer::new(writer);
    value.serialize(&mut ser)
}

/// Serializes `value` to a writer using pretty-printed JSON formatting.
#[cfg(feature = "std")]
pub fn to_writer_pretty<W: io::Write, T: Serialize + ?Sized>(writer: W, value: &T) -> Result<()> {
    let mut ser = Serializer::pretty(writer);
    value.serialize(&mut ser)
}

/// Serializes `value` to a `Vec<u8>` using compact JSON formatting.
pub fn to_vec<T: Serialize + ?Sized>(value: &T) -> Result<Vec<u8>> {
    let mut writer = Vec::with_capacity(128);
    let mut ser = Serializer::new(&mut writer);
    value.serialize(&mut ser)?;
    Ok(writer)
}

/// Serializes `value` to a `Vec<u8>` using pretty-printed JSON formatting.
pub fn to_vec_pretty<T: Serialize + ?Sized>(value: &T) -> Result<Vec<u8>> {
    let mut writer = Vec::with_capacity(128);
    let mut ser = Serializer::pretty(&mut writer);
    value.serialize(&mut ser)?;
    Ok(writer)
}

/// Serializes `value` to a `String` using compact JSON formatting.
pub fn to_string<T: Serialize + ?Sized>(value: &T) -> Result<String> {
    let vec = to_vec(value)?;
    // SAFETY: JSON output is always valid UTF-8
    let string = unsafe { String::from_utf8_unchecked(vec) };
    Ok(string)
}

/// Serializes `value` to a `String` using pretty-printed JSON formatting.
pub fn to_string_pretty<T: Serialize + ?Sized>(value: &T) -> Result<String> {
    let vec = to_vec_pretty(value)?;
    // SAFETY: JSON output is always valid UTF-8
    let string = unsafe { String::from_utf8_unchecked(vec) };
    Ok(string)
}

/// Trait for controlling JSON output formatting.
pub trait Formatter {
    /// Writes a JSON null value.
    fn write_null<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        writer.write_all(b"null")
    }

    /// Writes a JSON boolean value.
    fn write_bool<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: bool) -> io::Result<()> {
        let s = if value { b"true" as &[u8] } else { b"false" as &[u8] };
        writer.write_all(s)
    }

    fn write_i8<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: i8) -> io::Result<()> {
        let mut buf = itoa::Buffer::new();
        writer.write_all(buf.format(value).as_bytes())
    }

    fn write_i16<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: i16) -> io::Result<()> {
        let mut buf = itoa::Buffer::new();
        writer.write_all(buf.format(value).as_bytes())
    }

    fn write_i32<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: i32) -> io::Result<()> {
        let mut buf = itoa::Buffer::new();
        writer.write_all(buf.format(value).as_bytes())
    }

    fn write_i64<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: i64) -> io::Result<()> {
        let mut buf = itoa::Buffer::new();
        writer.write_all(buf.format(value).as_bytes())
    }

    fn write_i128<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: i128) -> io::Result<()> {
        let mut buf = itoa::Buffer::new();
        writer.write_all(buf.format(value).as_bytes())
    }

    fn write_u8<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: u8) -> io::Result<()> {
        let mut buf = itoa::Buffer::new();
        writer.write_all(buf.format(value).as_bytes())
    }

    fn write_u16<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: u16) -> io::Result<()> {
        let mut buf = itoa::Buffer::new();
        writer.write_all(buf.format(value).as_bytes())
    }

    fn write_u32<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: u32) -> io::Result<()> {
        let mut buf = itoa::Buffer::new();
        writer.write_all(buf.format(value).as_bytes())
    }

    fn write_u64<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: u64) -> io::Result<()> {
        let mut buf = itoa::Buffer::new();
        writer.write_all(buf.format(value).as_bytes())
    }

    fn write_u128<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: u128) -> io::Result<()> {
        let mut buf = itoa::Buffer::new();
        writer.write_all(buf.format(value).as_bytes())
    }

    fn write_f32<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: f32) -> io::Result<()> {
        match value.classify() {
            FpCategory::Nan | FpCategory::Infinite => writer.write_all(b"null"),
            _ => {
                let s = format_float_f32(value);
                writer.write_all(s.as_bytes())
            }
        }
    }

    fn write_f64<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: f64) -> io::Result<()> {
        match value.classify() {
            FpCategory::Nan | FpCategory::Infinite => writer.write_all(b"null"),
            _ => {
                let s = format_float_f64(value);
                writer.write_all(s.as_bytes())
            }
        }
    }

    fn write_number_str<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: &str) -> io::Result<()> {
        writer.write_all(value.as_bytes())
    }

    fn begin_string<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        writer.write_all(b"\"")
    }

    fn end_string<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        writer.write_all(b"\"")
    }

    fn write_string_fragment<W: io::Write + ?Sized>(&mut self, writer: &mut W, fragment: &str) -> io::Result<()> {
        writer.write_all(fragment.as_bytes())
    }

    fn write_char_escape<W: io::Write + ?Sized>(&mut self, writer: &mut W, char_escape: CharEscape) -> io::Result<()> {
        use self::CharEscape::*;
        let s = match char_escape {
            Quote => b"\\\"" as &[u8],
            ReverseSolidus => b"\\\\",
            Solidus => b"\\/",
            Backspace => b"\\b",
            FormFeed => b"\\f",
            LineFeed => b"\\n",
            CarriageReturn => b"\\r",
            Tab => b"\\t",
            AsciiControl(byte) => {
                static HEX_DIGITS: &[u8] = b"0123456789abcdef";
                let bytes = [
                    b'\\',
                    b'u',
                    b'0',
                    b'0',
                    HEX_DIGITS[(byte >> 4) as usize],
                    HEX_DIGITS[(byte & 0xf) as usize],
                ];
                return writer.write_all(&bytes);
            }
        };
        writer.write_all(s)
    }

    fn begin_array<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        writer.write_all(b"[")
    }

    fn end_array<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        writer.write_all(b"]")
    }

    fn begin_array_value<W: io::Write + ?Sized>(&mut self, writer: &mut W, first: bool) -> io::Result<()> {
        if !first {
            writer.write_all(b",")?;
        }
        Ok(())
    }

    fn end_array_value<W: io::Write + ?Sized>(&mut self, _writer: &mut W) -> io::Result<()> {
        Ok(())
    }

    fn begin_object<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        writer.write_all(b"{")
    }

    fn end_object<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        writer.write_all(b"}")
    }

    fn begin_object_key<W: io::Write + ?Sized>(&mut self, writer: &mut W, first: bool) -> io::Result<()> {
        if !first {
            writer.write_all(b",")?;
        }
        Ok(())
    }

    fn end_object_key<W: io::Write + ?Sized>(&mut self, _writer: &mut W) -> io::Result<()> {
        Ok(())
    }

    fn begin_object_value<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        writer.write_all(b":")
    }

    fn end_object_value<W: io::Write + ?Sized>(&mut self, _writer: &mut W) -> io::Result<()> {
        Ok(())
    }

    fn write_byte_array<W: io::Write + ?Sized>(&mut self, writer: &mut W, value: &[u8]) -> io::Result<()> {
        self.begin_array(writer)?;
        let mut first = true;
        for byte in value {
            self.begin_array_value(writer, first)?;
            self.write_u8(writer, *byte)?;
            self.end_array_value(writer)?;
            first = false;
        }
        self.end_array(writer)
    }
}

/// Escape sequences for characters in JSON strings.
#[derive(Copy, Clone)]
pub enum CharEscape {
    /// `\"` — double quote
    Quote,
    /// `\\` — backslash
    ReverseSolidus,
    /// `\/` — forward slash (optional)
    Solidus,
    /// `\b` — backspace
    Backspace,
    /// `\f` — form feed
    FormFeed,
    /// `\n` — line feed
    LineFeed,
    /// `\r` — carriage return
    CarriageReturn,
    /// `\t` — tab
    Tab,
    /// `\uXXXX` — ASCII control character (0x00–0x1f, 0x7f excluded above)
    AsciiControl(u8),
}

impl CharEscape {
    fn from_byte(byte: u8) -> CharEscape {
        match byte {
            0x08 => CharEscape::Backspace,
            0x09 => CharEscape::Tab,
            0x0a => CharEscape::LineFeed,
            0x0c => CharEscape::FormFeed,
            0x0d => CharEscape::CarriageReturn,
            0x22 => CharEscape::Quote,
            0x5c => CharEscape::ReverseSolidus,
            b => CharEscape::AsciiControl(b),
        }
    }
}

/// Compact (minified) JSON formatter.
#[derive(Clone, Debug)]
pub struct CompactFormatter;

impl Formatter for CompactFormatter {}

/// Pretty-printed JSON formatter with configurable indentation.
pub struct PrettyFormatter<'a> {
    current_indent: usize,
    has_value: bool,
    indent: &'a [u8],
}

impl<'a> PrettyFormatter<'a> {
    /// Creates a new `PrettyFormatter` using 2-space indentation.
    pub fn new() -> Self {
        PrettyFormatter::with_indent(b"  ")
    }

    /// Creates a new `PrettyFormatter` with the given indentation bytes.
    pub fn with_indent(indent: &'a [u8]) -> Self {
        PrettyFormatter {
            current_indent: 0,
            has_value: false,
            indent,
        }
    }
}

impl<'a> Default for PrettyFormatter<'a> {
    fn default() -> Self {
        PrettyFormatter::new()
    }
}

impl<'a> Formatter for PrettyFormatter<'a> {
    fn begin_array<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        self.current_indent += 1;
        self.has_value = false;
        writer.write_all(b"[")
    }

    fn end_array<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        self.current_indent -= 1;
        if self.has_value {
            writer.write_all(b"\n")?;
            indent(writer, self.current_indent, self.indent)?;
        }
        writer.write_all(b"]")
    }

    fn begin_array_value<W: io::Write + ?Sized>(&mut self, writer: &mut W, first: bool) -> io::Result<()> {
        if first {
            writer.write_all(b"\n")?;
        } else {
            writer.write_all(b",\n")?;
        }
        indent(writer, self.current_indent, self.indent)
    }

    fn end_array_value<W: io::Write + ?Sized>(&mut self, _writer: &mut W) -> io::Result<()> {
        self.has_value = true;
        Ok(())
    }

    fn begin_object<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        self.current_indent += 1;
        self.has_value = false;
        writer.write_all(b"{")
    }

    fn end_object<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        self.current_indent -= 1;
        if self.has_value {
            writer.write_all(b"\n")?;
            indent(writer, self.current_indent, self.indent)?;
        }
        writer.write_all(b"}")
    }

    fn begin_object_key<W: io::Write + ?Sized>(&mut self, writer: &mut W, first: bool) -> io::Result<()> {
        if first {
            writer.write_all(b"\n")?;
        } else {
            writer.write_all(b",\n")?;
        }
        indent(writer, self.current_indent, self.indent)
    }

    fn end_object_key<W: io::Write + ?Sized>(&mut self, _writer: &mut W) -> io::Result<()> {
        Ok(())
    }

    fn begin_object_value<W: io::Write + ?Sized>(&mut self, writer: &mut W) -> io::Result<()> {
        writer.write_all(b": ")
    }

    fn end_object_value<W: io::Write + ?Sized>(&mut self, _writer: &mut W) -> io::Result<()> {
        self.has_value = true;
        Ok(())
    }
}

fn indent<W: io::Write + ?Sized>(writer: &mut W, n: usize, s: &[u8]) -> io::Result<()> {
    for _ in 0..n {
        writer.write_all(s)?;
    }
    Ok(())
}

/// JSON serializer wrapping a writer and formatter.
pub struct Serializer<W, F = CompactFormatter> {
    writer: W,
    formatter: F,
}

impl<W: io::Write> Serializer<W, CompactFormatter> {
    /// Creates a new compact serializer.
    pub fn new(writer: W) -> Self {
        Serializer::with_formatter(writer, CompactFormatter)
    }
}

impl<'a, W: io::Write> Serializer<W, PrettyFormatter<'a>> {
    /// Creates a new pretty-printing serializer.
    pub fn pretty(writer: W) -> Self {
        Serializer::with_formatter(writer, PrettyFormatter::new())
    }
}

impl<W: io::Write, F: Formatter> Serializer<W, F> {
    /// Creates a new serializer with a custom formatter.
    pub fn with_formatter(writer: W, formatter: F) -> Self {
        Serializer { writer, formatter }
    }

    /// Consumes the serializer and returns the underlying writer.
    pub fn into_inner(self) -> W {
        self.writer
    }
}

impl<'a, W: io::Write, F: Formatter> ser::Serializer for &'a mut Serializer<W, F> {
    type Ok = ();
    type Error = Error;

    type SerializeSeq = Compound<'a, W, F>;
    type SerializeTuple = Compound<'a, W, F>;
    type SerializeTupleStruct = Compound<'a, W, F>;
    type SerializeTupleVariant = Compound<'a, W, F>;
    type SerializeMap = Compound<'a, W, F>;
    type SerializeStruct = Compound<'a, W, F>;
    type SerializeStructVariant = Compound<'a, W, F>;

    fn serialize_bool(self, v: bool) -> Result<()> {
        self.formatter
            .write_bool(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_i8(self, v: i8) -> Result<()> {
        self.formatter
            .write_i8(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_i16(self, v: i16) -> Result<()> {
        self.formatter
            .write_i16(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_i32(self, v: i32) -> Result<()> {
        self.formatter
            .write_i32(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_i64(self, v: i64) -> Result<()> {
        self.formatter
            .write_i64(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_i128(self, v: i128) -> Result<()> {
        self.formatter
            .write_i128(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_u8(self, v: u8) -> Result<()> {
        self.formatter
            .write_u8(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_u16(self, v: u16) -> Result<()> {
        self.formatter
            .write_u16(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_u32(self, v: u32) -> Result<()> {
        self.formatter
            .write_u32(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_u64(self, v: u64) -> Result<()> {
        self.formatter
            .write_u64(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_u128(self, v: u128) -> Result<()> {
        self.formatter
            .write_u128(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_f32(self, v: f32) -> Result<()> {
        self.formatter
            .write_f32(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_f64(self, v: f64) -> Result<()> {
        self.formatter
            .write_f64(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_char(self, v: char) -> Result<()> {
        // A single character is serialized as a JSON string
        let mut buf = [0u8; 4];
        let s = v.encode_utf8(&mut buf);
        self.serialize_str(s)
    }

    fn serialize_str(self, v: &str) -> Result<()> {
        format_escaped_str(&mut self.writer, &mut self.formatter, v).map_err(Error::io)
    }

    fn serialize_bytes(self, v: &[u8]) -> Result<()> {
        self.formatter
            .write_byte_array(&mut self.writer, v)
            .map_err(Error::io)
    }

    fn serialize_none(self) -> Result<()> {
        self.serialize_unit()
    }

    fn serialize_some<T: Serialize + ?Sized>(self, value: &T) -> Result<()> {
        value.serialize(self)
    }

    fn serialize_unit(self) -> Result<()> {
        self.formatter
            .write_null(&mut self.writer)
            .map_err(Error::io)
    }

    fn serialize_unit_struct(self, _name: &'static str) -> Result<()> {
        self.serialize_unit()
    }

    fn serialize_unit_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
    ) -> Result<()> {
        self.serialize_str(variant)
    }

    fn serialize_newtype_struct<T: Serialize + ?Sized>(
        self,
        name: &'static str,
        value: &T,
    ) -> Result<()> {
        #[cfg(feature = "arbitrary_precision")]
        if name == crate::number::TOKEN {
            use ser::SerializeMap;
            let mut map = self.serialize_map(Some(1))?;
            map.serialize_entry(crate::number::TOKEN, value)?;
            return map.end();
        }
        #[cfg(feature = "raw_value")]
        if name == crate::raw::TOKEN {
            use self::ser::SerializeMap;
            let mut map = self.serialize_map(Some(1))?;
            map.serialize_entry(crate::raw::TOKEN, value)?;
            return map.end();
        }
        let _ = name;
        value.serialize(self)
    }

    fn serialize_newtype_variant<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
        value: &T,
    ) -> Result<()> {
        self.formatter
            .begin_object(&mut self.writer)
            .map_err(Error::io)?;
        self.formatter
            .begin_object_key(&mut self.writer, true)
            .map_err(Error::io)?;
        self.serialize_str(variant)?;
        self.formatter
            .end_object_key(&mut self.writer)
            .map_err(Error::io)?;
        self.formatter
            .begin_object_value(&mut self.writer)
            .map_err(Error::io)?;
        value.serialize(&mut *self)?;
        self.formatter
            .end_object_value(&mut self.writer)
            .map_err(Error::io)?;
        self.formatter
            .end_object(&mut self.writer)
            .map_err(Error::io)
    }

    fn serialize_seq(self, _len: Option<usize>) -> Result<Self::SerializeSeq> {
        self.formatter
            .begin_array(&mut self.writer)
            .map_err(Error::io)?;
        Ok(Compound {
            ser: self,
            state: State::First,
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
        _len: usize,
    ) -> Result<Self::SerializeTupleVariant> {
        self.formatter
            .begin_object(&mut self.writer)
            .map_err(Error::io)?;
        self.formatter
            .begin_object_key(&mut self.writer, true)
            .map_err(Error::io)?;
        self.serialize_str(variant)?;
        self.formatter
            .end_object_key(&mut self.writer)
            .map_err(Error::io)?;
        self.formatter
            .begin_object_value(&mut self.writer)
            .map_err(Error::io)?;
        self.formatter
            .begin_array(&mut self.writer)
            .map_err(Error::io)?;
        Ok(Compound {
            ser: self,
            state: State::TupleVariant,
        })
    }

    fn serialize_map(self, _len: Option<usize>) -> Result<Self::SerializeMap> {
        self.formatter
            .begin_object(&mut self.writer)
            .map_err(Error::io)?;
        Ok(Compound {
            ser: self,
            state: State::First,
        })
    }

    fn serialize_struct(self, name: &'static str, len: usize) -> Result<Self::SerializeStruct> {
        match name {
            #[cfg(feature = "arbitrary_precision")]
            crate::number::TOKEN => Ok(Compound {
                ser: self,
                state: State::First,
            }),
            #[cfg(feature = "raw_value")]
            crate::raw::TOKEN => Ok(Compound {
                ser: self,
                state: State::First,
            }),
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
        self.formatter
            .begin_object(&mut self.writer)
            .map_err(Error::io)?;
        self.formatter
            .begin_object_key(&mut self.writer, true)
            .map_err(Error::io)?;
        self.serialize_str(variant)?;
        self.formatter
            .end_object_key(&mut self.writer)
            .map_err(Error::io)?;
        self.formatter
            .begin_object_value(&mut self.writer)
            .map_err(Error::io)?;
        self.formatter
            .begin_object(&mut self.writer)
            .map_err(Error::io)?;
        Ok(Compound {
            ser: self,
            state: State::StructVariant,
        })
    }

    fn collect_str<T: Display + ?Sized>(self, value: &T) -> Result<()> {
        use core::fmt::Write;
        let mut adapter = WriterFormatter {
            writer: &mut self.writer,
            formatter: &mut self.formatter,
            error: None,
        };
        adapter.formatter.begin_string(adapter.writer).map_err(Error::io)?;
        if let Err(e) = write!(adapter, "{}", value) {
            if let Some(io_err) = adapter.error {
                return Err(Error::io(io_err));
            }
            return Err(Error::syntax(ErrorCode::Message(e.to_string().into()), 0, 0));
        }
        adapter.formatter.end_string(adapter.writer).map_err(Error::io)
    }
}

struct WriterFormatter<'a, W: 'a, F: 'a> {
    writer: &'a mut W,
    formatter: &'a mut F,
    error: Option<io::Error>,
}

impl<'a, W: io::Write, F: Formatter> fmt::Write for WriterFormatter<'a, W, F> {
    fn write_str(&mut self, s: &str) -> fmt::Result {
        match format_escaped_str_contents(self.writer, self.formatter, s) {
            Ok(()) => Ok(()),
            Err(e) => {
                self.error = Some(e);
                Err(fmt::Error)
            }
        }
    }
}

#[derive(PartialEq)]
enum State {
    First,
    Rest,
    TupleVariant,
    StructVariant,
}

/// Serialization compound (sequence/map in progress).
pub struct Compound<'a, W: 'a, F: 'a> {
    ser: &'a mut Serializer<W, F>,
    state: State,
}

impl<'a, W: io::Write, F: Formatter> ser::SerializeSeq for Compound<'a, W, F> {
    type Ok = ();
    type Error = Error;

    fn serialize_element<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
        self.ser
            .formatter
            .begin_array_value(&mut self.ser.writer, self.state == State::First)
            .map_err(Error::io)?;
        self.state = State::Rest;
        value.serialize(&mut *self.ser)?;
        self.ser
            .formatter
            .end_array_value(&mut self.ser.writer)
            .map_err(Error::io)
    }

    fn end(self) -> Result<()> {
        match self.state {
            State::First => {}
            _ => {
                self.ser
                    .formatter
                    .end_array_value(&mut self.ser.writer)
                    .map_err(Error::io)?;
            }
        }
        self.ser
            .formatter
            .end_array(&mut self.ser.writer)
            .map_err(Error::io)
    }
}

impl<'a, W: io::Write, F: Formatter> ser::SerializeTuple for Compound<'a, W, F> {
    type Ok = ();
    type Error = Error;

    fn serialize_element<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
        ser::SerializeSeq::serialize_element(self, value)
    }

    fn end(self) -> Result<()> {
        ser::SerializeSeq::end(self)
    }
}

impl<'a, W: io::Write, F: Formatter> ser::SerializeTupleStruct for Compound<'a, W, F> {
    type Ok = ();
    type Error = Error;

    fn serialize_field<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
        ser::SerializeSeq::serialize_element(self, value)
    }

    fn end(self) -> Result<()> {
        ser::SerializeSeq::end(self)
    }
}

impl<'a, W: io::Write, F: Formatter> ser::SerializeTupleVariant for Compound<'a, W, F> {
    type Ok = ();
    type Error = Error;

    fn serialize_field<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
        self.ser
            .formatter
            .begin_array_value(&mut self.ser.writer, self.state == State::TupleVariant)
            .map_err(Error::io)?;
        self.state = State::Rest;
        value.serialize(&mut *self.ser)?;
        self.ser
            .formatter
            .end_array_value(&mut self.ser.writer)
            .map_err(Error::io)
    }

    fn end(self) -> Result<()> {
        match self.state {
            State::TupleVariant => {}
            _ => {
                self.ser
                    .formatter
                    .end_array_value(&mut self.ser.writer)
                    .map_err(Error::io)?;
            }
        }
        self.ser
            .formatter
            .end_array(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_object_value(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_object(&mut self.ser.writer)
            .map_err(Error::io)
    }
}

impl<'a, W: io::Write, F: Formatter> ser::SerializeMap for Compound<'a, W, F> {
    type Ok = ();
    type Error = Error;

    fn serialize_key<T: Serialize + ?Sized>(&mut self, key: &T) -> Result<()> {
        self.ser
            .formatter
            .begin_object_key(&mut self.ser.writer, self.state == State::First)
            .map_err(Error::io)?;
        self.state = State::Rest;

        key.serialize(MapKeySerializer { ser: self.ser })?;

        self.ser
            .formatter
            .end_object_key(&mut self.ser.writer)
            .map_err(Error::io)
    }

    fn serialize_value<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
        self.ser
            .formatter
            .begin_object_value(&mut self.ser.writer)
            .map_err(Error::io)?;
        value.serialize(&mut *self.ser)?;
        self.ser
            .formatter
            .end_object_value(&mut self.ser.writer)
            .map_err(Error::io)
    }

    fn end(self) -> Result<()> {
        match self.state {
            State::First => {}
            _ => {
                self.ser
                    .formatter
                    .end_object_value(&mut self.ser.writer)
                    .map_err(Error::io)?;
            }
        }
        self.ser
            .formatter
            .end_object(&mut self.ser.writer)
            .map_err(Error::io)
    }
}

impl<'a, W: io::Write, F: Formatter> ser::SerializeStruct for Compound<'a, W, F> {
    type Ok = ();
    type Error = Error;

    fn serialize_field<T: Serialize + ?Sized>(&mut self, key: &'static str, value: &T) -> Result<()> {
        match self.state {
            #[cfg(feature = "arbitrary_precision")]
            State::First if key == crate::number::TOKEN => {
                // The value is the raw number string
                value.serialize(RawNumberSerializer { ser: self.ser })?;
                self.state = State::Rest;
                return Ok(());
            }
            #[cfg(feature = "raw_value")]
            State::First if key == crate::raw::TOKEN => {
                value.serialize(RawValueStrSerializer { ser: self.ser })?;
                self.state = State::Rest;
                return Ok(());
            }
            _ => {}
        }
        ser::SerializeMap::serialize_key(self, key)?;
        ser::SerializeMap::serialize_value(self, value)
    }

    fn end(self) -> Result<()> {
        match self.state {
            State::Rest => {
                // For arbitrary_precision / raw_value, we don't need to close an object
                #[cfg(any(feature = "arbitrary_precision", feature = "raw_value"))]
                return Ok(());
            }
            _ => {}
        }
        ser::SerializeMap::end(self)
    }
}

impl<'a, W: io::Write, F: Formatter> ser::SerializeStructVariant for Compound<'a, W, F> {
    type Ok = ();
    type Error = Error;

    fn serialize_field<T: Serialize + ?Sized>(&mut self, key: &'static str, value: &T) -> Result<()> {
        self.ser
            .formatter
            .begin_object_key(&mut self.ser.writer, self.state == State::StructVariant)
            .map_err(Error::io)?;
        self.state = State::Rest;

        key.serialize(MapKeySerializer { ser: self.ser })?;

        self.ser
            .formatter
            .end_object_key(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .begin_object_value(&mut self.ser.writer)
            .map_err(Error::io)?;
        value.serialize(&mut *self.ser)?;
        self.ser
            .formatter
            .end_object_value(&mut self.ser.writer)
            .map_err(Error::io)
    }

    fn end(self) -> Result<()> {
        match self.state {
            State::StructVariant => {}
            _ => {
                self.ser
                    .formatter
                    .end_object_value(&mut self.ser.writer)
                    .map_err(Error::io)?;
            }
        }
        self.ser
            .formatter
            .end_object(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_object_value(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_object(&mut self.ser.writer)
            .map_err(Error::io)
    }
}

/// Serializer for map keys (must serialize as strings).
struct MapKeySerializer<'a, W: 'a, F: 'a> {
    ser: &'a mut Serializer<W, F>,
}

fn key_must_be_a_string() -> Error {
    Error::syntax(ErrorCode::KeyMustBeAString, 0, 0)
}

impl<'a, W: io::Write, F: Formatter> ser::Serializer for MapKeySerializer<'a, W, F> {
    type Ok = ();
    type Error = Error;
    type SerializeSeq = ser::Impossible<(), Error>;
    type SerializeTuple = ser::Impossible<(), Error>;
    type SerializeTupleStruct = ser::Impossible<(), Error>;
    type SerializeTupleVariant = ser::Impossible<(), Error>;
    type SerializeMap = ser::Impossible<(), Error>;
    type SerializeStruct = ser::Impossible<(), Error>;
    type SerializeStructVariant = ser::Impossible<(), Error>;

    fn serialize_bool(self, _v: bool) -> Result<()> {
        Err(key_must_be_a_string())
    }
    fn serialize_i8(self, v: i8) -> Result<()> {
        self.ser
            .formatter
            .begin_string(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .write_i8(&mut self.ser.writer, v)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_string(&mut self.ser.writer)
            .map_err(Error::io)
    }
    fn serialize_i16(self, v: i16) -> Result<()> {
        self.ser
            .formatter
            .begin_string(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .write_i16(&mut self.ser.writer, v)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_string(&mut self.ser.writer)
            .map_err(Error::io)
    }
    fn serialize_i32(self, v: i32) -> Result<()> {
        self.ser
            .formatter
            .begin_string(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .write_i32(&mut self.ser.writer, v)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_string(&mut self.ser.writer)
            .map_err(Error::io)
    }
    fn serialize_i64(self, v: i64) -> Result<()> {
        self.ser
            .formatter
            .begin_string(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .write_i64(&mut self.ser.writer, v)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_string(&mut self.ser.writer)
            .map_err(Error::io)
    }
    fn serialize_i128(self, v: i128) -> Result<()> {
        self.ser
            .formatter
            .begin_string(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .write_i128(&mut self.ser.writer, v)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_string(&mut self.ser.writer)
            .map_err(Error::io)
    }
    fn serialize_u8(self, v: u8) -> Result<()> {
        self.ser
            .formatter
            .begin_string(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .write_u8(&mut self.ser.writer, v)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_string(&mut self.ser.writer)
            .map_err(Error::io)
    }
    fn serialize_u16(self, v: u16) -> Result<()> {
        self.ser
            .formatter
            .begin_string(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .write_u16(&mut self.ser.writer, v)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_string(&mut self.ser.writer)
            .map_err(Error::io)
    }
    fn serialize_u32(self, v: u32) -> Result<()> {
        self.ser
            .formatter
            .begin_string(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .write_u32(&mut self.ser.writer, v)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_string(&mut self.ser.writer)
            .map_err(Error::io)
    }
    fn serialize_u64(self, v: u64) -> Result<()> {
        self.ser
            .formatter
            .begin_string(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .write_u64(&mut self.ser.writer, v)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_string(&mut self.ser.writer)
            .map_err(Error::io)
    }
    fn serialize_u128(self, v: u128) -> Result<()> {
        self.ser
            .formatter
            .begin_string(&mut self.ser.writer)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .write_u128(&mut self.ser.writer, v)
            .map_err(Error::io)?;
        self.ser
            .formatter
            .end_string(&mut self.ser.writer)
            .map_err(Error::io)
    }
    fn serialize_f32(self, _v: f32) -> Result<()> {
        Err(key_must_be_a_string())
    }
    fn serialize_f64(self, _v: f64) -> Result<()> {
        Err(key_must_be_a_string())
    }
    fn serialize_char(self, v: char) -> Result<()> {
        let mut s = [0u8; 4];
        let s = v.encode_utf8(&mut s);
        self.serialize_str(s)
    }
    fn serialize_str(self, v: &str) -> Result<()> {
        format_escaped_str(&mut self.ser.writer, &mut self.ser.formatter, v).map_err(Error::io)
    }
    fn serialize_bytes(self, _v: &[u8]) -> Result<()> {
        Err(key_must_be_a_string())
    }
    fn serialize_none(self) -> Result<()> {
        Err(key_must_be_a_string())
    }
    fn serialize_some<T: Serialize + ?Sized>(self, value: &T) -> Result<()> {
        value.serialize(self)
    }
    fn serialize_unit(self) -> Result<()> {
        Err(key_must_be_a_string())
    }
    fn serialize_unit_struct(self, _name: &'static str) -> Result<()> {
        Err(key_must_be_a_string())
    }
    fn serialize_unit_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
    ) -> Result<()> {
        self.serialize_str(variant)
    }
    fn serialize_newtype_struct<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        value: &T,
    ) -> Result<()> {
        value.serialize(self)
    }
    fn serialize_newtype_variant<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        _variant_index: u32,
        _variant: &'static str,
        _value: &T,
    ) -> Result<()> {
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

    fn collect_str<T: Display + ?Sized>(self, value: &T) -> Result<()> {
        self.serialize_str(&alloc::string::ToString::to_string(value))
    }
}

/// Serializer that writes a raw number string directly (for arbitrary_precision).
#[cfg(feature = "arbitrary_precision")]
struct RawNumberSerializer<'a, W: 'a, F: 'a> {
    ser: &'a mut Serializer<W, F>,
}

#[cfg(feature = "arbitrary_precision")]
impl<'a, W: io::Write, F: Formatter> ser::Serializer for RawNumberSerializer<'a, W, F> {
    type Ok = ();
    type Error = Error;
    type SerializeSeq = ser::Impossible<(), Error>;
    type SerializeTuple = ser::Impossible<(), Error>;
    type SerializeTupleStruct = ser::Impossible<(), Error>;
    type SerializeTupleVariant = ser::Impossible<(), Error>;
    type SerializeMap = ser::Impossible<(), Error>;
    type SerializeStruct = ser::Impossible<(), Error>;
    type SerializeStructVariant = ser::Impossible<(), Error>;

    fn serialize_str(self, v: &str) -> Result<()> {
        self.ser
            .formatter
            .write_number_str(&mut self.ser.writer, v)
            .map_err(Error::io)
    }

    fn serialize_bool(self, _v: bool) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_i8(self, _v: i8) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_i16(self, _v: i16) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_i32(self, _v: i32) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_i64(self, _v: i64) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_i128(self, _v: i128) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_u8(self, _v: u8) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_u16(self, _v: u16) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_u32(self, _v: u32) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_u64(self, _v: u64) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_u128(self, _v: u128) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_f32(self, _v: f32) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_f64(self, _v: f64) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_char(self, _v: char) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_bytes(self, _v: &[u8]) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_none(self) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_some<T: Serialize + ?Sized>(self, _v: &T) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_unit(self) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_unit_struct(self, _name: &'static str) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_unit_variant(self, _n: &'static str, _i: u32, _v: &'static str) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_newtype_struct<T: Serialize + ?Sized>(self, _n: &'static str, _v: &T) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_newtype_variant<T: Serialize + ?Sized>(self, _n: &'static str, _i: u32, _v: &'static str, _val: &T) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_seq(self, _len: Option<usize>) -> Result<Self::SerializeSeq> { Err(key_must_be_a_string()) }
    fn serialize_tuple(self, _len: usize) -> Result<Self::SerializeTuple> { Err(key_must_be_a_string()) }
    fn serialize_tuple_struct(self, _n: &'static str, _len: usize) -> Result<Self::SerializeTupleStruct> { Err(key_must_be_a_string()) }
    fn serialize_tuple_variant(self, _n: &'static str, _i: u32, _v: &'static str, _len: usize) -> Result<Self::SerializeTupleVariant> { Err(key_must_be_a_string()) }
    fn serialize_map(self, _len: Option<usize>) -> Result<Self::SerializeMap> { Err(key_must_be_a_string()) }
    fn serialize_struct(self, _n: &'static str, _len: usize) -> Result<Self::SerializeStruct> { Err(key_must_be_a_string()) }
    fn serialize_struct_variant(self, _n: &'static str, _i: u32, _v: &'static str, _len: usize) -> Result<Self::SerializeStructVariant> { Err(key_must_be_a_string()) }
}

/// Serializer that writes a raw value string directly (for raw_value).
#[cfg(feature = "raw_value")]
struct RawValueStrSerializer<'a, W: 'a, F: 'a> {
    ser: &'a mut Serializer<W, F>,
}

#[cfg(feature = "raw_value")]
impl<'a, W: io::Write, F: Formatter> ser::Serializer for RawValueStrSerializer<'a, W, F> {
    type Ok = ();
    type Error = Error;
    type SerializeSeq = ser::Impossible<(), Error>;
    type SerializeTuple = ser::Impossible<(), Error>;
    type SerializeTupleStruct = ser::Impossible<(), Error>;
    type SerializeTupleVariant = ser::Impossible<(), Error>;
    type SerializeMap = ser::Impossible<(), Error>;
    type SerializeStruct = ser::Impossible<(), Error>;
    type SerializeStructVariant = ser::Impossible<(), Error>;

    fn serialize_str(self, v: &str) -> Result<()> {
        self.ser
            .writer
            .write_all(v.as_bytes())
            .map_err(Error::io)
    }

    fn serialize_bool(self, _v: bool) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_i8(self, _v: i8) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_i16(self, _v: i16) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_i32(self, _v: i32) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_i64(self, _v: i64) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_i128(self, _v: i128) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_u8(self, _v: u8) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_u16(self, _v: u16) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_u32(self, _v: u32) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_u64(self, _v: u64) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_u128(self, _v: u128) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_f32(self, _v: f32) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_f64(self, _v: f64) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_char(self, _v: char) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_bytes(self, _v: &[u8]) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_none(self) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_some<T: Serialize + ?Sized>(self, _v: &T) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_unit(self) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_unit_struct(self, _name: &'static str) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_unit_variant(self, _n: &'static str, _i: u32, _v: &'static str) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_newtype_struct<T: Serialize + ?Sized>(self, _n: &'static str, _v: &T) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_newtype_variant<T: Serialize + ?Sized>(self, _n: &'static str, _i: u32, _v: &'static str, _val: &T) -> Result<()> { Err(key_must_be_a_string()) }
    fn serialize_seq(self, _len: Option<usize>) -> Result<Self::SerializeSeq> { Err(key_must_be_a_string()) }
    fn serialize_tuple(self, _len: usize) -> Result<Self::SerializeTuple> { Err(key_must_be_a_string()) }
    fn serialize_tuple_struct(self, _n: &'static str, _len: usize) -> Result<Self::SerializeTupleStruct> { Err(key_must_be_a_string()) }
    fn serialize_tuple_variant(self, _n: &'static str, _i: u32, _v: &'static str, _len: usize) -> Result<Self::SerializeTupleVariant> { Err(key_must_be_a_string()) }
    fn serialize_map(self, _len: Option<usize>) -> Result<Self::SerializeMap> { Err(key_must_be_a_string()) }
    fn serialize_struct(self, _n: &'static str, _len: usize) -> Result<Self::SerializeStruct> { Err(key_must_be_a_string()) }
    fn serialize_struct_variant(self, _n: &'static str, _i: u32, _v: &'static str, _len: usize) -> Result<Self::SerializeStructVariant> { Err(key_must_be_a_string()) }
}

// ---- String escaping ----

// Table of escape bytes: 0 = no escape, otherwise the escape char or 0xFF for \uXXXX
// Bytes 0x00..0x1F need escaping, 0x22 ("), 0x5C (\)
static ESCAPE: [u8; 256] = {
    let mut table = [0u8; 256];
    // Control characters
    let mut i = 0u8;
    loop {
        if i < 0x20 {
            table[i as usize] = 0xFF; // \uXXXX
        }
        if i == 0xFF { break; }
        i += 1;
    }
    table[0x08] = b'b';
    table[0x09] = b't';
    table[0x0A] = b'n';
    table[0x0C] = b'f';
    table[0x0D] = b'r';
    table[0x22] = b'"';
    table[0x5C] = b'\\';
    table
};

fn format_escaped_str<W: io::Write + ?Sized, F: Formatter>(
    writer: &mut W,
    formatter: &mut F,
    value: &str,
) -> io::Result<()> {
    formatter.begin_string(writer)?;
    format_escaped_str_contents(writer, formatter, value)?;
    formatter.end_string(writer)
}

fn format_escaped_str_contents<W: io::Write + ?Sized, F: Formatter>(
    writer: &mut W,
    formatter: &mut F,
    value: &str,
) -> io::Result<()> {
    let bytes = value.as_bytes();
    let mut start = 0;
    let mut i = 0;

    while i < bytes.len() {
        let byte = bytes[i];
        let escape = ESCAPE[byte as usize];
        if escape == 0 {
            i += 1;
            continue;
        }

        if start < i {
            formatter.write_string_fragment(writer, &value[start..i])?;
        }

        let char_escape = match escape {
            b'"' => CharEscape::Quote,
            b'\\' => CharEscape::ReverseSolidus,
            b'b' => CharEscape::Backspace,
            b't' => CharEscape::Tab,
            b'n' => CharEscape::LineFeed,
            b'f' => CharEscape::FormFeed,
            b'r' => CharEscape::CarriageReturn,
            _ => CharEscape::AsciiControl(byte),
        };
        formatter.write_char_escape(writer, char_escape)?;

        i += 1;
        start = i;
    }

    if start < bytes.len() {
        formatter.write_string_fragment(writer, &value[start..])?;
    }

    Ok(())
}

// ---- Float formatting ----

fn format_float_f64(value: f64) -> String {
    // Use ryu for shortest round-trip representation
    // We don't have ryu in our dependencies; use zmij crate instead
    // Actually, we use zmij crate as mentioned in manifest
    // zmij is described as providing float formatting
    // Let's use the zmij crate
    zmij::Buffer::new().format(value).to_owned()
}

fn format_float_f32(value: f32) -> String {
    zmij::Buffer::new().format(value).to_owned()
}
