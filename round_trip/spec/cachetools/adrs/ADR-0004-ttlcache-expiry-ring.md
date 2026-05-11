# ADR-0004: TTLCache Expiry Ring Structure

## Status
Accepted

## Context
`TTLCache` must expire items in insertion order (oldest TTL first) and
also support LRU eviction when the cache is full but no items have
expired.

## Decision
A circular doubly-linked list (`_Link` objects with `key`, `expires`,
`next`, `prev` slots) acts as the expiry ring; the sentinel `__root`
node has `root.prev = root.next = root` on initialisation.  New links
are inserted before `root` (i.e., at the tail).  An `OrderedDict`
(`__links`) maps keys to `_Link` objects and provides LRU ordering via
`move_to_end`.

`expire(time)` walks from `root.next` forward, removing all links whose
`expires <= time` from both the ring and `Cache.__data`.

`popitem()` calls `expire` first, then evicts the LRU item from
`__links`.

`__contains__` checks the link's `expires` against `self.timer()` rather
than checking presence in `__data` alone, so that logically expired items
are treated as absent.

## Consequences
`__delitem__` raises `KeyError` if the deleted key was already expired
(expires ≤ current time) because logical deletion of an already-absent
item is an error.
