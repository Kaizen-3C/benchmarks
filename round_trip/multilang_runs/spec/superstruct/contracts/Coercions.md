# Contract: Coercions (src/structs/coercions.ts)

All coercions require `create()` or `mask()` to take effect; `assert()` and
`is()` never invoke coercers.

### `coerce<T,S,C>(struct, condition, coercer): Struct<T,S>`
Returns a new struct that, during coercion, applies `coercer(value, ctx)` only
when `is(value, condition)` is true, then passes the result to the original
struct's coercer.

### `defaulted<T,S>(struct, fallback, options?): Struct<T,S>`
- `fallback` may be a value or a zero-argument function.
- If `value === undefined`, replaces it with `fallback()`.
- If `options.strict !== true` and both value and fallback are plain objects,
  merges missing keys from fallback into a shallow copy of value.
- Implemented via `coerce(struct, unknown(), ...)`.

### `trimmed<T,S>(struct): Struct<T,S>`
Coerces string input by calling `.trim()`. Implemented via
`coerce(struct, string(), x => x.trim())`.
