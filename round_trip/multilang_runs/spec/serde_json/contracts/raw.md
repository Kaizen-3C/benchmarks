# Contract: src/raw.rs (feature = "raw_value")

## Public Types

### `RawValue`
`#[repr(transparent)]` newtype over `str`. Unsized; typically used as `&RawValue` or `Box<RawValue>`.

**`const NULL: &'static RawValue`** — the literal JSON `null`.
**`const TRUE: &'static RawValue`** — the literal JSON `true`.
**`const FALSE: &'static RawValue`** — the literal JSON `false`.
**`fn get(&self) -> &str`** — the underlying JSON text.
**`fn from_string(json: String) -> Result<Box<Self>, Error>`** — validates and wraps.

Implements `Debug`, `Display`, `Clone` (for `Box<RawValue>`), `ToOwned`, `Default` (for `Box<RawValue>`), `Serialize`, `Deserialize` (for `&RawValue` and `Box<RawValue>`), `IntoDeserializer`, `Deserializer`.

### `to_raw_value<T: Serialize>(value: &T) -> Result<Box<RawValue>, Error>`
Serializes a value to a JSON string and wraps it as a `RawValue`.
