# ADR-0001: no_std Support via alloc Feature

## Status
Accepted

## Context
serde_json needs to run in embedded/no_std environments. The crate uses `#![no_std]` at the top level but requires either `std` (default) or `alloc` feature to be enabled; compile error if neither is present.

## Decision
- Use `extern crate alloc` unconditionally; `extern crate std` only with `std` feature.
- Re-export `std::io` types when `std` is enabled; use a hand-rolled minimal `io` shim (`src/io/core.rs`) otherwise. The shim provides `Write`, `Error`, `ErrorKind`, `Result` with infallible impls for `Vec<u8>`.
- `IoRead` (reader-based deserializer) is gated behind `#[cfg(feature = "std")]`.
- `iter.rs` (LineColIterator) is only compiled under `std`.

## Consequences
Users on no_std must use `SliceRead` or `StrRead`. The `Write` trait in `io/core.rs` must mirror the `std::io::Write` interface exactly for the `Serializer` to work.
