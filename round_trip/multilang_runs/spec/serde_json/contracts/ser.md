# Contract: src/ser.rs

## Public Types

### `Serializer<W, F = CompactFormatter>`
Wraps a writer and formatter.

**`fn new(writer: W) -> Self`** — uses `CompactFormatter`.
**`fn pretty(writer: W) -> Self`** — uses `PrettyFormatter::new()`.
**`fn with_formatter(writer: W, formatter: F) -> Self`**
**`fn into_inner(self) -> W`**

Implements `serde::Serializer` (via `&mut Serializer<W,F>`).

### `PrettyFormatter<'a>`
Indentation-based formatter.

**`fn new() -> Self`** — uses 2-space indent.
**`fn with_indent(indent: &'a [u8]) -> Self`** — custom indent bytes.

### `CompactFormatter`
Produces minified JSON. Unit struct.

### `Formatter` trait
All formatting hooks — `write_null`, `write_bool`, `write_i8/i16/i32/i64/i128`, `write_u8/.../u128`, `write_f32/f64`, `begin_string/end_string`, `write_string_fragment`, `write_char_escape`, `begin_array/end_array`, `begin_array_value/end_array_value`, `begin_object/end_object`, `begin_object_key/end_object_key`, `begin_object_value/end_object_value`, `write_byte_array`.

## Free Functions (std only)
**`fn to_writer<W: io::Write, T: Serialize>(writer: W, value: &T) -> Result<()>`**
**`fn to_writer_pretty<W: io::Write, T: Serialize>(writer: W, value: &T) -> Result<()>`**

## Free Functions (always)
**`fn to_vec<T: Serialize>(value: &T) -> Result<Vec<u8>>`**
**`fn to_vec_pretty<T: Serialize>(value: &T) -> Result<Vec<u8>>`**
**`fn to_string<T: Serialize>(value: &T) -> Result<String>`**
**`fn to_string_pretty<T: Serialize>(value: &T) -> Result<String>`**
