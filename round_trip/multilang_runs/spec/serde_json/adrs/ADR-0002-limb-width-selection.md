# ADR-0002: Platform-Specific Limb Width via build.rs

## Status
Accepted

## Context
The lexical float-parsing algorithm uses a big-integer type (`Bigint`) built from "limbs". On 64-bit platforms, 64-bit limbs are faster; on 32-bit platforms, 32-bit limbs avoid emulated 64-bit arithmetic.

## Decision
`build.rs` inspects `CARGO_CFG_TARGET_ARCH` and `CARGO_CFG_TARGET_POINTER_WIDTH` at compile time and sets a custom cfg flag `fast_arithmetic = "64"` or `fast_arithmetic = "32"`. The `math.rs` module uses `#[cfg(fast_arithmetic = "64")]` / `#[cfg(fast_arithmetic = "32")]` to select `u64` vs `u32` as `Limb` and the corresponding `Wide` type (`u128` vs `u64`). Pre-computed power tables also differ: `large_powers64.rs` / `large_powers32.rs`.

Architectures explicitly listed as 64-bit: aarch64, loongarch64, mips64, powerpc64, riscv64, wasm32, x86_64. Also any target with pointer_width=64.

## Consequences
Two sets of pre-computed power tables must be maintained. The algorithm logic is identical; only the limb type changes.
