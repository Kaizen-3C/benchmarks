# Contract: src/error.rs

## Public Types

### `Error`
Opaque error type. Contains boxed `ErrorImpl { code: ErrorCode, line: usize, column: usize }`.

**`fn line(&self) -> usize`** — 1-based line number (0 if not from parsing).
**`fn column(&self) -> usize`** — 1-based column number.
**`fn classify(&self) -> Category`** — returns the error category.
**`fn is_io(&self) -> bool`** — true if I/O error.
**`fn is_syntax(&self) -> bool`** — true if syntax error.
**`fn is_data(&self) -> bool`** — true if data/semantic error.
**`fn is_eof(&self) -> bool`** — true if unexpected EOF.
**`fn io_error_kind(&self) -> Option<ErrorKind>`** (std only) — underlying I/O error kind.

Implements `Display`, `Debug`, `serde::de::Error`, `serde::ser::Error`, `std::error::Error` (std).
Implements `From<Error> for io::Error` (std): syntax/data → `InvalidData`, eof → `UnexpectedEof`.

### `Category`
`#[derive(Copy, Clone, PartialEq, Eq, Debug)]`
Variants: `Io`, `Syntax`, `Data`, `Eof`.

### `Result<T>`
Type alias: `result::Result<T, Error>`.
