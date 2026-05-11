# Contract: src/lexical/ (feature = "float_roundtrip")

## Public API (from lexical/mod.rs)

**`fn parse_concise_float<F: Float>(mantissa: u64, mant_exp: i32) -> F`**
Parse a float from mantissa × 10^mant_exp. Used when the entire decimal representation fits in a u64 mantissa.

**`fn parse_truncated_float<F: Float>(integer: &[u8], fraction: &[u8], exponent: i32) -> F`**
Parse a float from separate integer-part bytes, fraction-part bytes, and an exponent. Trailing zeros in fraction are stripped. Used when the mantissa overflowed u64 during parsing.

## Internal Key Types (pub(crate) within lexical)

**`ExtendedFloat { mant: u64, exp: i32 }`** — 80-bit extended precision float.
- `fn mul(&self, b: &ExtendedFloat) -> ExtendedFloat`
- `fn normalize(&mut self) -> u32`
- `fn round_to_native<F: Float, Algorithm>(&mut self, algorithm: Algorithm)`
- `fn into_float<F: Float>(self) -> F`
- `fn into_downward_float<F: Float>(self) -> F`
- `fn from_float<F: Float>(f: F) -> ExtendedFloat`

**`Bigint { data: Vec<Limb> }`** — arbitrary-precision integer for slow path.

**`trait Float`** — implemented by `f32` and `f64`. Key constants: `MANTISSA_SIZE`, `EXPONENT_BIAS`, `MAX_DIGITS`, `INFINITY_BITS`, etc. Key methods: `exponent_limit() -> (i32,i32)`, `mantissa_limit() -> i32`, `pow10(self, n: i32) -> Self`.

**`type Limb`** — `u32` (fast_arithmetic=32) or `u64` (fast_arithmetic=64).
