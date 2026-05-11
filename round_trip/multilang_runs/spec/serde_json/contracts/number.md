# Contract: src/number.rs

## Public Type: `Number`

Represents a JSON number (integer or float), always finite.

**`fn is_i64(&self) -> bool`**
**`fn is_u64(&self) -> bool`**
**`fn is_f64(&self) -> bool`**
**`fn as_i64(&self) -> Option<i64>`**
**`fn as_u64(&self) -> Option<u64>`**
**`fn as_f64(&self) -> Option<f64>`**
**`fn as_i128(&self) -> Option<i128>`**
**`fn as_u128(&self) -> Option<u128>`**
**`fn from_f64(f: f64) -> Option<Number>`** — None if not finite.
**`fn from_i128(i: i128) -> Option<Number>`** — None if out of range (without arbitrary_precision).
**`fn from_u128(u: u128) -> Option<Number>`** — None if out of range (without arbitrary_precision).
**`fn as_str(&self) -> &str`** (arbitrary_precision only)

Implements `Clone`, `PartialEq`, `Eq`, `Hash`, `Display`, `Debug`, `Serialize`, `Deserialize`.
Implements `From<u8/u16/u32/u64/usize/i8/i16/i32/i64/isize>` (and i128/u128 under arbitrary_precision).
