# ADR-0005: RawValue for Zero-Copy JSON Pass-Through

## Status
Accepted

## Context
Some use cases need to defer parsing or preserve exact formatting of a JSON fragment.

## Decision
`RawValue` is a `#[repr(transparent)]` newtype over `str`. It uses the same sentinel/token protocol as `arbitrary_precision` numbers: `TOKEN = "$serde_json::private::RawValue"`. During deserialization, the deserializer enters a "raw buffering" mode (`begin_raw_buffering` / `end_raw_buffering` on the `Read` trait) that captures the exact bytes of one JSON value. `BorrowedRawDeserializer` / `OwnedRawDeserializer` bridge the `MapAccess` protocol.

## Consequences
`RawValue` can only borrow from `from_str`/`from_slice`; `from_reader` requires `Box<RawValue>`. The `raw_value` feature must be enabled.
