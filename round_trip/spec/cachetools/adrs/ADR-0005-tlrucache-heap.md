# ADR-0005: TLRUCache Min-Heap Expiry Structure

## Status
Accepted

## Context
`TLRUCache` uses a per-item TTU (time-to-use) function rather than a
uniform TTL, so expiry times vary and cannot be managed with a simple
ring.

## Decision
A min-heap (`heapq`, ordered by `_Item.expires`) stores `_Item` objects
(`key`, `expires`, `removed` flag).  A dict `__items` maps keys to their
current `_Item`.  An `OrderedDict` `__order` provides LRU ordering.

On `__setitem__`: a new `_Item` is pushed onto the heap; the old item (if
any) has `removed = True` set as a lazy-deletion marker.  On `expire`:
heap entries with `removed=True` or whose key no longer maps to that item
are skipped (lazy deletion); entries whose `expires <= time` are evicted.

`__contains__` and `__getitem__` check `item.expires > self.timer()`.

`popitem()` expires first, then evicts the LRU item from `__order`.

## Consequences
Heap entries are never physically removed except during `expire`; stale
entries accumulate until `expire` is called.  The `removed` flag enables
O(log n) amortised expiry without a separate decrease-key operation.
