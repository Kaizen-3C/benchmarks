use alloc::string::String;
use core::borrow::Borrow;
use core::fmt;
use core::hash::Hash;
use core::iter::FromIterator;
use core::ops;

use serde_core::de::{self, IntoDeserializer};
use serde_core::ser;

use crate::error::Error;
use crate::value::Value;

#[cfg(not(feature = "preserve_order"))]
use alloc::collections::{btree_map, BTreeMap};

#[cfg(feature = "preserve_order")]
use indexmap::{self, IndexMap};

/// A map of String to Value.
///
/// By default the map is backed by a [`BTreeMap`]. Enable the `preserve_order`
/// feature of serde_json to use [`IndexMap`] instead, which preserves
/// entries in the order they are inserted into the map.
///
/// [`BTreeMap`]: https://doc.rust-lang.org/std/collections/struct.BTreeMap.html
/// [`IndexMap`]: https://docs.rs/indexmap/*/indexmap/map/struct.IndexMap.html
#[derive(Clone, PartialEq, Eq)]
pub struct Map<K, V> {
    map: MapImpl<K, V>,
}

#[cfg(not(feature = "preserve_order"))]
type MapImpl<K, V> = BTreeMap<K, V>;

#[cfg(feature = "preserve_order")]
type MapImpl<K, V> = IndexMap<K, V>;

impl Map<String, Value> {
    /// Makes a new empty Map.
    #[inline]
    pub fn new() -> Self {
        Map {
            map: MapImpl::new(),
        }
    }

    /// Makes a new empty Map with the given initial capacity.
    #[inline]
    pub fn with_capacity(capacity: usize) -> Self {
        Map {
            map: {
                #[cfg(not(feature = "preserve_order"))]
                {
                    // BTreeMap does not support capacity
                    let _ = capacity;
                    BTreeMap::new()
                }
                #[cfg(feature = "preserve_order")]
                IndexMap::with_capacity(capacity)
            },
        }
    }

    /// Clears the map, removing all values.
    #[inline]
    pub fn clear(&mut self) {
        self.map.clear();
    }

    /// Returns a reference to the value corresponding to the key.
    ///
    /// The key may be any borrowed form of the map's key type, but the
    /// ordering on the borrowed form *must* match the ordering on the key
    /// type.
    #[inline]
    pub fn get<Q>(&self, key: &Q) -> Option<&Value>
    where
        String: Borrow<Q>,
        Q: ?Sized + Ord + Eq + Hash,
    {
        self.map.get(key)
    }

    /// Returns true if the map contains a value for the specified key.
    ///
    /// The key may be any borrowed form of the map's key type, but the
    /// ordering on the borrowed form *must* match the ordering on the key
    /// type.
    #[inline]
    pub fn contains_key<Q>(&self, key: &Q) -> bool
    where
        String: Borrow<Q>,
        Q: ?Sized + Ord + Eq + Hash,
    {
        self.map.contains_key(key)
    }

    /// Returns a mutable reference to the value corresponding to the key.
    ///
    /// The key may be any borrowed form of the map's key type, but the
    /// ordering on the borrowed form *must* match the ordering on the key
    /// type.
    #[inline]
    pub fn get_mut<Q>(&mut self, key: &Q) -> Option<&mut Value>
    where
        String: Borrow<Q>,
        Q: ?Sized + Ord + Eq + Hash,
    {
        self.map.get_mut(key)
    }

    /// Returns the key-value pair matching the given key.
    #[inline]
    pub fn get_key_value<Q>(&self, key: &Q) -> Option<(&String, &Value)>
    where
        String: Borrow<Q>,
        Q: ?Sized + Ord + Eq + Hash,
    {
        self.map.get_key_value(key)
    }

    /// Inserts a key-value pair into the map.
    ///
    /// If the map did not have this key present, [`None`] is returned.
    ///
    /// If the map did have this key present, the value is updated, and the old
    /// value is returned.
    #[inline]
    pub fn insert(&mut self, k: String, v: Value) -> Option<Value> {
        self.map.insert(k, v)
    }

    /// Insert a key-value pair in the map at the given index.
    ///
    /// If the map did not have this key present, `None` is returned.
    ///
    /// If the map did have this key present, the key is moved to the new
    /// position, the value is updated, and the old value is returned.
    #[cfg(feature = "preserve_order")]
    #[inline]
    pub fn shift_insert(&mut self, index: usize, k: String, v: Value) -> Option<Value> {
        self.map.shift_insert(index, k, v)
    }

    /// Removes a key from the map, returning the value at the key if the key
    /// was previously in the map.
    ///
    /// The key may be any borrowed form of the map's key type, but the
    /// ordering on the borrowed form *must* match the ordering on the key
    /// type.
    ///
    /// If serde_json's "preserve_order" is enabled, `.remove` is equivalent to
    /// [`.swap_remove`], replacing this entry's position with the last element.
    /// If you need to preserve the relative order of the keys in the map, use
    /// [`.shift_remove`] instead.
    ///
    /// [`.swap_remove`]: Self::swap_remove
    /// [`.shift_remove`]: Self::shift_remove
    #[inline]
    pub fn remove<Q>(&mut self, key: &Q) -> Option<Value>
    where
        String: Borrow<Q>,
        Q: ?Sized + Ord + Eq + Hash,
    {
        #[cfg(feature = "preserve_order")]
        return self.map.swap_remove(key);
        #[cfg(not(feature = "preserve_order"))]
        return self.map.remove(key);
    }

    /// Removes a key from the map, returning the stored key and value if the
    /// key was previously in the map.
    ///
    /// The key may be any borrowed form of the map's key type, but the
    /// ordering on the borrowed form *must* match the ordering on the key
    /// type.
    ///
    /// If serde_json's "preserve_order" is enabled, `.remove_entry` is
    /// equivalent to [`.swap_remove_entry`], replacing this entry's position
    /// with the last element. If you need to preserve the relative order of the
    /// keys in the map, use [`.shift_remove_entry`] instead.
    ///
    /// [`.swap_remove_entry`]: Self::swap_remove_entry
    /// [`.shift_remove_entry`]: Self::shift_remove_entry
    #[inline]
    pub fn remove_entry<Q>(&mut self, key: &Q) -> Option<(String, Value)>
    where
        String: Borrow<Q>,
        Q: ?Sized + Ord + Eq + Hash,
    {
        #[cfg(feature = "preserve_order")]
        return self.map.swap_remove_entry(key);
        #[cfg(not(feature = "preserve_order"))]
        return self.map.remove_entry(key);
    }

    /// Removes and returns the value corresponding to the key from the map.
    ///
    /// Like [`Vec::swap_remove`], the entry is removed by swapping it with the
    /// last element of the map and popping it off. This perturbs the position
    /// of what used to be the last element!
    ///
    /// [`Vec::swap_remove`]: https://doc.rust-lang.org/std/vec/struct.Vec.html#method.swap_remove
    #[cfg(feature = "preserve_order")]
    #[inline]
    pub fn swap_remove<Q>(&mut self, key: &Q) -> Option<Value>
    where
        String: Borrow<Q>,
        Q: ?Sized + Ord + Eq + Hash,
    {
        self.map.swap_remove(key)
    }

    /// Remove and return the key-value pair.
    ///
    /// Like [`Vec::swap_remove`], the entry is removed by swapping it with the
    /// last element of the map and popping it off. This perturbs the position
    /// of what used to be the last element!
    ///
    /// [`Vec::swap_remove`]: https://doc.rust-lang.org/std/vec/struct.Vec.html#method.swap_remove
    #[cfg(feature = "preserve_order")]
    #[inline]
    pub fn swap_remove_entry<Q>(&mut self, key: &Q) -> Option<(String, Value)>
    where
        String: Borrow<Q>,
        Q: ?Sized + Ord + Eq + Hash,
    {
        self.map.swap_remove_entry(key)
    }

    /// Removes and returns the value corresponding to the key from the map.
    ///
    /// Like [`Vec::remove`], the entry is removed by shifting all of the
    /// elements that follow it, preserving their relative order. This perturbs
    /// the index of all of those elements!
    ///
    /// [`Vec::remove`]: https://doc.rust-lang.org/std/vec/struct.Vec.html#method.remove
    #[cfg(feature = "preserve_order")]
    #[inline]
    pub fn shift_remove<Q>(&mut self, key: &Q) -> Option<Value>
    where
        String: Borrow<Q>,
        Q: ?Sized + Ord + Eq + Hash,
    {
        self.map.shift_remove(key)
    }

    /// Remove and return the key-value pair.
    ///
    /// Like [`Vec::remove`], the entry is removed by shifting all of the
    /// elements that follow it, preserving their relative order. This perturbs
    /// the index of all of those elements!
    ///
    /// [`Vec::remove`]: https://doc.rust-lang.org/std/vec/struct.Vec.html#method.remove
    #[cfg(feature = "preserve_order")]
    #[inline]
    pub fn shift_remove_entry<Q>(&mut self, key: &Q) -> Option<(String, Value)>
    where
        String: Borrow<Q>,
        Q: ?Sized + Ord + Eq + Hash,
    {
        self.map.shift_remove_entry(key)
    }

    /// Moves all elements from other into self, leaving other empty.
    #[inline]
    pub fn append(&mut self, other: &mut Self) {
        #[cfg(feature = "preserve_order")]
        for (k, v) in core::mem::take(&mut other.map) {
            self.map.insert(k, v);
        }
        #[cfg(not(feature = "preserve_order"))]
        self.map.append(&mut other.map);
    }

    /// Gets the given key's corresponding entry in the map for in-place
    /// manipulation.
    pub fn entry<S: Into<String>>(&mut self, key: S) -> Entry {
        #[cfg(not(feature = "preserve_order"))]
        use alloc::collections::btree_map::Entry as EntryImpl;
        #[cfg(feature = "preserve_order")]
        use indexmap::map::Entry as EntryImpl;

        match self.map.entry(key.into()) {
            EntryImpl::Vacant(vacant) => Entry::Vacant(VacantEntry { vacant }),
            EntryImpl::Occupied(occupied) => Entry::Occupied(OccupiedEntry { occupied }),
        }
    }

    /// Returns the number of elements in the map.
    #[inline]
    pub fn len(&self) -> usize {
        self.map.len()
    }

    /// Returns true if the map contains no elements.
    #[inline]
    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }

    /// Gets an iterator over the entries of the map.
    #[inline]
    pub fn iter(&self) -> Iter {
        Iter {
            iter: self.map.iter(),
        }
    }

    /// Gets a mutable iterator over the entries of the map.
    #[inline]
    pub fn iter_mut(&mut self) -> IterMut {
        IterMut {
            iter: self.map.iter_mut(),
        }
    }

    /// Gets an iterator over the keys of the map.
    #[inline]
    pub fn keys(&self) -> Keys {
        Keys {
            iter: self.map.keys(),
        }
    }

    /// Gets an iterator over the values of the map.
    #[inline]
    pub fn values(&self) -> Values {
        Values {
            iter: self.map.values(),
        }
    }

    /// Gets a mutable iterator over the values of the map.
    #[inline]
    pub fn values_mut(&mut self) -> ValuesMut {
        ValuesMut {
            iter: self.map.values_mut(),
        }
    }

    /// Gets a consuming iterator over the values of the map.
    #[inline]
    pub fn into_values(self) -> IntoValues {
        IntoValues {
            iter: self.map.into_values(),
        }
    }

    /// Retains only the elements specified by the predicate.
    #[inline]
    pub fn retain<F>(&mut self, f: F)
    where
        F: FnMut(&String, &mut Value) -> bool,
    {
        self.map.retain(f);
    }

    /// Sort all keys in this map in place.
    ///
    /// This only has an effect when the `preserve_order` feature is enabled.
    #[inline]
    pub fn sort_keys(&mut self) {
        #[cfg(feature = "preserve_order")]
        self.map.sort_keys();
    }
}

impl Default for Map<String, Value> {
    #[inline]
    fn default() -> Self {
        Map {
            map: MapImpl::new(),
        }
    }
}

impl fmt::Debug for Map<String, Value> {
    #[inline]
    fn fmt(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
        self.map.fmt(formatter)
    }
}

impl core::hash::Hash for Map<String, Value> {
    fn hash<H: core::hash::Hasher>(&self, state: &mut H) {
        #[cfg(not(feature = "preserve_order"))]
        {
            // BTreeMap iterates in sorted order
            for (k, v) in &self.map {
                k.hash(state);
                v.hash(state);
            }
        }
        #[cfg(feature = "preserve_order")]
        {
            // Sort keys for consistent hashing
            let mut entries: alloc::vec::Vec<(&String, &Value)> = self.map.iter().collect();
            entries.sort_by_key(|(k, _)| k.as_str());
            for (k, v) in entries {
                k.hash(state);
                v.hash(state);
            }
        }
    }
}

impl ser::Serialize for Map<String, Value> {
    #[inline]
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: ser::Serializer,
    {
        use serde_core::ser::SerializeMap;
        let mut map = serializer.serialize_map(Some(self.len()))?;
        for (k, v) in &self.map {
            map.serialize_entry(k, v)?;
        }
        map.end()
    }
}

impl<'de> de::Deserialize<'de> for Map<String, Value> {
    #[inline]
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: de::Deserializer<'de>,
    {
        struct Visitor;

        impl<'de> de::Visitor<'de> for Visitor {
            type Value = Map<String, Value>;

            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                formatter.write_str("a map")
            }

            #[inline]
            fn visit_unit<E>(self) -> Result<Self::Value, E>
            where
                E: de::Error,
            {
                Ok(Map::new())
            }

            #[inline]
            fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
            where
                A: de::MapAccess<'de>,
            {
                let mut values = Map::new();

                while let Some((key, value)) = map.next_entry()? {
                    values.insert(key, value);
                }

                Ok(values)
            }
        }

        deserializer.deserialize_map(Visitor)
    }
}

impl FromIterator<(String, Value)> for Map<String, Value> {
    fn from_iter<T: IntoIterator<Item = (String, Value)>>(iter: T) -> Self {
        Map {
            map: FromIterator::from_iter(iter),
        }
    }
}

impl Extend<(String, Value)> for Map<String, Value> {
    fn extend<T: IntoIterator<Item = (String, Value)>>(&mut self, iter: T) {
        self.map.extend(iter);
    }
}

impl ops::Index<&str> for Map<String, Value> {
    type Output = Value;

    fn index(&self, index: &str) -> &Value {
        static NULL: Value = Value::Null;
        self.map.get(index).unwrap_or(&NULL)
    }
}

impl ops::IndexMut<&str> for Map<String, Value> {
    fn index_mut(&mut self, index: &str) -> &mut Value {
        // For object, insert null if missing
        if !self.map.contains_key(index) {
            self.map.insert(index.to_owned(), Value::Null);
        }
        self.map.get_mut(index).unwrap()
    }
}

impl<'a> IntoIterator for &'a Map<String, Value> {
    type Item = (&'a String, &'a Value);
    type IntoIter = Iter<'a>;

    #[inline]
    fn into_iter(self) -> Self::IntoIter {
        Iter {
            iter: self.map.iter(),
        }
    }
}

impl<'a> IntoIterator for &'a mut Map<String, Value> {
    type Item = (&'a String, &'a mut Value);
    type IntoIter = IterMut<'a>;

    #[inline]
    fn into_iter(self) -> Self::IntoIter {
        IterMut {
            iter: self.map.iter_mut(),
        }
    }
}

impl IntoIterator for Map<String, Value> {
    type Item = (String, Value);
    type IntoIter = IntoIter;

    #[inline]
    fn into_iter(self) -> Self::IntoIter {
        IntoIter {
            iter: self.map.into_iter(),
        }
    }
}

/// A view into a single entry in a map, which may either be vacant or occupied.
/// This enum is constructed from the [`entry`] method on [`Map`].
///
/// [`entry`]: struct.Map.html#method.entry
/// [`Map`]: struct.Map.html
pub enum Entry<'a> {
    /// A vacant Entry.
    Vacant(VacantEntry<'a>),
    /// An occupied Entry.
    Occupied(OccupiedEntry<'a>),
}

/// A vacant Entry. It is part of the [`Entry`] enum.
///
/// [`Entry`]: enum.Entry.html
pub struct VacantEntry<'a> {
    vacant: VacantEntryImpl<'a>,
}

/// An occupied Entry. It is part of the [`Entry`] enum.
///
/// [`Entry`]: enum.Entry.html
pub struct OccupiedEntry<'a> {
    occupied: OccupiedEntryImpl<'a>,
}

#[cfg(not(feature = "preserve_order"))]
type VacantEntryImpl<'a> = btree_map::VacantEntry<'a, String, Value>;
#[cfg(feature = "preserve_order")]
type VacantEntryImpl<'a> = indexmap::map::VacantEntry<'a, String, Value>;

#[cfg(not(feature = "preserve_order"))]
type OccupiedEntryImpl<'a> = btree_map::OccupiedEntry<'a, String, Value>;
#[cfg(feature = "preserve_order")]
type OccupiedEntryImpl<'a> = indexmap::map::OccupiedEntry<'a, String, Value>;

impl<'a> Entry<'a> {
    /// Returns a reference to this entry's key.
    pub fn key(&self) -> &String {
        match self {
            Entry::Vacant(e) => e.key(),
            Entry::Occupied(e) => e.key(),
        }
    }

    /// Ensures a value is in the entry by inserting the default if empty, and
    /// returns a mutable reference to the value in the entry.
    pub fn or_insert(self, default: Value) -> &'a mut Value {
        match self {
            Entry::Vacant(entry) => entry.insert(default),
            Entry::Occupied(entry) => entry.into_mut(),
        }
    }

    /// Ensures a value is in the entry by inserting the result of the default
    /// function if empty, and returns a mutable reference to the value in the
    /// entry.
    pub fn or_insert_with<F: FnOnce() -> Value>(self, default: F) -> &'a mut Value {
        match self {
            Entry::Vacant(entry) => entry.insert(default()),
            Entry::Occupied(entry) => entry.into_mut(),
        }
    }

    /// Provides in-place mutable access to an occupied entry before any
    /// potential inserts into the map.
    pub fn and_modify<F: FnOnce(&mut Value)>(self, f: F) -> Self {
        match self {
            Entry::Vacant(entry) => Entry::Vacant(entry),
            Entry::Occupied(mut entry) => {
                f(entry.get_mut());
                Entry::Occupied(entry)
            }
        }
    }
}

impl<'a> VacantEntry<'a> {
    /// Gets a reference to the key that would be used when inserting a value
    /// through the VacantEntry.
    #[inline]
    pub fn key(&self) -> &String {
        self.vacant.key()
    }

    /// Sets the value of the entry with the VacantEntry's key, and returns a
    /// mutable reference to it.
    #[inline]
    pub fn insert(self, value: Value) -> &'a mut Value {
        self.vacant.insert(value)
    }
}

impl<'a> OccupiedEntry<'a> {
    /// Gets a reference to the key in the entry.
    #[inline]
    pub fn key(&self) -> &String {
        self.occupied.key()
    }

    /// Gets a reference to the value in the entry.
    #[inline]
    pub fn get(&self) -> &Value {
        self.occupied.get()
    }

    /// Gets a mutable reference to the value in the entry.
    #[inline]
    pub fn get_mut(&mut self) -> &mut Value {
        self.occupied.get_mut()
    }

    /// Converts the entry into a mutable reference to its value.
    #[inline]
    pub fn into_mut(self) -> &'a mut Value {
        self.occupied.into_mut()
    }

    /// Sets the value of the entry with the OccupiedEntry's key, and returns
    /// the entry's old value.
    #[inline]
    pub fn insert(&mut self, value: Value) -> Value {
        self.occupied.insert(value)
    }

    /// Takes the value of the entry out of the map, and returns it.
    #[inline]
    pub fn remove(self) -> Value {
        #[cfg(feature = "preserve_order")]
        return self.occupied.swap_remove();
        #[cfg(not(feature = "preserve_order"))]
        return self.occupied.remove();
    }

    /// Takes the value and key of the entry out of the map, and returns them.
    #[inline]
    pub fn remove_entry(self) -> (String, Value) {
        #[cfg(feature = "preserve_order")]
        return self.occupied.swap_remove_entry();
        #[cfg(not(feature = "preserve_order"))]
        return self.occupied.remove_entry();
    }

    /// Removes the entry from the map by swapping it with the last element.
    #[cfg(feature = "preserve_order")]
    #[inline]
    pub fn swap_remove(self) -> Value {
        self.occupied.swap_remove()
    }

    /// Removes the entry from the map by swapping it with the last element,
    /// returning the stored key and value.
    #[cfg(feature = "preserve_order")]
    #[inline]
    pub fn swap_remove_entry(self) -> (String, Value) {
        self.occupied.swap_remove_entry()
    }

    /// Removes the entry from the map while preserving order.
    #[cfg(feature = "preserve_order")]
    #[inline]
    pub fn shift_remove(self) -> Value {
        self.occupied.shift_remove()
    }

    /// Removes the entry from the map while preserving order, returning the
    /// stored key and value.
    #[cfg(feature = "preserve_order")]
    #[inline]
    pub fn shift_remove_entry(self) -> (String, Value) {
        self.occupied.shift_remove_entry()
    }
}

//////////////////////////////////////////////////////////////////////////////

/// An iterator over a serde_json map's entries.
pub struct Iter<'a> {
    iter: IterImpl<'a>,
}

#[cfg(not(feature = "preserve_order"))]
type IterImpl<'a> = btree_map::Iter<'a, String, Value>;
#[cfg(feature = "preserve_order")]
type IterImpl<'a> = indexmap::map::Iter<'a, String, Value>;

impl<'a> Iterator for Iter<'a> {
    type Item = (&'a String, &'a Value);

    #[inline]
    fn next(&mut self) -> Option<Self::Item> {
        self.iter.next()
    }

    #[inline]
    fn size_hint(&self) -> (usize, Option<usize>) {
        self.iter.size_hint()
    }
}

impl<'a> ExactSizeIterator for Iter<'a> {
    #[inline]
    fn len(&self) -> usize {
        self.iter.len()
    }
}

impl<'a> DoubleEndedIterator for Iter<'a> {
    #[inline]
    fn next_back(&mut self) -> Option<Self::Item> {
        self.iter.next_back()
    }
}

/// A mutable iterator over a serde_json map's entries.
pub struct IterMut<'a> {
    iter: IterMutImpl<'a>,
}

#[cfg(not(feature = "preserve_order"))]
type IterMutImpl<'a> = btree_map::IterMut<'a, String, Value>;
#[cfg(feature = "preserve_order")]
type IterMutImpl<'a> = indexmap::map::IterMut<'a, String, Value>;

impl<'a> Iterator for IterMut<'a> {
    type Item = (&'a String, &'a mut Value);

    #[inline]
    fn next(&mut self) -> Option<Self::Item> {
        self.iter.next()
    }

    #[inline]
    fn size_hint(&self) -> (usize, Option<usize>) {
        self.iter.size_hint()
    }
}

impl<'a> ExactSizeIterator for IterMut<'a> {
    #[inline]
    fn len(&self) -> usize {
        self.iter.len()
    }
}

impl<'a> DoubleEndedIterator for IterMut<'a> {
    #[inline]
    fn next_back(&mut self) -> Option<Self::Item> {
        self.iter.next_back()
    }
}

/// An owning iterator over a serde_json map's entries.
pub struct IntoIter {
    iter: IntoIterImpl,
}

#[cfg(not(feature = "preserve_order"))]
type IntoIterImpl = btree_map::IntoIter<String, Value>;
#[cfg(feature = "preserve_order")]
type IntoIterImpl = indexmap::map::IntoIter<String, Value>;

impl Iterator for IntoIter {
    type Item = (String, Value);

    #[inline]
    fn next(&mut self) -> Option<Self::Item> {
        self.iter.next()
    }

    #[inline]
    fn size_hint(&self) -> (usize, Option<usize>) {
        self.iter.size_hint()
    }
}

impl ExactSizeIterator for IntoIter {
    #[inline]
    fn len(&self) -> usize {
        self.iter.len()
    }
}

impl DoubleEndedIterator for IntoIter {
    #[inline]
    fn next_back(&mut self) -> Option<Self::Item> {
        self.iter.next_back()
    }
}

/// An iterator over a serde_json map's keys.
pub struct Keys<'a> {
    iter: KeysImpl<'a>,
}

#[cfg(not(feature = "preserve_order"))]
type KeysImpl<'a> = btree_map::Keys<'a, String, Value>;
#[cfg(feature = "preserve_order")]
type KeysImpl<'a> = indexmap::map::Keys<'a, String, Value>;

impl<'a> Iterator for Keys<'a> {
    type Item = &'a String;

    #[inline]
    fn next(&mut self) -> Option<Self::Item> {
        self.iter.next()
    }

    #[inline]
    fn size_hint(&self) -> (usize, Option<usize>) {
        self.iter.size_hint()
    }
}

impl<'a> ExactSizeIterator for Keys<'a> {
    #[inline]
    fn len(&self) -> usize {
        self.iter.len()
    }
}

impl<'a> DoubleEndedIterator for Keys<'a> {
    #[inline]
    fn next_back(&mut self) -> Option<Self::Item> {
        self.iter.next_back()
    }
}

/// An iterator over a serde_json map's values.
pub struct Values<'a> {
    iter: ValuesImpl<'a>,
}

#[cfg(not(feature = "preserve_order"))]
type ValuesImpl<'a> = btree_map::Values<'a, String, Value>;
#[cfg(feature = "preserve_order")]
type ValuesImpl<'a> = indexmap::map::Values<'a, String, Value>;

impl<'a> Iterator for Values<'a> {
    type Item = &'a Value;

    #[inline]
    fn next(&mut self) -> Option<Self::Item> {
        self.iter.next()
    }

    #[inline]
    fn size_hint(&self) -> (usize, Option<usize>) {
        self.iter.size_hint()
    }
}

impl<'a> ExactSizeIterator for Values<'a> {
    #[inline]
    fn len(&self) -> usize {
        self.iter.len()
    }
}

impl<'a> DoubleEndedIterator for Values<'a> {
    #[inline]
    fn next_back(&mut self) -> Option<Self::Item> {
        self.iter.next_back()
    }
}

/// A mutable iterator over a serde_json map's values.
pub struct ValuesMut<'a> {
    iter: ValuesMutImpl<'a>,
}

#[cfg(not(feature = "preserve_order"))]
type ValuesMutImpl<'a> = btree_map::ValuesMut<'a, String, Value>;
#[cfg(feature = "preserve_order")]
type ValuesMutImpl<'a> = indexmap::map::ValuesMut<'a, String, Value>;

impl<'a> Iterator for ValuesMut<'a> {
    type Item = &'a mut Value;

    #[inline]
    fn next(&mut self) -> Option<Self::Item> {
        self.iter.next()
    }

    #[inline]
    fn size_hint(&self) -> (usize, Option<usize>) {
        self.iter.size_hint()
    }
}

impl<'a> ExactSizeIterator for ValuesMut<'a> {
    #[inline]
    fn len(&self) -> usize {
        self.iter.len()
    }
}

impl<'a> DoubleEndedIterator for ValuesMut<'a> {
    #[inline]
    fn next_back(&mut self) -> Option<Self::Item> {
        self.iter.next_back()
    }
}

/// A consuming iterator over a serde_json map's values.
pub struct IntoValues {
    iter: IntoValuesImpl,
}

#[cfg(not(feature = "preserve_order"))]
type IntoValuesImpl = btree_map::IntoValues<String, Value>;
#[cfg(feature = "preserve_order")]
type IntoValuesImpl = indexmap::map::IntoValues<String, Value>;

impl Iterator for IntoValues {
    type Item = Value;

    #[inline]
    fn next(&mut self) -> Option<Self::Item> {
        self.iter.next()
    }

    #[inline]
    fn size_hint(&self) -> (usize, Option<usize>) {
        self.iter.size_hint()
    }
}

impl ExactSizeIterator for IntoValues {
    #[inline]
    fn len(&self) -> usize {
        self.iter.len()
    }
}

impl DoubleEndedIterator for IntoValues {
    #[inline]
    fn next_back(&mut self) -> Option<Self::Item> {
        self.iter.next_back()
    }
}

//////////////////////////////////////////////////////////////////////////////

impl<'de> de::IntoDeserializer<'de, Error> for Map<String, Value> {
    type Deserializer = Self;

    fn into_deserializer(self) -> Self::Deserializer {
        self
    }
}

impl<'de> de::Deserializer<'de> for Map<String, Value> {
    type Error = Error;

    #[inline]
    fn deserialize_any<V>(self, visitor: V) -> Result<V::Value, Error>
    where
        V: de::Visitor<'de>,
    {
        use serde_core::de::MapAccess;
        visitor.visit_map(MapAccessDeserializer {
            iter: self.into_iter(),
            value: None,
        })
    }

    serde_core::forward_to_deserialize_any! {
        bool i8 i16 i32 i64 i128 u8 u16 u32 u64 u128 f32 f64 char str string
        bytes byte_buf option unit unit_struct newtype_struct seq tuple
        tuple_struct map struct enum identifier ignored_any
    }
}

struct MapAccessDeserializer {
    iter: IntoIter,
    value: Option<Value>,
}

impl<'de> de::MapAccess<'de> for MapAccessDeserializer {
    type Error = Error;

    fn next_key_seed<K>(&mut self, seed: K) -> Result<Option<K::Value>, Error>
    where
        K: de::DeserializeSeed<'de>,
    {
        match self.iter.next() {
            Some((key, value)) => {
                self.value = Some(value);
                let key_de = de::value::StringDeserializer::<Error>::new(key);
                seed.deserialize(key_de).map(Some)
            }
            None => Ok(None),
        }
    }

    fn next_value_seed<V>(&mut self, seed: V) -> Result<V::Value, Error>
    where
        V: de::DeserializeSeed<'de>,
    {
        match self.value.take() {
            Some(value) => seed.deserialize(value),
            None => Err(de::Error::custom("value is missing")),
        }
    }
}
