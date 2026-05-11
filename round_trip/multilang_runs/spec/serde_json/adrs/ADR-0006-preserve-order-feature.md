# ADR-0006: Map Key Order Preservation via `preserve_order` Feature

## Status
Accepted

## Context
`BTreeMap` always sorts keys. Some JSON applications care about round-tripping key order.

## Decision
When `preserve_order` is enabled, `MapImpl<K,V>` is `IndexMap<K,V>` from the `indexmap` crate. Otherwise it is `BTreeMap<K,V>`. All public `Map` methods remain identical; `remove` maps to `swap_remove` under `preserve_order` (perturbs order). `shift_remove` and `shift_insert` are conditionally available under `preserve_order`.

## Consequences
`preserve_order` requires `std`. The `Hash` impl for `Map` under `preserve_order` sorts keys before hashing for consistency.
