use crate::error::{Error, ErrorCode, Result};
use crate::io;

#[cfg(feature = "std")]
use crate::iter::LineColIterator;

#[cfg(feature = "raw_value")]
use crate::raw::{BorrowedRawDeserializer, OwnedRawDeserializer};

#[cfg(feature = "raw_value")]
use serde_core::de::Visitor;

/// Position in the input stream.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct Position {
    pub line: usize,
    pub column: usize,
}

/// A reference to a parsed string/bytes — either borrowed from input or copied into scratch.
pub enum Reference<'b, 'c, T: ?Sized + 'static> {
    Borrowed(&'b T),
    Copied(&'c T),
}

impl<'b, 'c, T: ?Sized + 'static> core::ops::Deref for Reference<'b, 'c, T> {
    type Target = T;

    fn deref(&self) -> &Self::Target {
        match self {
            Reference::Borrowed(b) => b,
            Reference::Copied(c) => c,
        }
    }
}

/// Sealed trait for reading JSON input.
pub trait Read<'de>: private::Sealed {
    #[doc(hidden)]
    fn next(&mut self) -> Result<Option<u8>>;

    #[doc(hidden)]
    fn peek(&mut self) -> Result<Option<u8>>;

    #[doc(hidden)]
    fn discard(&mut self);

    #[doc(hidden)]
    fn position(&self) -> Position;

    #[doc(hidden)]
    fn peek_position(&self) -> Position;

    #[doc(hidden)]
    fn byte_offset(&self) -> usize;

    #[doc(hidden)]
    fn parse_str<'s>(
        &'s mut self,
        scratch: &'s mut Vec<u8>,
    ) -> Result<Reference<'de, 's, str>>;

    #[doc(hidden)]
    fn parse_str_raw<'s>(
        &'s mut self,
        scratch: &'s mut Vec<u8>,
    ) -> Result<Reference<'de, 's, [u8]>>;

    #[doc(hidden)]
    fn ignore_str(&mut self) -> Result<()>;

    #[doc(hidden)]
    fn decode_hex_escape(&mut self) -> Result<u16>;

    #[cfg(feature = "raw_value")]
    #[doc(hidden)]
    fn begin_raw_buffering(&mut self);

    #[cfg(feature = "raw_value")]
    #[doc(hidden)]
    fn end_raw_buffering<V: Visitor<'de>>(&mut self, visitor: V) -> Result<V::Value>;

    #[doc(hidden)]
    const should_early_return_if_failed: bool;

    #[doc(hidden)]
    fn set_failed(&mut self, failed: &mut bool);
}

/// Marker trait for readers that support fused iteration.
pub trait Fused: private::Sealed {}

mod private {
    pub trait Sealed {}
}

// ── helpers ──────────────────────────────────────────────────────────────────

fn decode_hex_escape_from<R: Read<'static>>(read: &mut R) -> Result<u16> {
    // Implemented inline per reader; this is just a convenience note.
    unimplemented!()
}

/// Read 4 hex digits and return them as a u16.
fn read_four_hex_digits(bytes: &[u8], pos: &mut usize) -> Option<u16> {
    if *pos + 4 > bytes.len() {
        return None;
    }
    let mut n: u16 = 0;
    for i in 0..4 {
        let digit = match bytes[*pos + i] {
            c @ b'0'..=b'9' => (c - b'0') as u16,
            c @ b'a'..=b'f' => (c - b'a' + 10) as u16,
            c @ b'A'..=b'F' => (c - b'A' + 10) as u16,
            _ => return None,
        };
        n = (n << 4) | digit;
    }
    *pos += 4;
    Some(n)
}

/// Parse a string body (after the opening `"`) from a byte slice. Returns the
/// index just past the closing `"`.
///
/// If the string has no escapes, returns `Ok(None)` — the caller can borrow
/// the slice directly.  If there were escapes the decoded bytes are written into
/// `scratch` and `Ok(Some(end_pos))` is returned.
fn parse_string_bytes<'de>(
    slice: &'de [u8],
    index: &mut usize, // on entry: first byte after opening quote; on exit: first byte after closing quote
    scratch: &mut Vec<u8>,
) -> Result<bool> {
    // Returns true if we used scratch (i.e. there were escapes/multibyte concerns),
    // false if the raw slice can be borrowed.
    let start = *index;
    loop {
        if *index >= slice.len() {
            return Err(Error::syntax(ErrorCode::EofWhileParsingString, 0, 0));
        }
        let byte = slice[*index];
        match byte {
            b'"' => {
                // closing quote
                *index += 1;
                return Ok(false); // borrowable (scratch not used yet, unless we fell through)
                // Note: if we ever pushed to scratch we need Ok(true); handled below.
            }
            b'\\' => {
                // need scratch: first copy everything so far
                scratch.extend_from_slice(&slice[start..*index]);
                *index += 1;
                parse_escape(slice, index, scratch)?;
                // now continue in scratch-mode
                return parse_string_bytes_scratch(slice, index, scratch);
            }
            byte if byte < 0x20 => {
                return Err(Error::syntax(ErrorCode::ControlCharacterWhileParsingString, 0, 0));
            }
            _ => {
                *index += 1;
            }
        }
    }
}

fn parse_string_bytes_scratch<'de>(
    slice: &'de [u8],
    index: &mut usize,
    scratch: &mut Vec<u8>,
) -> Result<bool> {
    loop {
        if *index >= slice.len() {
            return Err(Error::syntax(ErrorCode::EofWhileParsingString, 0, 0));
        }
        let byte = slice[*index];
        match byte {
            b'"' => {
                *index += 1;
                return Ok(true);
            }
            b'\\' => {
                *index += 1;
                parse_escape(slice, index, scratch)?;
            }
            byte if byte < 0x20 => {
                return Err(Error::syntax(ErrorCode::ControlCharacterWhileParsingString, 0, 0));
            }
            _ => {
                scratch.push(byte);
                *index += 1;
            }
        }
    }
}

fn parse_escape(slice: &[u8], index: &mut usize, scratch: &mut Vec<u8>) -> Result<()> {
    if *index >= slice.len() {
        return Err(Error::syntax(ErrorCode::EofWhileParsingString, 0, 0));
    }
    let escape = slice[*index];
    *index += 1;
    match escape {
        b'"' => scratch.push(b'"'),
        b'\\' => scratch.push(b'\\'),
        b'/' => scratch.push(b'/'),
        b'b' => scratch.push(b'\x08'),
        b'f' => scratch.push(b'\x0c'),
        b'n' => scratch.push(b'\n'),
        b'r' => scratch.push(b'\r'),
        b't' => scratch.push(b'\t'),
        b'u' => {
            let n = decode_four_hex(slice, index)?;
            // handle surrogate pairs
            let c = if n >= 0xD800 && n <= 0xDBFF {
                // high surrogate — expect \uXXXX
                if *index + 1 < slice.len() && slice[*index] == b'\\' && slice[*index + 1] == b'u' {
                    *index += 2;
                    let n2 = decode_four_hex(slice, index)?;
                    if n2 >= 0xDC00 && n2 <= 0xDFFF {
                        let codepoint = 0x10000u32
                            + ((n as u32 - 0xD800) << 10)
                            + (n2 as u32 - 0xDC00);
                        char::from_u32(codepoint)
                            .ok_or_else(|| Error::syntax(ErrorCode::InvalidUnicodeCodePoint, 0, 0))?
                    } else {
                        return Err(Error::syntax(ErrorCode::LoneLeadingSurrogateInHexEscape, 0, 0));
                    }
                } else {
                    return Err(Error::syntax(ErrorCode::LoneLeadingSurrogateInHexEscape, 0, 0));
                }
            } else if n >= 0xDC00 && n <= 0xDFFF {
                return Err(Error::syntax(ErrorCode::LoneLeadingSurrogateInHexEscape, 0, 0));
            } else {
                char::from_u32(n as u32)
                    .ok_or_else(|| Error::syntax(ErrorCode::InvalidUnicodeCodePoint, 0, 0))?
            };
            let mut buf = [0u8; 4];
            let s = c.encode_utf8(&mut buf);
            scratch.extend_from_slice(s.as_bytes());
        }
        _ => {
            return Err(Error::syntax(ErrorCode::InvalidEscape, 0, 0));
        }
    }
    Ok(())
}

fn decode_four_hex(slice: &[u8], index: &mut usize) -> Result<u16> {
    if *index + 4 > slice.len() {
        return Err(Error::syntax(ErrorCode::EofWhileParsingString, 0, 0));
    }
    let mut n: u16 = 0;
    for i in 0..4 {
        let digit = match slice[*index + i] {
            c @ b'0'..=b'9' => (c - b'0') as u16,
            c @ b'a'..=b'f' => (c - b'a' + 10) as u16,
            c @ b'A'..=b'F' => (c - b'A' + 10) as u16,
            _ => return Err(Error::syntax(ErrorCode::InvalidEscape, 0, 0)),
        };
        n = (n << 4) | digit;
    }
    *index += 4;
    Ok(n)
}

// ── SliceRead ─────────────────────────────────────────────────────────────────

/// JSON reader over a `&[u8]` slice.
pub struct SliceRead<'a> {
    slice: &'a [u8],
    /// current index (next byte to read)
    index: usize,
    #[cfg(feature = "raw_value")]
    raw_buffering_start_index: usize,
}

impl<'a> SliceRead<'a> {
    /// Create a new `SliceRead` wrapping the given byte slice.
    pub fn new(slice: &'a [u8]) -> Self {
        SliceRead {
            slice,
            index: 0,
            #[cfg(feature = "raw_value")]
            raw_buffering_start_index: 0,
        }
    }

    fn position_of_index(&self, i: usize) -> Position {
        let mut line = 1usize;
        let mut column = 0usize;
        for &b in &self.slice[..i] {
            if b == b'\n' {
                line += 1;
                column = 0;
            } else {
                column += 1;
            }
        }
        Position { line, column }
    }

    /// Parse a string that starts at the current index (which should point just
    /// past the opening `"`).
    fn parse_str_bytes<'s>(
        &'s mut self,
        scratch: &'s mut Vec<u8>,
        validate: bool,
    ) -> Result<Reference<'a, 's, [u8]>> {
        let start = self.index;
        loop {
            if self.index >= self.slice.len() {
                return Err(self.error(ErrorCode::EofWhileParsingString));
            }
            let byte = self.slice[self.index];
            match byte {
                b'"' => {
                    // end of string — we can borrow if scratch is empty
                    let end = self.index;
                    self.index += 1;
                    if scratch.is_empty() {
                        return Ok(Reference::Borrowed(&self.slice[start..end]));
                    } else {
                        return Ok(Reference::Copied(scratch.as_slice()));
                    }
                }
                b'\\' => {
                    // copy everything up to here into scratch and handle escape
                    scratch.extend_from_slice(&self.slice[start..self.index]);
                    self.index += 1;
                    self.parse_escape_into_scratch(scratch)?;
                    // continue loop reading into scratch
                    return self.parse_str_bytes_into_scratch(scratch, validate);
                }
                byte if byte < 0x20 => {
                    return Err(self.error(ErrorCode::ControlCharacterWhileParsingString));
                }
                _ => {
                    self.index += 1;
                }
            }
        }
    }

    fn parse_str_bytes_into_scratch<'s>(
        &'s mut self,
        scratch: &'s mut Vec<u8>,
        validate: bool,
    ) -> Result<Reference<'a, 's, [u8]>> {
        loop {
            if self.index >= self.slice.len() {
                return Err(self.error(ErrorCode::EofWhileParsingString));
            }
            let byte = self.slice[self.index];
            match byte {
                b'"' => {
                    self.index += 1;
                    return Ok(Reference::Copied(scratch.as_slice()));
                }
                b'\\' => {
                    self.index += 1;
                    self.parse_escape_into_scratch(scratch)?;
                }
                byte if byte < 0x20 => {
                    return Err(self.error(ErrorCode::ControlCharacterWhileParsingString));
                }
                _ => {
                    scratch.push(byte);
                    self.index += 1;
                }
            }
        }
    }

    fn parse_escape_into_scratch(&mut self, scratch: &mut Vec<u8>) -> Result<()> {
        if self.index >= self.slice.len() {
            return Err(self.error(ErrorCode::EofWhileParsingString));
        }
        let escape = self.slice[self.index];
        self.index += 1;
        match escape {
            b'"' => scratch.push(b'"'),
            b'\\' => scratch.push(b'\\'),
            b'/' => scratch.push(b'/'),
            b'b' => scratch.push(b'\x08'),
            b'f' => scratch.push(b'\x0c'),
            b'n' => scratch.push(b'\n'),
            b'r' => scratch.push(b'\r'),
            b't' => scratch.push(b'\t'),
            b'u' => {
                let n = self.decode_hex_escape()?;
                let c = if n >= 0xD800 && n <= 0xDBFF {
                    if self.index + 1 < self.slice.len()
                        && self.slice[self.index] == b'\\'
                        && self.slice[self.index + 1] == b'u'
                    {
                        self.index += 2;
                        let n2 = self.decode_hex_escape()?;
                        if n2 >= 0xDC00 && n2 <= 0xDFFF {
                            let codepoint = 0x10000u32
                                + ((n as u32 - 0xD800) << 10)
                                + (n2 as u32 - 0xDC00);
                            char::from_u32(codepoint).ok_or_else(|| {
                                self.error(ErrorCode::InvalidUnicodeCodePoint)
                            })?
                        } else {
                            return Err(self.error(ErrorCode::LoneLeadingSurrogateInHexEscape));
                        }
                    } else {
                        return Err(self.error(ErrorCode::LoneLeadingSurrogateInHexEscape));
                    }
                } else if n >= 0xDC00 && n <= 0xDFFF {
                    return Err(self.error(ErrorCode::LoneLeadingSurrogateInHexEscape));
                } else {
                    char::from_u32(n as u32).ok_or_else(|| {
                        self.error(ErrorCode::InvalidUnicodeCodePoint)
                    })?
                };
                let mut buf = [0u8; 4];
                let s = c.encode_utf8(&mut buf);
                scratch.extend_from_slice(s.as_bytes());
            }
            _ => {
                return Err(self.error(ErrorCode::InvalidEscape));
            }
        }
        Ok(())
    }

    fn error(&self, code: ErrorCode) -> Error {
        let pos = self.position_of_index(self.index);
        Error::syntax(code, pos.line, pos.column)
    }
}

impl<'a> private::Sealed for SliceRead<'a> {}
impl<'a> Fused for SliceRead<'a> {}

impl<'de> Read<'de> for SliceRead<'de> {
    #[inline]
    fn next(&mut self) -> Result<Option<u8>> {
        if self.index < self.slice.len() {
            let b = self.slice[self.index];
            self.index += 1;
            Ok(Some(b))
        } else {
            Ok(None)
        }
    }

    #[inline]
    fn peek(&mut self) -> Result<Option<u8>> {
        if self.index < self.slice.len() {
            Ok(Some(self.slice[self.index]))
        } else {
            Ok(None)
        }
    }

    #[inline]
    fn discard(&mut self) {
        self.index += 1;
    }

    fn position(&self) -> Position {
        self.position_of_index(self.index)
    }

    fn peek_position(&self) -> Position {
        self.position_of_index(self.index)
    }

    fn byte_offset(&self) -> usize {
        self.index
    }

    fn parse_str<'s>(
        &'s mut self,
        scratch: &'s mut Vec<u8>,
    ) -> Result<Reference<'de, 's, str>> {
        match self.parse_str_bytes(scratch, true)? {
            Reference::Borrowed(bytes) => {
                let s = core::str::from_utf8(bytes)
                    .map_err(|_| self.error(ErrorCode::InvalidUnicodeCodePoint))?;
                Ok(Reference::Borrowed(s))
            }
            Reference::Copied(bytes) => {
                let s = core::str::from_utf8(bytes)
                    .map_err(|_| self.error(ErrorCode::InvalidUnicodeCodePoint))?;
                Ok(Reference::Copied(s))
            }
        }
    }

    fn parse_str_raw<'s>(
        &'s mut self,
        scratch: &'s mut Vec<u8>,
    ) -> Result<Reference<'de, 's, [u8]>> {
        self.parse_str_bytes(scratch, false)
    }

    fn ignore_str(&mut self) -> Result<()> {
        loop {
            if self.index >= self.slice.len() {
                return Err(self.error(ErrorCode::EofWhileParsingString));
            }
            let byte = self.slice[self.index];
            match byte {
                b'"' => {
                    self.index += 1;
                    return Ok(());
                }
                b'\\' => {
                    self.index += 1;
                    if self.index >= self.slice.len() {
                        return Err(self.error(ErrorCode::EofWhileParsingString));
                    }
                    if self.slice[self.index] == b'u' {
                        self.index += 1;
                        // skip 4 hex digits
                        if self.index + 4 > self.slice.len() {
                            return Err(self.error(ErrorCode::EofWhileParsingString));
                        }
                        self.index += 4;
                    } else {
                        self.index += 1;
                    }
                }
                byte if byte < 0x20 => {
                    return Err(self.error(ErrorCode::ControlCharacterWhileParsingString));
                }
                _ => {
                    self.index += 1;
                }
            }
        }
    }

    fn decode_hex_escape(&mut self) -> Result<u16> {
        if self.index + 4 > self.slice.len() {
            self.index = self.slice.len();
            return Err(self.error(ErrorCode::EofWhileParsingString));
        }
        let mut n: u16 = 0;
        for i in 0..4 {
            let digit = match self.slice[self.index + i] {
                c @ b'0'..=b'9' => (c - b'0') as u16,
                c @ b'a'..=b'f' => (c - b'a' + 10) as u16,
                c @ b'A'..=b'F' => (c - b'A' + 10) as u16,
                _ => return Err(self.error(ErrorCode::InvalidEscape)),
            };
            n = (n << 4) | digit;
        }
        self.index += 4;
        Ok(n)
    }

    #[cfg(feature = "raw_value")]
    fn begin_raw_buffering(&mut self) {
        self.raw_buffering_start_index = self.index;
    }

    #[cfg(feature = "raw_value")]
    fn end_raw_buffering<V: Visitor<'de>>(&mut self, visitor: V) -> Result<V::Value> {
        let raw = &self.slice[self.raw_buffering_start_index..self.index];
        let raw_str = core::str::from_utf8(raw)
            .map_err(|_| self.error(ErrorCode::InvalidUnicodeCodePoint))?;
        visitor.visit_map(BorrowedRawDeserializer::new(raw_str))
    }

    const should_early_return_if_failed: bool = false;

    fn set_failed(&mut self, _failed: &mut bool) {}
}

// ── StrRead ───────────────────────────────────────────────────────────────────

/// JSON reader over a `&str` slice. Skips UTF-8 validation for unescaped
/// strings since the input is already valid UTF-8.
pub struct StrRead<'a> {
    delegate: SliceRead<'a>,
}

impl<'a> StrRead<'a> {
    pub fn new(s: &'a str) -> Self {
        StrRead {
            delegate: SliceRead::new(s.as_bytes()),
        }
    }
}

impl<'a> private::Sealed for StrRead<'a> {}
impl<'a> Fused for StrRead<'a> {}

impl<'de> Read<'de> for StrRead<'de> {
    #[inline]
    fn next(&mut self) -> Result<Option<u8>> {
        self.delegate.next()
    }

    #[inline]
    fn peek(&mut self) -> Result<Option<u8>> {
        self.delegate.peek()
    }

    #[inline]
    fn discard(&mut self) {
        self.delegate.discard()
    }

    fn position(&self) -> Position {
        self.delegate.position()
    }

    fn peek_position(&self) -> Position {
        self.delegate.peek_position()
    }

    fn byte_offset(&self) -> usize {
        self.delegate.byte_offset()
    }

    fn parse_str<'s>(
        &'s mut self,
        scratch: &'s mut Vec<u8>,
    ) -> Result<Reference<'de, 's, str>> {
        // Same as SliceRead but can skip utf8 check for borrowed case (input is valid str)
        match self.delegate.parse_str_bytes(scratch, true)? {
            Reference::Borrowed(bytes) => {
                // SAFETY: input is &str so bytes are valid UTF-8
                let s = unsafe { core::str::from_utf8_unchecked(bytes) };
                Ok(Reference::Borrowed(s))
            }
            Reference::Copied(bytes) => {
                let s = core::str::from_utf8(bytes)
                    .map_err(|_| self.delegate.error(ErrorCode::InvalidUnicodeCodePoint))?;
                Ok(Reference::Copied(s))
            }
        }
    }

    fn parse_str_raw<'s>(
        &'s mut self,
        scratch: &'s mut Vec<u8>,
    ) -> Result<Reference<'de, 's, [u8]>> {
        self.delegate.parse_str_raw(scratch)
    }

    fn ignore_str(&mut self) -> Result<()> {
        self.delegate.ignore_str()
    }

    fn decode_hex_escape(&mut self) -> Result<u16> {
        self.delegate.decode_hex_escape()
    }

    #[cfg(feature = "raw_value")]
    fn begin_raw_buffering(&mut self) {
        self.delegate.begin_raw_buffering()
    }

    #[cfg(feature = "raw_value")]
    fn end_raw_buffering<V: Visitor<'de>>(&mut self, visitor: V) -> Result<V::Value> {
        let raw = &self.delegate.slice
            [self.delegate.raw_buffering_start_index..self.delegate.index];
        // SAFETY: input was &str so this slice is valid UTF-8
        let raw_str = unsafe { core::str::from_utf8_unchecked(raw) };
        visitor.visit_map(BorrowedRawDeserializer::new(raw_str))
    }

    const should_early_return_if_failed: bool = false;

    fn set_failed(&mut self, _failed: &mut bool) {}
}

// ── IoRead ────────────────────────────────────────────────────────────────────

#[cfg(feature = "std")]
pub struct IoRead<R: io::Read> {
    iter: LineColIterator<io::Bytes<R>>,
    /// one-byte lookahead
    ch: Option<u8>,
    #[cfg(feature = "raw_value")]
    raw_buffer: Option<Vec<u8>>,
}

#[cfg(feature = "std")]
impl<R: io::Read> IoRead<R> {
    pub fn new(reader: R) -> Self {
        IoRead {
            iter: LineColIterator::new(reader.bytes()),
            ch: None,
            #[cfg(feature = "raw_value")]
            raw_buffer: None,
        }
    }

    fn parse_str_bytes<'s>(
        &'s mut self,
        scratch: &'s mut Vec<u8>,
        validate: bool,
    ) -> Result<Reference<'static, 's, [u8]>> {
        loop {
            let b = match self.next()? {
                Some(b) => b,
                None => return Err(self.error(ErrorCode::EofWhileParsingString)),
            };
            match b {
                b'"' => {
                    return Ok(Reference::Copied(scratch.as_slice()));
                }
                b'\\' => {
                    self.parse_escape_into_scratch(scratch)?;
                }
                byte if byte < 0x20 => {
                    return Err(self.error(ErrorCode::ControlCharacterWhileParsingString));
                }
                _ => {
                    scratch.push(b);
                }
            }
        }
    }

    fn parse_escape_into_scratch(&mut self, scratch: &mut Vec<u8>) -> Result<()> {
        let escape = match self.next()? {
            Some(b) => b,
            None => return Err(self.error(ErrorCode::EofWhileParsingString)),
        };
        match escape {
            b'"' => scratch.push(b'"'),
            b'\\' => scratch.push(b'\\'),
            b'/' => scratch.push(b'/'),
            b'b' => scratch.push(b'\x08'),
            b'f' => scratch.push(b'\x0c'),
            b'n' => scratch.push(b'\n'),
            b'r' => scratch.push(b'\r'),
            b't' => scratch.push(b'\t'),
            b'u' => {
                let n = self.decode_hex_escape()?;
                let c = if n >= 0xD800 && n <= 0xDBFF {
                    // high surrogate
                    match (self.next()?, self.next()?) {
                        (Some(b'\\'), Some(b'u')) => {
                            let n2 = self.decode_hex_escape()?;
                            if n2 >= 0xDC00 && n2 <= 0xDFFF {
                                let codepoint = 0x10000u32
                                    + ((n as u32 - 0xD800) << 10)
                                    + (n2 as u32 - 0xDC00);
                                char::from_u32(codepoint).ok_or_else(|| {
                                    self.error(ErrorCode::InvalidUnicodeCodePoint)
                                })?
                            } else {
                                return Err(
                                    self.error(ErrorCode::LoneLeadingSurrogateInHexEscape)
                                );
                            }
                        }
                        _ => {
                            return Err(self.error(ErrorCode::LoneLeadingSurrogateInHexEscape));
                        }
                    }
                } else if n >= 0xDC00 && n <= 0xDFFF {
                    return Err(self.error(ErrorCode::LoneLeadingSurrogateInHexEscape));
                } else {
                    char::from_u32(n as u32)
                        .ok_or_else(|| self.error(ErrorCode::InvalidUnicodeCodePoint))?
                };
                let mut buf = [0u8; 4];
                let s = c.encode_utf8(&mut buf);
                scratch.extend_from_slice(s.as_bytes());
            }
            _ => {
                return Err(self.error(ErrorCode::InvalidEscape));
            }
        }
        Ok(())
    }

    fn error(&self, code: ErrorCode) -> Error {
        let pos = self.iter.position();
        Error::syntax(code, pos.0, pos.1)
    }
}

#[cfg(feature = "std")]
impl<R: io::Read> private::Sealed for IoRead<R> {}

#[cfg(feature = "std")]
impl<'de, R: io::Read> Read<'de> for IoRead<R> {
    #[inline]
    fn next(&mut self) -> Result<Option<u8>> {
        match self.ch.take() {
            Some(b) => {
                #[cfg(feature = "raw_value")]
                if let Some(ref mut buf) = self.raw_buffer {
                    buf.push(b);
                }
                Ok(Some(b))
            }
            None => match self.iter.next() {
                Some(Ok(b)) => {
                    #[cfg(feature = "raw_value")]
                    if let Some(ref mut buf) = self.raw_buffer {
                        buf.push(b);
                    }
                    Ok(Some(b))
                }
                Some(Err(e)) => Err(Error::io(e)),
                None => Ok(None),
            },
        }
    }

    #[inline]
    fn peek(&mut self) -> Result<Option<u8>> {
        if self.ch.is_none() {
            self.ch = match self.iter.next() {
                Some(Ok(b)) => Some(b),
                Some(Err(e)) => return Err(Error::io(e)),
                None => None,
            };
        }
        Ok(self.ch)
    }

    #[inline]
    fn discard(&mut self) {
        // peek first to fill ch if needed, then drop it
        if self.ch.is_some() {
            let b = self.ch.take().unwrap();
            #[cfg(feature = "raw_value")]
            if let Some(ref mut buf) = self.raw_buffer {
                buf.push(b);
            }
            #[cfg(not(feature = "raw_value"))]
            let _ = b;
        } else {
            match self.iter.next() {
                Some(Ok(b)) => {
                    #[cfg(feature = "raw_value")]
                    if let Some(ref mut buf) = self.raw_buffer {
                        buf.push(b);
                    }
                    #[cfg(not(feature = "raw_value"))]
                    let _ = b;
                }
                _ => {}
            }
        }
    }

    fn position(&self) -> Position {
        let p = self.iter.position();
        Position {
            line: p.0,
            column: p.1,
        }
    }

    fn peek_position(&self) -> Position {
        let p = self.iter.position();
        Position {
            line: p.0,
            column: p.1,
        }
    }

    fn byte_offset(&self) -> usize {
        self.iter.byte_offset()
    }

    fn parse_str<'s>(
        &'s mut self,
        scratch: &'s mut Vec<u8>,
    ) -> Result<Reference<'de, 's, str>> {
        self.parse_str_bytes(scratch, true)?;
        let s = core::str::from_utf8(scratch)
            .map_err(|_| self.error(ErrorCode::InvalidUnicodeCodePoint))?;
        Ok(Reference::Copied(s))
    }

    fn parse_str_raw<'s>(
        &'s mut self,
        scratch: &'s mut Vec<u8>,
    ) -> Result<Reference<'de, 's, [u8]>> {
        self.parse_str_bytes(scratch, false)?;
        Ok(Reference::Copied(scratch.as_slice()))
    }

    fn ignore_str(&mut self) -> Result<()> {
        loop {
            match self.next()? {
                Some(b'"') => return Ok(()),
                Some(b'\\') => {
                    let escape = match self.next()? {
                        Some(b) => b,
                        None => return Err(self.error(ErrorCode::EofWhileParsingString)),
                    };
                    if escape == b'u' {
                        // skip 4 hex digits
                        for _ in 0..4 {
                            match self.next()? {
                                Some(_) => {}
                                None => return Err(self.error(ErrorCode::EofWhileParsingString)),
                            }
                        }
                    }
                }
                Some(b) if b < 0x20 => {
                    return Err(self.error(ErrorCode::ControlCharacterWhileParsingString));
                }
                Some(_) => {}
                None => return Err(self.error(ErrorCode::EofWhileParsingString)),
            }
        }
    }

    fn decode_hex_escape(&mut self) -> Result<u16> {
        let mut n: u16 = 0;
        for _ in 0..4 {
            let b = match self.next()? {
                Some(b) => b,
                None => return Err(self.error(ErrorCode::EofWhileParsingString)),
            };
            let digit = match b {
                c @ b'0'..=b'9' => (c - b'0') as u16,
                c @ b'a'..=b'f' => (c - b'a' + 10) as u16,
                c @ b'A'..=b'F' => (c - b'A' + 10) as u16,
                _ => return Err(self.error(ErrorCode::InvalidEscape)),
            };
            n = (n << 4) | digit;
        }
        Ok(n)
    }

    #[cfg(feature = "raw_value")]
    fn begin_raw_buffering(&mut self) {
        self.raw_buffer = Some(Vec::new());
    }

    #[cfg(feature = "raw_value")]
    fn end_raw_buffering<V: Visitor<'de>>(&mut self, visitor: V) -> Result<V::Value> {
        let buf = self.raw_buffer.take().unwrap_or_default();
        let raw_str = String::from_utf8(buf)
            .map_err(|_| self.error(ErrorCode::InvalidUnicodeCodePoint))?;
        visitor.visit_map(OwnedRawDeserializer::new(raw_str))
    }

    const should_early_return_if_failed: bool = true;

    fn set_failed(&mut self, _failed: &mut bool) {
        *_failed = true;
    }
}
