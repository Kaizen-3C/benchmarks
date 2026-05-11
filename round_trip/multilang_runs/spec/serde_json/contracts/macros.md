# Contract: src/macros.rs

## Public Macros

### `json!($($json:tt)+)`
Constructs a `serde_json::Value` from JSON-like literal syntax. Supports `null`, `true`, `false`, arrays `[...]`, objects `{...}`, and any `Serialize`-able expression. Trailing commas allowed. Variables and expressions interpolated directly.

### `json_internal!($($json:tt)+)` (hidden, doc(hidden))
Implementation detail used by `json!`. Also referenced by Rocket crate.

### `json_unexpected!()` (hidden)
Zero-argument macro that triggers "no rules expected the token" errors.

### `json_expect_expr_comma!($e:expr , $($tt:tt)*)` (hidden)
Validates comma after expression in object value position.
