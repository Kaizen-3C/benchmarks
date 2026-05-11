# Contract: src/io/mod.rs and src/io/core.rs

## Purpose
Thin facade re-exporting `std::io` under `std` feature, or providing a minimal reimplementation under no-std.

## Public Items (always available)
**`type Error`** — I/O error type (std: `std::io::Error`; no-std: unit-like struct, infallible).
**`type ErrorKind`** — no-std: enum with single variant `Other`; std: `std::io::ErrorKind`.
**`type Result<T>`** — `result::Result<T, Error>`.
**`trait Write`** — `write(&mut self, buf: &[u8]) -> Result<usize>`, `write_all(&mut self, buf: &[u8]) -> Result<()>`, `flush(&mut self) -> Result<()>`.

Implementations: `Vec<u8>: Write` (infallible extend), `&mut W: Write` (delegates).

## std-only re-exports
`Bytes`, `Read` (from `std::io`).
