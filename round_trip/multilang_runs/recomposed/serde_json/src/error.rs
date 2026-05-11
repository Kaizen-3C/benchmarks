use core::fmt;
use core::result;

use crate::io;

/// A result type alias for serde_json errors.
pub type Result<T> = result::Result<T, Error>;

/// Error type for serde_json.
pub struct Error {
    inner: Box<ErrorImpl>,
}

struct ErrorImpl {
    code: ErrorCode,
    line: usize,
    column: usize,
}

#[derive(Debug)]
pub(crate) enum ErrorCode {
    /// Catchall for syntax error messages
    Message(Box<str>),

    /// Some I/O error occurred while serializing or deserializing.
    Io(io::Error),

    /// EOF while parsing a list.
    EofWhileParsingList,

    /// EOF while parsing an object.
    EofWhileParsingObject,

    /// EOF while parsing a string.
    EofWhileParsingString,

    /// EOF while parsing a JSON value.
    EofWhileParsingValue,

    /// Expected this character to be a `':'`.
    ExpectedColon,

    /// Expected this character to be either a `','` or a `']'`.
    ExpectedListCommaOrEnd,

    /// Expected this character to be either a `','` or a `'}'`.
    ExpectedObjectCommaOrEnd,

    /// Expected to parse either a `true`, `false`, or a `null`.
    ExpectedSomeIdent,

    /// Expected this character to start a JSON value.
    ExpectedSomeValue,

    /// Invalid hex escape code.
    InvalidEscape,

    /// Invalid number.
    InvalidNumber,

    /// Number is bigger than the maximum value of its type.
    NumberOutOfRange,

    /// Invalid unicode code point.
    InvalidUnicodeCodePoint,

    /// Control character found while parsing a string.
    ControlCharacterWhileParsingString,

    /// Object key is not a string.
    KeyMustBeAString,

    /// Lone leading surrogate in hex escape.
    LoneLeadingSurrogateInHexEscape,

    /// JSON has a comma after the last value in an array or map.
    TrailingComma,

    /// JSON has non-whitespace trailing characters after the value.
    TrailingCharacters,

    /// Unexpected end of hex escape.
    UnexpectedEndOfHexEscape,

    /// Encountered nesting of JSON maps and arrays more than 128 layers deep.
    RecursionLimitExceeded,
}

/// Categorizes the cause of a `serde_json::Error`.
#[derive(Copy, Clone, PartialEq, Eq, Debug)]
pub enum Category {
    /// The error was caused by a failure to read or write bytes on an I/O stream.
    Io,

    /// The error was caused by input that was not syntactically valid JSON.
    Syntax,

    /// The error was caused by input data that was semantically incorrect.
    ///
    /// For example, JSON containing a number that is semantically incorrect
    /// when parsed as the Rust type `u64`.
    Data,

    /// The error was caused by prematurely reaching the end of the input data.
    Eof,
}

impl Error {
    /// One-based line number at which the error was detected.
    ///
    /// Characters in the first line of the input (before the first newline
    /// character) are in line 1.
    pub fn line(&self) -> usize {
        self.inner.line
    }

    /// One-based column number at which the error was detected.
    ///
    /// The first character in the input and any characters immediately
    /// following a newline character are in column 1.
    pub fn column(&self) -> usize {
        self.inner.column
    }

    /// Categorizes the cause of this error.
    pub fn classify(&self) -> Category {
        match self.inner.code {
            ErrorCode::Message(_) => Category::Data,
            ErrorCode::Io(_) => Category::Io,
            ErrorCode::EofWhileParsingList
            | ErrorCode::EofWhileParsingObject
            | ErrorCode::EofWhileParsingString
            | ErrorCode::EofWhileParsingValue => Category::Eof,
            ErrorCode::ExpectedColon
            | ErrorCode::ExpectedListCommaOrEnd
            | ErrorCode::ExpectedObjectCommaOrEnd
            | ErrorCode::ExpectedSomeIdent
            | ErrorCode::ExpectedSomeValue
            | ErrorCode::InvalidEscape
            | ErrorCode::InvalidNumber
            | ErrorCode::NumberOutOfRange
            | ErrorCode::InvalidUnicodeCodePoint
            | ErrorCode::ControlCharacterWhileParsingString
            | ErrorCode::KeyMustBeAString
            | ErrorCode::LoneLeadingSurrogateInHexEscape
            | ErrorCode::TrailingComma
            | ErrorCode::TrailingCharacters
            | ErrorCode::UnexpectedEndOfHexEscape
            | ErrorCode::RecursionLimitExceeded => Category::Syntax,
        }
    }

    /// Returns true if this error was caused by a failure to read or write
    /// bytes on an I/O stream.
    pub fn is_io(&self) -> bool {
        self.classify() == Category::Io
    }

    /// Returns true if this error was caused by input that was not
    /// syntactically valid JSON.
    pub fn is_syntax(&self) -> bool {
        self.classify() == Category::Syntax
    }

    /// Returns true if this error was caused by input data that was
    /// semantically incorrect.
    pub fn is_data(&self) -> bool {
        self.classify() == Category::Data
    }

    /// Returns true if this error was caused by prematurely reaching the end
    /// of the input data.
    pub fn is_eof(&self) -> bool {
        self.classify() == Category::Eof
    }

    /// The kind reported by the underlying standard library I/O error, if this
    /// error was caused by a failure to read or write bytes on an I/O stream.
    #[cfg(feature = "std")]
    pub fn io_error_kind(&self) -> Option<io::ErrorKind> {
        if let ErrorCode::Io(ref io_error) = self.inner.code {
            Some(io_error.kind())
        } else {
            None
        }
    }

    pub(crate) fn fix_position<F>(self, f: F) -> Self
    where
        F: FnOnce(ErrorCode) -> Error,
    {
        if self.inner.line == 0 {
            f(self.inner.code)
        } else {
            self
        }
    }
}

impl fmt::Display for ErrorCode {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            ErrorCode::Message(msg) => f.write_str(msg),
            ErrorCode::Io(err) => fmt::Display::fmt(err, f),
            ErrorCode::EofWhileParsingList => f.write_str("EOF while parsing a list"),
            ErrorCode::EofWhileParsingObject => f.write_str("EOF while parsing an object"),
            ErrorCode::EofWhileParsingString => f.write_str("EOF while parsing a string"),
            ErrorCode::EofWhileParsingValue => f.write_str("EOF while parsing a value"),
            ErrorCode::ExpectedColon => f.write_str("expected `:`"),
            ErrorCode::ExpectedListCommaOrEnd => f.write_str("expected `,` or `]`"),
            ErrorCode::ExpectedObjectCommaOrEnd => f.write_str("expected `,` or `}`"),
            ErrorCode::ExpectedSomeIdent => f.write_str("expected ident"),
            ErrorCode::ExpectedSomeValue => f.write_str("expected value"),
            ErrorCode::InvalidEscape => f.write_str("invalid escape"),
            ErrorCode::InvalidNumber => f.write_str("invalid number"),
            ErrorCode::NumberOutOfRange => f.write_str("number out of range"),
            ErrorCode::InvalidUnicodeCodePoint => f.write_str("invalid unicode code point"),
            ErrorCode::ControlCharacterWhileParsingString => {
                f.write_str("control character (\\u0000-\\u001F) found while parsing a string")
            }
            ErrorCode::KeyMustBeAString => f.write_str("key must be a string"),
            ErrorCode::LoneLeadingSurrogateInHexEscape => {
                f.write_str("lone leading surrogate in hex escape")
            }
            ErrorCode::TrailingComma => f.write_str("trailing comma"),
            ErrorCode::TrailingCharacters => f.write_str("trailing characters"),
            ErrorCode::UnexpectedEndOfHexEscape => f.write_str("unexpected end of hex escape"),
            ErrorCode::RecursionLimitExceeded => f.write_str("recursion limit exceeded"),
        }
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        if self.inner.line == 0 {
            fmt::Display::fmt(&self.inner.code, f)
        } else {
            write!(
                f,
                "{} at line {} column {}",
                self.inner.code, self.inner.line, self.inner.column
            )
        }
    }
}

impl fmt::Debug for Error {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(
            f,
            "Error({:?}, line: {}, column: {})",
            self.inner.code.to_string(),
            self.inner.line,
            self.inner.column
        )
    }
}

#[cfg(feature = "std")]
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match &self.inner.code {
            ErrorCode::Io(err) => Some(err),
            _ => None,
        }
    }
}

#[cfg(feature = "std")]
impl From<Error> for io::Error {
    fn from(j: Error) -> Self {
        if let ErrorCode::Io(err) = j.inner.code {
            return err;
        }
        match j.classify() {
            Category::Io => unreachable!(),
            Category::Syntax | Category::Data => {
                io::Error::new(io::ErrorKind::InvalidData, j.to_string())
            }
            Category::Eof => io::Error::new(io::ErrorKind::UnexpectedEof, j.to_string()),
        }
    }
}

impl serde::de::Error for Error {
    #[cold]
    fn custom<T: fmt::Display>(msg: T) -> Error {
        make_error(msg.to_string())
    }

    #[cold]
    fn invalid_type(unexp: serde::de::Unexpected, exp: &dyn serde::de::Expected) -> Self {
        if let serde::de::Unexpected::Unit = unexp {
            Error::custom(format_args!("invalid type: null, expected {}", exp))
        } else {
            Error::custom(format_args!("invalid type: {}, expected {}", unexp, exp))
        }
    }
}

impl serde::ser::Error for Error {
    #[cold]
    fn custom<T: fmt::Display>(msg: T) -> Error {
        make_error(msg.to_string())
    }
}

// Parse "at line N column M" from a message to recover position info
fn make_error(mut msg: String) -> Error {
    let (line, column) = parse_line_col(&mut msg).unwrap_or((0, 0));
    Error {
        inner: Box::new(ErrorImpl {
            code: ErrorCode::Message(msg.into_boxed_str()),
            line,
            column,
        }),
    }
}

fn parse_line_col(msg: &mut String) -> Option<(usize, usize)> {
    let start_of_suffix = match msg.rfind(" at line ") {
        Some(index) => index,
        None => return None,
    };

    // Find " column " after " at line "
    let start_of_column = match msg[start_of_suffix..].find(" column ") {
        Some(index) => start_of_suffix + index,
        None => return None,
    };

    let line_str = &msg[start_of_suffix + " at line ".len()..start_of_column];
    let line: usize = match line_str.parse() {
        Ok(line) => line,
        Err(_) => return None,
    };

    let column_str = &msg[start_of_column + " column ".len()..];
    let column: usize = match column_str.parse() {
        Ok(column) => column,
        Err(_) => return None,
    };

    msg.truncate(start_of_suffix);
    Some((line, column))
}

pub(crate) fn make_io_error(err: io::Error) -> Error {
    Error {
        inner: Box::new(ErrorImpl {
            code: ErrorCode::Io(err),
            line: 0,
            column: 0,
        }),
    }
}

pub(crate) fn error(code: ErrorCode, line: usize, column: usize) -> Error {
    Error {
        inner: Box::new(ErrorImpl { code, line, column }),
    }
}

pub(crate) fn peek_error(code: ErrorCode, position: crate::read::Position) -> Error {
    Error {
        inner: Box::new(ErrorImpl {
            code,
            line: position.line,
            column: position.column,
        }),
    }
}

pub(crate) fn syntax(code: ErrorCode, line: usize, column: usize) -> Error {
    Error {
        inner: Box::new(ErrorImpl { code, line, column }),
    }
}
