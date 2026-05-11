# Contract: src/read.rs

## Public Trait: `Read<'de>` (sealed)

All implementors must provide:
- `fn next(&mut self) -> Result<Option<u8>>`
- `fn peek(&mut self) -> Result<Option<u8>>`
- `fn discard(&mut self)`
- `fn position(&self) -> Position`
- `fn peek_position(&self) -> Position`
- `fn byte_offset(&self) -> usize`
- `fn parse_str<'s>(&'s mut self, scratch: &'s mut Vec<u8>) -> Result<Reference<'de, 's, str>>`
- `fn parse_str_raw<'s>(&'s mut self, scratch: &'s mut Vec<u8>) -> Result<Reference<'de, 's, [u8]>>`
- `fn ignore_str(&mut self) -> Result<()>`
- `fn decode_hex_escape(&mut self) -> Result<u16>`
- `fn begin_raw_buffering(&mut self)` (raw_value)
- `fn end_raw_buffering<V: Visitor<'de>>(&mut self, visitor: V) -> Result<V::Value>` (raw_value)
- `const should_early_return_if_failed: bool`
- `fn set_failed(&mut self, failed: &mut bool)`

## Public Structs

### `Position`
`pub struct Position { pub line: usize, pub column: usize }`

### `Reference<'b, 'c, T: ?Sized + 'static>`
`enum Reference { Borrowed(&'b T), Copied(&'c T) }` — implements `Deref<Target=T>`.

### `SliceRead<'a>`
Reads from `&'a [u8]`. Supports borrowing strings directly from input.

**`fn new(slice: &'a [u8]) -> Self`**

### `StrRead<'a>`
Reads from `&'a str`. Skips UTF-8 validation on unescaped strings.

**`fn new(s: &'a str) -> Self`**

### `IoRead<R: io::Read>` (std only)
Reads from any `io::Read`. Uses `LineColIterator` for position tracking.

**`fn new(reader: R) -> Self`**

## Marker Trait: `Fused` (sealed)
Implemented by `SliceRead` and `StrRead`; enables `FusedIterator` on `StreamDeserializer`.
