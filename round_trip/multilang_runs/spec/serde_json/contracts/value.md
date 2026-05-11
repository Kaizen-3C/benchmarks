# Contract: src/value/mod.rs

## Public Enum: `Value`
`#[derive(Clone, Eq, PartialEq, Hash)]`

Variants:
- `Null`
- `Bool(bool)`
- `Number(Number)`
- `String(String)`
- `Array(Vec<Value>)`
- `Object(Map<String, Value>)`

### Accessor Methods
**`fn get<I: Index>(&self, index: I) -> Option<&Value>`**
**`fn get_mut<I: Index>(&mut self, index: I) -> Option<&mut Value>`**
**`fn is_object(&self) -> bool`** / **`fn as_object(&self) -> Option<&Map<String, Value>>`** / **`fn as_object_mut(&mut self) -> Option<&mut Map<String, Value>>`**
**`fn is_array(&self) -> bool`** / **`fn as_array(&self) -> Option<&Vec<Value>>`** / **`fn as_array_mut(&mut self) -> Option<&mut Vec<Value>>`**
**`fn is_string(&self) -> bool`** / **`fn as_str(&self) -> Option<&str>`**
**`fn is_number(&self) -> bool`** / **`fn as_number(&self) -> Option<&Number>`**
**`fn is_i64(&self) -> bool`** / **`fn as_i64(&self) -> Option<i64>`**
**`fn is_u64(&self) -> bool`** / **`fn as_u64(&self) -> Option<u64>`**
**`fn is_f64(&self) -> bool`** / **`fn as_f64(&self) -> Option<f64>`**
**`fn is_boolean(&self) -> bool`** / **`fn as_bool(&self) -> Option<bool>`**
**`fn is_null(&self) -> bool`** / **`fn as_null(&self) -> Option<()>`**
**`fn pointer(&self, pointer: &str) -> Option<&Value>`** — RFC6901 JSON Pointer.
**`fn pointer_mut(&mut self, pointer: &str) -> Option<&mut Value>`**
**`fn take(&mut self) -> Value`** — replaces self with Null, returns old value.
**`fn sort_all_objects(&mut self)`** — sorts nested maps (no-op without preserve_order).

### Trait Implementations
`Debug`, `Display` (JSON serialization, `{:#}` for pretty), `Default` (Null), `Serialize`, `Deserialize`, `Index<I>` (returns `&Value::Null` on miss), `IndexMut<I>` (inserts null on miss for objects), `FromStr`, `IntoDeserializer`.

### `Index` Trait (sealed)
Implemented for `usize`, `str`, `String`, `&T where T: Index`.

## Free Functions
**`fn to_value<T: Serialize>(value: T) -> Result<Value, Error>`**
**`fn from_value<T: DeserializeOwned>(value: Value) -> Result<T, Error>`**
