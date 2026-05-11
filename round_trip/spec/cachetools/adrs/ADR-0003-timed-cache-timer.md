# ADR-0003: Timer Abstraction in Timed Caches

## Status
Accepted

## Context
`TTLCache` and `TLRUCache` need a monotonic clock for expiry but tests
need to inject a fake clock.

## Decision
`_TimedCache` wraps the timer callable in an inner `_Timer` object that
acts as both a callable and a context manager.

- Called with no arguments: delegates to the underlying timer, unless
  currently inside a `with self.timer` block, in which case it returns
  the time captured at context entry.
- Used as a context manager (`with self.timer as now`): captures the
  current time at entry, increments a nesting counter so nested uses
  return the same snapshot, decrements on exit.

The default timer is `time.monotonic`.

`expire(time=None)` may be called with an explicit time; if `None` it
calls `self.timer()`.

## Consequences
All mutation operations that need consistent time snapshots use
`with self.timer as now`.  `__repr__`, `__len__`, and `currsize` all
call `expire` inside a timer context to ensure stale items are excluded.
