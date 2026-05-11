# Contract: src/map.rs

## Public Type: `Map<K, V>` (specialized as `Map<String, Value>`)

Backed by `BTreeMap` (default) or `IndexMap` (preserve_order). All methods operate on `Map<String, Value>`.

**`fn new() -> Self`** — empty map.
**`fn with_capacity(capacity: usize) -> Self`** — pre-allocated (no-op for BTreeMap).
**`fn clear(&mut self)`**
**`fn get<Q>(&self, key: &Q) -> Option<&Value>`** — Q: Ord+Eq+Hash, String: Borrow<Q>.
**`fn contains_key<Q>(&self, key: &Q) -> bool`**
**`fn get_mut<Q>(&mut self, key: &Q) -> Option<&mut Value>`**
**`fn get_key_value<Q>(&self, key: &Q) -> Option<(&String, &Value)>`**
**`fn insert(&mut self, k: String, v: Value) -> Option<Value>`**
**`fn shift_insert(&mut self, index: usize, k: String, v: Value) -> Option<Value>`** (preserve_order only)
**`fn remove<Q>(&mut self, key: &Q) -> Option<Value>`** — swap_remove under preserve_order.
**`fn remove_entry<Q>(&mut self, key: &Q) -> Option<(String, Value)>`**
**`fn swap_remove<Q>(&mut self, key: &Q) -> Option<Value>`** (preserve_order)
**`fn swap_remove_entry<Q>(&mut self, key: &Q) -> Option<(String, Value)>`** (preserve_order)
**`fn shift_remove<Q>(&mut self, key: &Q) -> Option<Value>`** (preserve_order)
**`fn shift_remove_entry<Q>(&mut self, key: &Q) -> Option<(String, Value)>`** (preserve_order)
**`fn append(&mut self, other: &mut Self)`**
**`fn entry<S: Into<String>>(&mut self, key: S) -> Entry`**
**`fn len(&self) -> usize`**
**`fn is_empty(&self) -> bool`**
**`fn iter(&self) -> Iter`**
**`fn iter_mut(&mut self) -> IterMut`**
**`fn keys(&self) -> Keys`**
**`fn values(&self) -> Values`**
**`fn values_mut(&mut self) -> ValuesMut`**
**`fn into_values(self) -> IntoValues`**
**`fn retain<F: FnMut(&String, &mut Value) -> bool>(&mut self, f: F)`**
**`fn sort_keys(&mut self)`** — sorts under preserve_order; no-op otherwise.

Implements `Default`, `Clone`, `PartialEq`, `Eq`, `Hash`, `Debug`, `Serialize`, `Deserialize`, `FromIterator`, `Extend`, `Index<&Q>`, `IndexMut<&Q>`, `IntoIterator`, `de::IntoDeserializer`.

### Entry API
**`Entry<'a>`** — enum `Vacant(VacantEntry<'a>)` / `Occupied(OccupiedEntry<'a>)`.
- `fn key(&self) -> &String`
- `fn or_insert(self, default: Value) -> &'a mut Value`
- `fn or_insert_with<F: FnOnce() -> Value>(self, default: F) -> &'a mut Value`
- `fn and_modify<F: FnOnce(&mut Value)>(self, f: F) -> Self`

**`VacantEntry<'a>`**: `fn key(&self) -> &String`, `fn insert(self, value: Value) -> &'a mut Value`.
**`OccupiedEntry<'a>`**: `fn key(&self) -> &String`, `fn get(&self) -> &Value`, `fn get_mut(&mut self) -> &mut Value`, `fn into_mut(self) -> &'a mut Value`, `fn insert(&mut self, value: Value) -> Value`, `fn remove(self) -> Value`, `fn remove_entry(self) -> (String, Value)`, plus swap/shift variants under preserve_order.
