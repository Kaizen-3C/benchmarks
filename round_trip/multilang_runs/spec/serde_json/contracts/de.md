# Contract: src/de.rs

## Public Types

### `Deserializer<R>`
A JSON deserializer generic over a `Read` source.

Fields (private): `read: R`, `scratch: Vec<u8>`, `remaining_depth: u8`, optionally `single_precision: bool` (float_roundtrip), `disable_recursion_limit: bool` (unbounded_depth).

**`Deserializer::new(read: R) -> Self`** — constructs with depth=128.
**`Deserializer::from_reader(reader: R) -> Self`** (std only) — wraps `IoRead`.
**`Deserializer::from_slice(bytes: &'a [u8]) -> Self`** — wraps `SliceRead`.
**`Deserializer::from_str(s: &'a str) -> Self`** — wraps `StrRead`.
**`fn end(&mut self) -> Result<()>`** — asserts no trailing non-whitespace.
**`fn into_iter<T>(self) -> StreamDeserializer<'de, R, T>`** — creates streaming iterator.
**`fn disable_recursion_limit(&mut self)`** (unbounded_depth) — disables depth check.

Implements `serde::Deserializer<'de>` for all standard types.

### `StreamDeserializer<'de, R, T>`
Iterator yielding `Result<T>` from a stream of JSON values. Tracks byte offset.

**`fn byte_offset(&self) -> usize`** — returns current byte position.

Implements `Iterator<Item = Result<T>>` and `FusedIterator` (when R: Fused).

### Re-exported from `read`:
**`pub use crate::read::{Read, SliceRead, StrRead}`**
**`pub use crate::read::IoRead`** (std only)

## Free Functions
**`from_str<'a, T: Deserialize<'a>>(s: &'a str) -> Result<T>`**
**`from_slice<'a, T: Deserialize<'a>>(v: &'a [u8]) -> Result<T>`**
**`from_reader<R: io::Read, T: DeserializeOwned>(rdr: R) -> Result<T>`** (std only)
**`from_value<T: DeserializeOwned>(value: Value) -> Result<T>`**

## Internal Types (pub(crate))
**`ParserNumber`** — enum: `F64(f64)`, `U64(u64)`, `I64(i64)`, `String(String)` (arbitrary_precision).
