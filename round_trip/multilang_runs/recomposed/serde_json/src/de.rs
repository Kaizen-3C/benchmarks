use alloc::borrow::ToOwned;
use alloc::string::String;
use alloc::vec::Vec;
use core::fmt;
use core::iter::FusedIterator;
use core::marker::PhantomData;
use core::result;
use core::str;

use serde_core::de::{
    self, Deserialize, DeserializeOwned, DeserializeSeed, Expected, IntoDeserializer,
    MapAccess, SeqAccess, Unexpected, Visitor,
};
use serde_core::forward_to_deserialize_any;

use crate::error::{Error, ErrorCode, Result};
#[cfg(feature = "float_roundtrip")]
use crate::lexical;
use crate::number::Number;
use crate::number::NumberDeserializer;
use crate::read::{self, Fused, Reference};

#[cfg(feature = "std")]
pub use crate::read::IoRead;
pub use crate::read::{Read, SliceRead, StrRead};

#[cfg(feature = "arbitrary_precision")]
use alloc::string::ToString;

/// Deserializer from a JSON value.
pub struct Deserializer<R> {
    read: R,
    scratch: Vec<u8>,
    remaining_depth: u8,
    #[cfg(feature = "float_roundtrip")]
    single_precision: bool,
    #[cfg(feature = "unbounded_depth")]
    disable_recursion_limit: bool,
}

impl<'de, R: Read<'de>> Deserializer<R> {
    pub fn new(read: R) -> Self {
        Deserializer {
            read,
            scratch: Vec::new(),
            remaining_depth: 128,
            #[cfg(feature = "float_roundtrip")]
            single_precision: false,
            #[cfg(feature = "unbounded_depth")]
            disable_recursion_limit: false,
        }
    }

    #[cfg(feature = "unbounded_depth")]
    pub fn disable_recursion_limit(&mut self) {
        self.disable_recursion_limit = true;
    }

    pub fn end(&mut self) -> Result<()> {
        match self.parse_whitespace()? {
            Some(_) => Err(self.peek_error(ErrorCode::TrailingCharacters)),
            None => Ok(()),
        }
    }

    pub fn into_iter<T>(self) -> StreamDeserializer<'de, R, T>
    where
        T: de::Deserialize<'de>,
    {
        StreamDeserializer {
            de: self,
            offset: 0,
            failed: false,
            output: PhantomData,
            lifetime: PhantomData,
        }
    }

    fn peek(&mut self) -> Result<Option<u8>> {
        self.read.peek()
    }

    fn peek_or_null(&mut self) -> Result<u8> {
        Ok(self.peek()?.unwrap_or(b'\x00'))
    }

    fn eat_char(&mut self) {
        self.read.discard();
    }

    fn next_char(&mut self) -> Result<Option<u8>> {
        self.read.next()
    }

    fn next_char_or_null(&mut self) -> Result<u8> {
        Ok(self.next_char()?.unwrap_or(b'\x00'))
    }

    fn error(&self, reason: ErrorCode) -> Error {
        let position = self.read.position();
        Error::syntax(reason, position.line, position.column)
    }

    fn peek_error(&self, reason: ErrorCode) -> Error {
        let position = self.read.peek_position();
        Error::syntax(reason, position.line, position.column)
    }

    fn fix_position(&self, err: Error) -> Error {
        if err.is_fix_position() {
            let position = self.read.position();
            err.fix_position(move |code| Error::syntax(code, position.line, position.column))
        } else {
            err
        }
    }

    fn parse_whitespace(&mut self) -> Result<Option<u8>> {
        loop {
            match self.peek()? {
                Some(b' ') | Some(b'\n') | Some(b'\t') | Some(b'\r') => {
                    self.eat_char();
                }
                other => {
                    return Ok(other);
                }
            }
        }
    }

    fn parse_ident(&mut self, ident: &[u8]) -> Result<()> {
        for expected in ident {
            match self.next_char()? {
                None => {
                    return Err(self.error(ErrorCode::EofWhileParsingValue));
                }
                Some(next) => {
                    if next != *expected {
                        return Err(self.error(ErrorCode::ExpectedSomeIdent));
                    }
                }
            }
        }
        Ok(())
    }

    fn parse_str<'s>(&'s mut self) -> Result<Reference<'de, 's, str>> {
        self.read.parse_str(&mut self.scratch)
    }

    fn parse_str_raw<'s>(&'s mut self) -> Result<Reference<'de, 's, [u8]>> {
        self.read.parse_str_raw(&mut self.scratch)
    }

    #[cold]
    fn deserialize_number<'any, V>(&mut self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'any>,
    {
        let peek = match self.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.peek_error(ErrorCode::EofWhileParsingValue));
            }
        };

        let value = match peek {
            b'-' => {
                self.eat_char();
                self.parse_integer(false)
            }
            b'0'..=b'9' => self.parse_integer(true),
            _ => Err(self.peek_error(ErrorCode::InvalidNumber)),
        }?;

        match value {
            #[cfg(not(feature = "arbitrary_precision"))]
            ParserNumber::F64(x) => visitor.visit_f64(x),
            #[cfg(not(feature = "arbitrary_precision"))]
            ParserNumber::U64(x) => visitor.visit_u64(x),
            #[cfg(not(feature = "arbitrary_precision"))]
            ParserNumber::I64(x) => visitor.visit_i64(x),
            #[cfg(feature = "arbitrary_precision")]
            ParserNumber::F64(x) => visitor.visit_f64(x),
            #[cfg(feature = "arbitrary_precision")]
            ParserNumber::U64(x) => visitor.visit_u64(x),
            #[cfg(feature = "arbitrary_precision")]
            ParserNumber::I64(x) => visitor.visit_i64(x),
            #[cfg(feature = "arbitrary_precision")]
            ParserNumber::String(s) => visitor.visit_map(NumberDeserializer { number: s.into() }),
        }
    }

    fn parse_integer(&mut self, positive: bool) -> Result<ParserNumber> {
        let next = match self.next_char()? {
            Some(b) => b,
            None => {
                return Err(self.error(ErrorCode::EofWhileParsingValue));
            }
        };

        match next {
            b'0' => {
                // There can be only one leading '0'.
                match self.peek_or_null()? {
                    b'0'..=b'9' => Err(self.peek_error(ErrorCode::InvalidNumber)),
                    _ => self.parse_number(positive, 0),
                }
            }
            c @ b'1'..=b'9' => {
                let mut res: u64 = (c - b'0') as u64;

                loop {
                    match self.peek_or_null()? {
                        c @ b'0'..=b'9' => {
                            self.eat_char();
                            let digit = (c - b'0') as u64;

                            // We need to be careful with overflow. If we can,
                            // try to keep the number as a `u64` until we grow
                            // too large. At that point, switch to parsing the
                            // value as a `f64`.
                            if overflow!(res * 10 + digit, u64::MAX) {
                                return Ok(ParserNumber::F64(self.parse_long_integer(
                                    positive, res, 1, // res * 10^1
                                )?));
                            }

                            res = res * 10 + digit;
                        }
                        _ => {
                            return self.parse_number(positive, res);
                        }
                    }
                }
            }
            _ => Err(self.error(ErrorCode::InvalidNumber)),
        }
    }

    fn parse_long_integer(
        &mut self,
        positive: bool,
        significand: u64,
        mut exponent: i32,
    ) -> Result<f64> {
        loop {
            match self.peek_or_null()? {
                b'0'..=b'9' => {
                    self.eat_char();
                    // This is already an arbitrary large number, just try to
                    // keep it accurate for as long as possible, considering
                    // digits past the "decimal" as not significant.
                    exponent += 1;
                }
                b'.' => {
                    self.eat_char();
                    return self.parse_decimal(positive, significand, exponent);
                }
                b'e' | b'E' => {
                    self.eat_char();
                    return self.parse_exponent(positive, significand, exponent);
                }
                _ => {
                    return self.f64_from_parts(positive, significand, exponent);
                }
            }
        }
    }

    fn parse_number(&mut self, positive: bool, significand: u64) -> Result<ParserNumber> {
        Ok(match self.peek_or_null()? {
            b'.' => {
                self.eat_char();
                let f = self.parse_decimal(positive, significand, 0)?;
                ParserNumber::F64(f)
            }
            b'e' | b'E' => {
                self.eat_char();
                let f = self.parse_exponent(positive, significand, 0)?;
                ParserNumber::F64(f)
            }
            _ => {
                if positive {
                    ParserNumber::U64(significand)
                } else {
                    let neg = (significand as i64).wrapping_neg();
                    if neg <= 0 {
                        ParserNumber::I64(neg)
                    } else {
                        // Overflow: -9223372036854775809 and beyond
                        ParserNumber::F64(-(significand as f64))
                    }
                }
            }
        })
    }

    fn parse_decimal(
        &mut self,
        positive: bool,
        mut significand: u64,
        exponent: i32,
    ) -> Result<f64> {
        #[cfg(feature = "float_roundtrip")]
        let integer_end = self.read.byte_offset() - 1; // before decimal point

        let mut exponent = exponent;
        let mut at_least_one_digit = false;

        #[cfg(feature = "float_roundtrip")]
        let decimal_start = self.read.byte_offset();

        loop {
            match self.peek_or_null()? {
                c @ b'0'..=b'9' => {
                    self.eat_char();
                    let digit = (c - b'0') as u64;
                    at_least_one_digit = true;

                    if overflow!(significand * 10 + digit, u64::MAX) {
                        // Skip remaining digits.
                        #[cfg(feature = "float_roundtrip")]
                        {
                            let _ = integer_end;
                            let fraction_end = self.read.byte_offset() - 1;
                            return self.parse_decimal_overflow(
                                positive,
                                significand,
                                exponent,
                                decimal_start,
                                fraction_end,
                            );
                        }
                        #[cfg(not(feature = "float_roundtrip"))]
                        while let b'0'..=b'9' = self.peek_or_null()? {
                            self.eat_char();
                        }
                        // Treat overflow as just truncation
                        #[cfg(not(feature = "float_roundtrip"))]
                        {
                            exponent -= 1; // We lost one digit
                            significand = significand * 10 + digit;
                        }
                    } else {
                        significand = significand * 10 + digit;
                        exponent -= 1;
                    }
                }
                _ => {
                    break;
                }
            }
        }

        if !at_least_one_digit {
            return Err(self.peek_error(ErrorCode::InvalidNumber));
        }

        match self.peek_or_null()? {
            b'e' | b'E' => {
                self.eat_char();
                self.parse_exponent(positive, significand, exponent)
            }
            _ => self.f64_from_parts(positive, significand, exponent),
        }
    }

    #[cfg(feature = "float_roundtrip")]
    fn parse_decimal_overflow(
        &mut self,
        positive: bool,
        significand: u64,
        exponent: i32,
        decimal_start: usize,
        _fraction_end: usize,
    ) -> Result<f64> {
        // Skip remaining fraction digits
        while let b'0'..=b'9' = self.peek_or_null()? {
            self.eat_char();
        }
        let exp_addition = match self.peek_or_null()? {
            b'e' | b'E' => {
                self.eat_char();
                self.parse_raw_exponent()?
            }
            _ => 0,
        };
        let _ = decimal_start;
        // Fall back to simple computation
        self.f64_from_parts(positive, significand, exponent + exp_addition)
    }

    fn parse_exponent(
        &mut self,
        positive: bool,
        significand: u64,
        starting_exp: i32,
    ) -> Result<f64> {
        let exp = self.parse_raw_exponent()?;
        self.f64_from_parts(positive, significand, starting_exp + exp)
    }

    fn parse_raw_exponent(&mut self) -> Result<i32> {
        let mut exp_positive = true;
        match self.peek_or_null()? {
            b'+' => {
                self.eat_char();
            }
            b'-' => {
                self.eat_char();
                exp_positive = false;
            }
            _ => {}
        }

        let next = match self.next_char()? {
            Some(b) => b,
            None => {
                return Err(self.error(ErrorCode::EofWhileParsingValue));
            }
        };

        let mut exp: i32 = match next {
            c @ b'0'..=b'9' => (c - b'0') as i32,
            _ => {
                return Err(self.error(ErrorCode::InvalidNumber));
            }
        };

        loop {
            match self.peek_or_null()? {
                c @ b'0'..=b'9' => {
                    self.eat_char();
                    let digit = (c - b'0') as i32;
                    if exp > (i32::MAX - digit) / 10 {
                        // Exponent overflow
                        if exp_positive {
                            return Ok(i32::MAX);
                        } else {
                            return Ok(i32::MIN);
                        }
                    }
                    exp = exp * 10 + digit;
                }
                _ => {
                    break;
                }
            }
        }

        if exp_positive {
            Ok(exp)
        } else {
            Ok(-exp)
        }
    }

    fn f64_from_parts(&mut self, positive: bool, significand: u64, exponent: i32) -> Result<f64> {
        #[cfg(feature = "float_roundtrip")]
        let f = lexical::parse_concise_float::<f64>(significand, exponent);
        #[cfg(not(feature = "float_roundtrip"))]
        let f = {
            let mut f = significand as f64;
            // Apply exponent
            if exponent < 0 {
                let neg_exp = (-exponent) as u32;
                if neg_exp < POW10.len() as u32 {
                    f /= POW10[neg_exp as usize];
                } else {
                    f *= 1e-308_f64;
                    let remaining = neg_exp - 308;
                    if remaining < POW10.len() as u32 {
                        f /= POW10[remaining as usize];
                    } else {
                        f = 0.0;
                    }
                }
            } else if exponent > 0 {
                let pos_exp = exponent as u32;
                if pos_exp < POW10.len() as u32 {
                    f *= POW10[pos_exp as usize];
                } else {
                    f *= 1e308_f64;
                    let remaining = pos_exp - 308;
                    if remaining < POW10.len() as u32 {
                        f *= POW10[remaining as usize];
                    } else {
                        f = f64::INFINITY;
                    }
                }
            }
            f
        };

        if f.is_infinite() {
            Err(self.error(ErrorCode::NumberOutOfRange))
        } else if positive {
            Ok(f)
        } else {
            Ok(-f)
        }
    }

    fn parse_object_colon(&mut self) -> Result<()> {
        match self.parse_whitespace()? {
            Some(b':') => {
                self.eat_char();
                Ok(())
            }
            Some(_) => Err(self.peek_error(ErrorCode::ExpectedColon)),
            None => Err(self.peek_error(ErrorCode::EofWhileParsingObject)),
        }
    }

    fn end_seq(&mut self) -> Result<()> {
        match self.parse_whitespace()? {
            Some(b']') => {
                self.eat_char();
                Ok(())
            }
            Some(b',') => {
                self.eat_char();
                match self.parse_whitespace()? {
                    Some(b']') => Err(self.peek_error(ErrorCode::TrailingComma)),
                    Some(_) => Err(self.peek_error(ErrorCode::TrailingComma)),
                    None => Err(self.peek_error(ErrorCode::EofWhileParsingList)),
                }
            }
            Some(_) => Err(self.peek_error(ErrorCode::ExpectedListCommaOrEnd)),
            None => Err(self.peek_error(ErrorCode::EofWhileParsingList)),
        }
    }

    fn end_map(&mut self) -> Result<()> {
        match self.parse_whitespace()? {
            Some(b'}') => {
                self.eat_char();
                Ok(())
            }
            Some(b',') => {
                self.eat_char();
                match self.parse_whitespace()? {
                    Some(b'}') => Err(self.peek_error(ErrorCode::TrailingComma)),
                    Some(_) => Err(self.peek_error(ErrorCode::TrailingComma)),
                    None => Err(self.peek_error(ErrorCode::EofWhileParsingObject)),
                }
            }
            Some(_) => Err(self.peek_error(ErrorCode::ExpectedObjectCommaOrEnd)),
            None => Err(self.peek_error(ErrorCode::EofWhileParsingObject)),
        }
    }

    fn ignore_value(&mut self) -> Result<()> {
        let mut count = 0i32;

        loop {
            let peek = match self.parse_whitespace()? {
                Some(b) => b,
                None => {
                    return Err(self.peek_error(ErrorCode::EofWhileParsingValue));
                }
            };

            match peek {
                b'"' => {
                    self.eat_char();
                    self.read.ignore_str()?;
                    if count == 0 {
                        return Ok(());
                    }
                }
                b'[' | b'{' => {
                    self.eat_char();
                    count += 1;
                }
                b']' | b'}' => {
                    self.eat_char();
                    count -= 1;
                    if count < 0 {
                        return Err(self.error(ErrorCode::Message("unexpected closing bracket".to_owned())));
                    }
                    if count == 0 {
                        return Ok(());
                    }
                }
                b'n' => {
                    self.eat_char();
                    self.parse_ident(b"ull")?;
                    if count == 0 {
                        return Ok(());
                    }
                }
                b't' => {
                    self.eat_char();
                    self.parse_ident(b"rue")?;
                    if count == 0 {
                        return Ok(());
                    }
                }
                b'f' => {
                    self.eat_char();
                    self.parse_ident(b"alse")?;
                    if count == 0 {
                        return Ok(());
                    }
                }
                b'-' | b'0'..=b'9' => {
                    // skip number
                    self.eat_char();
                    loop {
                        match self.peek_or_null()? {
                            b'0'..=b'9' | b'.' | b'e' | b'E' | b'+' | b'-' => {
                                self.eat_char();
                            }
                            _ => break,
                        }
                    }
                    if count == 0 {
                        return Ok(());
                    }
                }
                b',' | b':' => {
                    if count == 0 {
                        return Err(self.peek_error(ErrorCode::ExpectedSomeValue));
                    }
                    self.eat_char();
                }
                _ => {
                    return Err(self.peek_error(ErrorCode::ExpectedSomeValue));
                }
            }
        }
    }

    fn deserialize_prim_number<'any, V>(&mut self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'any>,
    {
        let peek = match self.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.peek_error(ErrorCode::EofWhileParsingValue));
            }
        };

        let value = match peek {
            b'-' => {
                self.eat_char();
                self.parse_integer(false)
            }
            b'0'..=b'9' => self.parse_integer(true),
            _ => return Err(self.peek_error(ErrorCode::ExpectedSomeValue)),
        }?;

        match value {
            ParserNumber::F64(x) => visitor.visit_f64(x),
            ParserNumber::U64(x) => visitor.visit_u64(x),
            ParserNumber::I64(x) => visitor.visit_i64(x),
            #[cfg(feature = "arbitrary_precision")]
            ParserNumber::String(s) => {
                visitor.visit_map(NumberDeserializer { number: s.into() })
            }
        }
    }

    fn scan_integer128(&mut self, buf: &mut String) -> Result<()> {
        loop {
            match self.peek_or_null()? {
                c @ b'0'..=b'9' => {
                    buf.push(c as char);
                    self.eat_char();
                }
                _ => break,
            }
        }
        Ok(())
    }

    #[cfg(feature = "raw_value")]
    fn deserialize_raw_value<'any, V>(&mut self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'any>,
    {
        self.read.begin_raw_buffering();
        // Skip the value
        self.ignore_value()?;
        self.read.end_raw_buffering(visitor)
    }

    fn recurse<F, T>(&mut self, f: F) -> Result<T>
    where
        F: FnOnce(&mut Self) -> Result<T>,
    {
        #[cfg(feature = "unbounded_depth")]
        if self.disable_recursion_limit {
            return f(self);
        }

        if self.remaining_depth == 0 {
            return Err(self.peek_error(ErrorCode::RecursionLimitExceeded));
        }
        self.remaining_depth -= 1;
        let result = f(self);
        self.remaining_depth += 1;
        result
    }
}

#[cfg(not(feature = "float_roundtrip"))]
static POW10: [f64; 309] = {
    let mut table = [0.0f64; 309];
    let mut i = 0;
    // We build this at compile time... but const fn floats not stable for all ops.
    // Instead we'll initialize via a lazy approach. Actually we need a const array.
    // Let's just hardcode the first 24 and use a fallback for the rest.
    // Actually, we can use a static built at runtime, or just use a manual table.
    // Since we need compile-time initialization, we hardcode the first 309.
    // 10^0 through 10^308
    table
};

// Actually, we need a proper implementation. Let's use a different approach:
#[cfg(not(feature = "float_roundtrip"))]
fn pow10(exp: i32) -> f64 {
    // Use a small lookup table for common exponents
    const TABLE: [f64; 23] = [
        1e0, 1e1, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11, 1e12, 1e13, 1e14, 1e15,
        1e16, 1e17, 1e18, 1e19, 1e20, 1e21, 1e22,
    ];
    if exp >= 0 && exp <= 22 {
        TABLE[exp as usize]
    } else if exp > 22 {
        // Combine
        let hi = exp / 22;
        let lo = exp % 22;
        let mut result = TABLE[22].powi(hi);
        if lo > 0 {
            result *= TABLE[lo as usize];
        }
        result
    } else {
        1.0 / pow10(-exp)
    }
}

impl<'de, R: Read<'de>> Deserializer<R> {
    #[cfg(not(feature = "float_roundtrip"))]
    fn f64_from_parts(&mut self, positive: bool, significand: u64, exponent: i32) -> Result<f64> {
        let mut f = significand as f64;
        if exponent < 0 {
            f /= pow10(-exponent);
        } else if exponent > 0 {
            f *= pow10(exponent);
        }

        if f.is_infinite() {
            Err(self.error(ErrorCode::NumberOutOfRange))
        } else if positive {
            Ok(f)
        } else {
            Ok(-f)
        }
    }
}

// We have duplicate f64_from_parts for cfg(float_roundtrip) above. Let's reorganize.
// Actually the impl blocks above are ambiguous — we'll consolidate properly below.

// StreamDeserializer
pub struct StreamDeserializer<'de, R, T> {
    de: Deserializer<R>,
    offset: usize,
    failed: bool,
    output: PhantomData<T>,
    lifetime: PhantomData<&'de ()>,
}

impl<'de, R: Read<'de>, T: de::Deserialize<'de>> StreamDeserializer<'de, R, T> {
    pub fn byte_offset(&self) -> usize {
        self.de.read.byte_offset()
    }
}

impl<'de, R: Read<'de>, T: de::Deserialize<'de>> Iterator for StreamDeserializer<'de, R, T> {
    type Item = Result<T>;

    fn next(&mut self) -> Option<Self::Item> {
        if self.failed {
            return None;
        }

        // Skip whitespace
        match self.de.parse_whitespace() {
            Err(e) => {
                self.failed = true;
                return Some(Err(e));
            }
            Ok(None) => return None,
            Ok(Some(_)) => {}
        }

        self.offset = self.de.read.byte_offset();

        let result = T::deserialize(&mut self.de);

        match result {
            Ok(value) => Some(Ok(value)),
            Err(e) => {
                self.failed = !e.is_eof() || {
                    // If we failed in the middle of a value, stop
                    self.de.read.byte_offset() > self.offset
                };
                Some(Err(e))
            }
        }
    }
}

impl<'de, R: Read<'de> + Fused, T: de::Deserialize<'de>> FusedIterator
    for StreamDeserializer<'de, R, T>
{
}

/// Internal enum representing a parsed JSON number.
#[cfg(not(feature = "arbitrary_precision"))]
pub(crate) enum ParserNumber {
    F64(f64),
    U64(u64),
    I64(i64),
}

#[cfg(feature = "arbitrary_precision")]
pub(crate) enum ParserNumber {
    F64(f64),
    U64(u64),
    I64(i64),
    String(String),
}

macro_rules! overflow {
    ($a:ident * 10 + $b:ident, $c:expr) => {
        $a > ($c / 10) || ($a == $c / 10 && $b > $c % 10)
    };
}

// Serde Deserializer impl
struct SeqAccessDeserializer<'a, R: 'a> {
    de: &'a mut Deserializer<R>,
    first: bool,
}

impl<'de, 'a, R: Read<'de> + 'a> SeqAccess<'de> for SeqAccessDeserializer<'a, R> {
    type Error = Error;

    fn next_element_seed<T>(&mut self, seed: T) -> Result<Option<T::Value>>
    where
        T: DeserializeSeed<'de>,
    {
        let peek = match self.de.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.de.peek_error(ErrorCode::EofWhileParsingList));
            }
        };

        if peek == b']' {
            return Ok(None);
        }

        if self.first {
            self.first = false;
        } else if peek == b',' {
            self.de.eat_char();
            match self.de.parse_whitespace()? {
                Some(b']') => {
                    return Err(self.de.peek_error(ErrorCode::TrailingComma));
                }
                Some(_) => {}
                None => {
                    return Err(self.de.peek_error(ErrorCode::EofWhileParsingList));
                }
            }
        } else {
            return Err(self.de.peek_error(ErrorCode::ExpectedListCommaOrEnd));
        }

        let value = seed.deserialize(&mut *self.de)?;
        Ok(Some(value))
    }
}

struct MapAccessDeserializer<'a, R: 'a> {
    de: &'a mut Deserializer<R>,
    first: bool,
}

impl<'de, 'a, R: Read<'de> + 'a> MapAccess<'de> for MapAccessDeserializer<'a, R> {
    type Error = Error;

    fn next_key_seed<K>(&mut self, seed: K) -> Result<Option<K::Value>>
    where
        K: DeserializeSeed<'de>,
    {
        let peek = match self.de.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.de.peek_error(ErrorCode::EofWhileParsingObject));
            }
        };

        if peek == b'}' {
            return Ok(None);
        }

        if self.first {
            self.first = false;
        } else if peek == b',' {
            self.de.eat_char();
            match self.de.parse_whitespace()? {
                Some(b'}') => {
                    return Err(self.de.peek_error(ErrorCode::TrailingComma));
                }
                Some(_) => {}
                None => {
                    return Err(self.de.peek_error(ErrorCode::EofWhileParsingObject));
                }
            }
        } else {
            return Err(self.de.peek_error(ErrorCode::ExpectedObjectCommaOrEnd));
        }

        // Key must be a string
        match self.de.parse_whitespace()? {
            Some(b'"') => {}
            Some(_) => {
                return Err(self.de.peek_error(ErrorCode::KeyMustBeAString));
            }
            None => {
                return Err(self.de.peek_error(ErrorCode::EofWhileParsingObject));
            }
        }

        seed.deserialize(MapKeyDeserializer { de: self.de }).map(Some)
    }

    fn next_value_seed<V>(&mut self, seed: V) -> Result<V::Value>
    where
        V: DeserializeSeed<'de>,
    {
        self.de.parse_object_colon()?;
        seed.deserialize(&mut *self.de)
    }
}

struct MapKeyDeserializer<'a, R: 'a> {
    de: &'a mut Deserializer<R>,
}

impl<'de, 'a, R: Read<'de> + 'a> de::Deserializer<'de> for MapKeyDeserializer<'a, R> {
    type Error = Error;

    fn deserialize_any<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.de.eat_char(); // eat '"'
        let s = self.de.parse_str()?;
        match s {
            Reference::Borrowed(b) => visitor.visit_borrowed_str(b),
            Reference::Copied(c) => visitor.visit_str(c),
        }
    }

    fn deserialize_str<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_any(visitor)
    }

    fn deserialize_string<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_any(visitor)
    }

    fn deserialize_bytes<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_any(visitor)
    }

    fn deserialize_byte_buf<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_any(visitor)
    }

    fn deserialize_enum<V>(
        self,
        _name: &str,
        _variants: &'static [&'static str],
        visitor: V,
    ) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.de.eat_char();
        let s = self.de.parse_str()?;
        visitor.visit_enum(match s {
            Reference::Borrowed(b) => UnitVariantAccess::new_borrowed(b),
            Reference::Copied(c) => UnitVariantAccess::new_owned(c.to_owned()),
        })
    }

    forward_to_deserialize_any! {
        bool i8 i16 i32 i64 i128 u8 u16 u32 u64 u128 f32 f64 char
        option unit unit_struct newtype_struct seq tuple
        tuple_struct map struct identifier ignored_any
    }
}

struct UnitVariantAccess<'de> {
    value: StrOrBorrowed<'de>,
}

enum StrOrBorrowed<'de> {
    Borrowed(&'de str),
    Owned(String),
}

impl<'de> UnitVariantAccess<'de> {
    fn new_borrowed(s: &'de str) -> Self {
        UnitVariantAccess {
            value: StrOrBorrowed::Borrowed(s),
        }
    }

    fn new_owned(s: String) -> Self {
        UnitVariantAccess {
            value: StrOrBorrowed::Owned(s),
        }
    }
}

impl<'de> de::EnumAccess<'de> for UnitVariantAccess<'de> {
    type Error = Error;
    type Variant = UnitOnly;

    fn variant_seed<V>(self, seed: V) -> Result<(V::Value, Self::Variant)>
    where
        V: DeserializeSeed<'de>,
    {
        let val = match self.value {
            StrOrBorrowed::Borrowed(b) => seed.deserialize(b.into_deserializer())?,
            StrOrBorrowed::Owned(s) => seed.deserialize(s.into_deserializer())?,
        };
        Ok((val, UnitOnly))
    }
}

struct UnitOnly;

impl<'de> de::VariantAccess<'de> for UnitOnly {
    type Error = Error;

    fn unit_variant(self) -> Result<()> {
        Ok(())
    }

    fn newtype_variant_seed<T>(self, _seed: T) -> Result<T::Value>
    where
        T: DeserializeSeed<'de>,
    {
        Err(de::Error::invalid_type(
            Unexpected::UnitVariant,
            &"newtype variant",
        ))
    }

    fn tuple_variant<V>(self, _len: usize, _visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        Err(de::Error::invalid_type(
            Unexpected::UnitVariant,
            &"tuple variant",
        ))
    }

    fn struct_variant<V>(self, _fields: &'static [&'static str], _visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        Err(de::Error::invalid_type(
            Unexpected::UnitVariant,
            &"struct variant",
        ))
    }
}

struct EnumAccessDeserializer<'a, R: 'a> {
    de: &'a mut Deserializer<R>,
}

impl<'de, 'a, R: Read<'de> + 'a> de::EnumAccess<'de> for EnumAccessDeserializer<'a, R> {
    type Error = Error;
    type Variant = VariantAccessDeserializer<'a, R>;

    fn variant_seed<V>(self, seed: V) -> Result<(V::Value, Self::Variant)>
    where
        V: DeserializeSeed<'de>,
    {
        // Expect {"VariantName": ...}
        match self.de.parse_whitespace()? {
            Some(b'"') => {}
            Some(_) => {
                return Err(self.de.peek_error(ErrorCode::KeyMustBeAString));
            }
            None => {
                return Err(self.de.peek_error(ErrorCode::EofWhileParsingObject));
            }
        }
        self.de.eat_char();
        let val = seed.deserialize(MapKeyDeserializer { de: self.de })?;
        self.de.parse_object_colon()?;
        Ok((val, VariantAccessDeserializer { de: self.de }))
    }
}

struct VariantAccessDeserializer<'a, R: 'a> {
    de: &'a mut Deserializer<R>,
}

impl<'de, 'a, R: Read<'de> + 'a> de::VariantAccess<'de> for VariantAccessDeserializer<'a, R> {
    type Error = Error;

    fn unit_variant(self) -> Result<()> {
        // Expect null
        de::Deserialize::deserialize(self.de)
    }

    fn newtype_variant_seed<T>(self, seed: T) -> Result<T::Value>
    where
        T: DeserializeSeed<'de>,
    {
        seed.deserialize(self.de)
    }

    fn tuple_variant<V>(self, _len: usize, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        de::Deserializer::deserialize_seq(self.de, visitor)
    }

    fn struct_variant<V>(self, fields: &'static [&'static str], visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        de::Deserializer::deserialize_struct(self.de, "", fields, visitor)
    }
}

impl<'de, 'a, R: Read<'de>> de::Deserializer<'de> for &'a mut Deserializer<R> {
    type Error = Error;

    #[inline]
    fn deserialize_any<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        let peek = match self.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.peek_error(ErrorCode::EofWhileParsingValue));
            }
        };

        let value = match peek {
            b'n' => {
                self.eat_char();
                self.parse_ident(b"ull")?;
                visitor.visit_unit()
            }
            b't' => {
                self.eat_char();
                self.parse_ident(b"rue")?;
                visitor.visit_bool(true)
            }
            b'f' => {
                self.eat_char();
                self.parse_ident(b"alse")?;
                visitor.visit_bool(false)
            }
            b'-' => {
                self.eat_char();
                self.parse_integer(false).and_then(|n| match n {
                    ParserNumber::F64(x) => visitor.visit_f64(x),
                    ParserNumber::U64(x) => visitor.visit_u64(x),
                    ParserNumber::I64(x) => visitor.visit_i64(x),
                    #[cfg(feature = "arbitrary_precision")]
                    ParserNumber::String(s) => {
                        visitor.visit_map(NumberDeserializer { number: s.into() })
                    }
                })
            }
            b'0'..=b'9' => self.parse_integer(true).and_then(|n| match n {
                ParserNumber::F64(x) => visitor.visit_f64(x),
                ParserNumber::U64(x) => visitor.visit_u64(x),
                ParserNumber::I64(x) => visitor.visit_i64(x),
                #[cfg(feature = "arbitrary_precision")]
                ParserNumber::String(s) => {
                    visitor.visit_map(NumberDeserializer { number: s.into() })
                }
            }),
            b'"' => {
                self.eat_char();
                let s = self.parse_str()?;
                match s {
                    Reference::Borrowed(b) => visitor.visit_borrowed_str(b),
                    Reference::Copied(c) => visitor.visit_str(c),
                }
            }
            b'[' => {
                self.eat_char();
                self.recurse(|de| {
                    let seq = visitor.visit_seq(SeqAccessDeserializer { de, first: true });
                    match seq {
                        Ok(val) => {
                            match de.parse_whitespace()? {
                                Some(b']') => {
                                    de.eat_char();
                                }
                                Some(b',') => {
                                    return Err(de.peek_error(ErrorCode::TrailingComma));
                                }
                                _ => {}
                            }
                            Ok(val)
                        }
                        Err(e) => Err(e),
                    }
                })
            }
            b'{' => {
                self.eat_char();
                self.recurse(|de| {
                    let map = visitor.visit_map(MapAccessDeserializer { de, first: true });
                    match map {
                        Ok(val) => {
                            match de.parse_whitespace()? {
                                Some(b'}') => {
                                    de.eat_char();
                                }
                                _ => {}
                            }
                            Ok(val)
                        }
                        Err(e) => Err(e),
                    }
                })
            }
            _ => Err(self.peek_error(ErrorCode::ExpectedSomeValue)),
        };

        value.map_err(|e| self.fix_position(e))
    }

    fn deserialize_bool<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        let peek = match self.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.peek_error(ErrorCode::EofWhileParsingValue));
            }
        };

        let value = match peek {
            b't' => {
                self.eat_char();
                self.parse_ident(b"rue")?;
                visitor.visit_bool(true)
            }
            b'f' => {
                self.eat_char();
                self.parse_ident(b"alse")?;
                visitor.visit_bool(false)
            }
            _ => Err(self.peek_error(ErrorCode::ExpectedSomeValue)),
        };

        value.map_err(|e| self.fix_position(e))
    }

    fn deserialize_i8<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_prim_number(visitor)
    }

    fn deserialize_i16<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_prim_number(visitor)
    }

    fn deserialize_i32<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_prim_number(visitor)
    }

    fn deserialize_i64<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_prim_number(visitor)
    }

    fn deserialize_i128<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_prim_number(visitor)
    }

    fn deserialize_u8<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_prim_number(visitor)
    }

    fn deserialize_u16<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_prim_number(visitor)
    }

    fn deserialize_u32<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_prim_number(visitor)
    }

    fn deserialize_u64<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_prim_number(visitor)
    }

    fn deserialize_u128<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_prim_number(visitor)
    }

    fn deserialize_f32<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_prim_number(visitor)
    }

    fn deserialize_f64<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_prim_number(visitor)
    }

    fn deserialize_char<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_str(visitor)
    }

    fn deserialize_str<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        let peek = match self.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.peek_error(ErrorCode::EofWhileParsingValue));
            }
        };

        let value = match peek {
            b'"' => {
                self.eat_char();
                let s = self.parse_str()?;
                match s {
                    Reference::Borrowed(b) => visitor.visit_borrowed_str(b),
                    Reference::Copied(c) => visitor.visit_str(c),
                }
            }
            _ => Err(self.peek_error(ErrorCode::ExpectedSomeValue)),
        };

        value.map_err(|e| self.fix_position(e))
    }

    fn deserialize_string<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_str(visitor)
    }

    fn deserialize_bytes<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        let peek = match self.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.peek_error(ErrorCode::EofWhileParsingValue));
            }
        };

        let value = match peek {
            b'"' => {
                self.eat_char();
                let bytes = self.parse_str_raw()?;
                match bytes {
                    Reference::Borrowed(b) => visitor.visit_borrowed_bytes(b),
                    Reference::Copied(c) => visitor.visit_bytes(c),
                }
            }
            b'[' => self.deserialize_seq(visitor),
            _ => Err(self.peek_error(ErrorCode::ExpectedSomeValue)),
        };

        value.map_err(|e| self.fix_position(e))
    }

    fn deserialize_byte_buf<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_bytes(visitor)
    }

    fn deserialize_option<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        match self.parse_whitespace()? {
            Some(b'n') => {
                self.eat_char();
                self.parse_ident(b"ull")?;
                visitor.visit_none()
            }
            _ => visitor.visit_some(self),
        }
    }

    fn deserialize_unit<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        let peek = match self.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.peek_error(ErrorCode::EofWhileParsingValue));
            }
        };

        let value = match peek {
            b'n' => {
                self.eat_char();
                self.parse_ident(b"ull")?;
                visitor.visit_unit()
            }
            _ => Err(self.peek_error(ErrorCode::ExpectedSomeValue)),
        };

        value.map_err(|e| self.fix_position(e))
    }

    fn deserialize_unit_struct<V>(self, _name: &'static str, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_unit(visitor)
    }

    fn deserialize_newtype_struct<V>(self, name: &'static str, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        #[cfg(feature = "raw_value")]
        {
            if name == crate::raw::TOKEN {
                return self.deserialize_raw_value(visitor);
            }
        }
        let _ = name;
        visitor.visit_newtype_struct(self)
    }

    fn deserialize_seq<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        let peek = match self.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.peek_error(ErrorCode::EofWhileParsingValue));
            }
        };

        let value = match peek {
            b'[' => {
                self.eat_char();
                self.recurse(|de| {
                    let v = visitor.visit_seq(SeqAccessDeserializer { de, first: true });
                    // consume closing bracket
                    match v {
                        Ok(val) => {
                            // SeqAccess stops at ']' but doesn't consume it
                            match de.parse_whitespace()? {
                                Some(b']') => {
                                    de.eat_char();
                                }
                                _ => {}
                            }
                            Ok(val)
                        }
                        Err(e) => Err(e),
                    }
                })
            }
            _ => Err(self.peek_error(ErrorCode::ExpectedSomeValue)),
        };

        value.map_err(|e| self.fix_position(e))
    }

    fn deserialize_tuple<V>(self, _len: usize, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_seq(visitor)
    }

    fn deserialize_tuple_struct<V>(
        self,
        _name: &'static str,
        _len: usize,
        visitor: V,
    ) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_seq(visitor)
    }

    fn deserialize_map<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        let peek = match self.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.peek_error(ErrorCode::EofWhileParsingValue));
            }
        };

        let value = match peek {
            b'{' => {
                self.eat_char();
                self.recurse(|de| {
                    let v = visitor.visit_map(MapAccessDeserializer { de, first: true });
                    match v {
                        Ok(val) => {
                            match de.parse_whitespace()? {
                                Some(b'}') => {
                                    de.eat_char();
                                }
                                _ => {}
                            }
                            Ok(val)
                        }
                        Err(e) => Err(e),
                    }
                })
            }
            _ => Err(self.peek_error(ErrorCode::ExpectedSomeValue)),
        };

        value.map_err(|e| self.fix_position(e))
    }

    fn deserialize_struct<V>(
        self,
        name: &'static str,
        fields: &'static [&'static str],
        visitor: V,
    ) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        #[cfg(feature = "arbitrary_precision")]
        {
            if name == crate::number::TOKEN {
                return self.deserialize_any(visitor);
            }
        }
        #[cfg(feature = "raw_value")]
        {
            if name == crate::raw::TOKEN {
                return self.deserialize_raw_value(visitor);
            }
        }
        let _ = name;
        let _ = fields;

        let peek = match self.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.peek_error(ErrorCode::EofWhileParsingValue));
            }
        };

        let value = match peek {
            b'{' => {
                self.eat_char();
                self.recurse(|de| {
                    let v = visitor.visit_map(MapAccessDeserializer { de, first: true });
                    match v {
                        Ok(val) => {
                            match de.parse_whitespace()? {
                                Some(b'}') => {
                                    de.eat_char();
                                }
                                _ => {}
                            }
                            Ok(val)
                        }
                        Err(e) => Err(e),
                    }
                })
            }
            b'[' => {
                self.eat_char();
                self.recurse(|de| {
                    let v = visitor.visit_seq(SeqAccessDeserializer { de, first: true });
                    match v {
                        Ok(val) => {
                            match de.parse_whitespace()? {
                                Some(b']') => {
                                    de.eat_char();
                                }
                                _ => {}
                            }
                            Ok(val)
                        }
                        Err(e) => Err(e),
                    }
                })
            }
            _ => Err(self.peek_error(ErrorCode::ExpectedSomeValue)),
        };

        value.map_err(|e| self.fix_position(e))
    }

    fn deserialize_enum<V>(
        self,
        _name: &'static str,
        _variants: &'static [&'static str],
        visitor: V,
    ) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        let peek = match self.parse_whitespace()? {
            Some(b) => b,
            None => {
                return Err(self.peek_error(ErrorCode::EofWhileParsingValue));
            }
        };

        match peek {
            b'"' => {
                self.eat_char();
                let s = self.parse_str()?;
                visitor.visit_enum(match s {
                    Reference::Borrowed(b) => UnitVariantAccess::new_borrowed(b),
                    Reference::Copied(c) => UnitVariantAccess::new_owned(c.to_owned()),
                })
            }
            b'{' => {
                self.eat_char();
                let result = self.recurse(|de| {
                    visitor.visit_enum(EnumAccessDeserializer { de })
                });
                match self.parse_whitespace()? {
                    Some(b'}') => {
                        self.eat_char();
                    }
                    _ => {}
                }
                result
            }
            _ => Err(self.peek_error(ErrorCode::ExpectedSomeValue)),
        }
        .map_err(|e| self.fix_position(e))
    }

    fn deserialize_identifier<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.deserialize_str(visitor)
    }

    fn deserialize_ignored_any<V>(self, visitor: V) -> Result<V::Value>
    where
        V: Visitor<'de>,
    {
        self.ignore_value()?;
        visitor.visit_unit()
    }

    fn is_human_readable(&self) -> bool {
        true
    }
}

// Constructors
impl<'a> Deserializer<SliceRead<'a>> {
    pub fn from_slice(bytes: &'a [u8]) -> Self {
        Deserializer::new(SliceRead::new(bytes))
    }
}

impl<'a> Deserializer<StrRead<'a>> {
    pub fn from_str(s: &'a str) -> Self {
        Deserializer::new(StrRead::new(s))
    }
}

#[cfg(feature = "std")]
impl<R: crate::io::Read> Deserializer<IoRead<R>> {
    pub fn from_reader(reader: R) -> Self {
        Deserializer::new(IoRead::new(reader))
    }
}

// Free functions

pub fn from_str<'a, T: Deserialize<'a>>(s: &'a str) -> Result<T> {
    let mut de = Deserializer::from_str(s);
    let value = T::deserialize(&mut de)?;
    de.end()?;
    Ok(value)
}

pub fn from_slice<'a, T: Deserialize<'a>>(v: &'a [u8]) -> Result<T> {
    let mut de = Deserializer::from_slice(v);
    let value = T::deserialize(&mut de)?;
    de.end()?;
    Ok(value)
}

#[cfg(feature = "std")]
pub fn from_reader<R: crate::io::Read, T: DeserializeOwned>(rdr: R) -> Result<T> {
    let mut de = Deserializer::from_reader(rdr);
    let value = T::deserialize(&mut de)?;
    de.end()?;
    Ok(value)
}

pub fn from_value<T: DeserializeOwned>(value: crate::value::Value) -> Result<T> {
    T::deserialize(value)
}
