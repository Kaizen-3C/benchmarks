# ADR-0007: 128-Level Recursion Limit

## Status
Accepted

## Context
Deeply nested JSON can cause stack overflows.

## Decision
`Deserializer` has a `remaining_depth: u8` field initialized to 128. Each recursive descent into an array or object decrements it; if it reaches zero, `ErrorCode::RecursionLimitExceeded` is returned. The `unbounded_depth` feature adds a `disable_recursion_limit: bool` field and a `disable_recursion_limit()` method that bypasses the check (intended for use with `serde_stacker`).

## Consequences
JSON with more than 128 nesting levels is rejected by default. Users needing deeper nesting must enable `unbounded_depth` and supply their own stack-overflow protection.
