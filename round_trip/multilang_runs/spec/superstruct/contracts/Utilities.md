# Contract: Utilities (src/structs/utilities.ts)

### `define<T>(name, validator): Struct<T, null>`
Creates a struct with a custom `Validator` function. Schema is `null`.

### `assign(A, B, ...): Struct<...>`
Merges schemas of two-to-five `object` or `type` structs via `Object.assign`.
Result type is `object` unless the first struct is `type`, in which case result
is `type`. Overloads for 2–5 arguments.

### `deprecated<T>(struct, log): Struct<T>`
If value is `undefined`, passes. Otherwise calls `log(value, ctx)` and
delegates to original struct's validator. Refiner also passes if `undefined`.

### `dynamic<T>(fn): Struct<T, null>`
Calls `fn(value, ctx)` at validation time to get the real struct. All
operations (entries, validator, coercer, refiner) delegate to the returned
struct.

### `lazy<T>(fn): Struct<T, null>`
Like `dynamic` but `fn` is called only once; result is cached (using `??=`).
Used for self-referential / recursive structs.

### `omit<S, K>(struct, keys): Struct<...>`
Removes listed keys from an `object` or `type` struct's schema.
Result preserves the original struct type (`object` vs `type`).

### `partial<S>(struct | schema): Struct<...>`
Makes all properties optional by wrapping each schema value in `optional()`.
Accepts either a `Struct` instance or a plain schema object.
Result is `type` if input is a `type` struct, otherwise `object`.

### `pick<S, K>(struct, keys): Struct<...>`
Keeps only listed keys in the schema; removes the rest.
Result preserves `object` vs `type`.

### `struct<T>(name, validator): Struct<T, null>`
**Deprecated.** Alias for `define`. Logs a console warning.
