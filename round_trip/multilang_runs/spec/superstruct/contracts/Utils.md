# Contract: Utilities (src/utils.ts) — internal

These are not exported from the public index but are used internally.

### `isObject(x): x is object`
`typeof x === 'object' && x != null`

### `isNonArrayObject(x): x is object`
`isObject(x) && !Array.isArray(x)`

### `isPlainObject(x): x is { [key: string]: any }`
Checks `Object.prototype.toString` and prototype chain (null or Object.prototype).

### `print(value): string`
Returns `JSON.stringify(value)` for strings, `value.toString()` for symbols,
otherwise `String(value)`.

### `shiftIterator<T>(input: Iterator<T>): T | undefined`
Calls `input.next()`; returns value or `undefined` if done.

### `toFailure(result, context, struct, value): Failure | undefined`
Normalises one `Result` to a `Failure` or `undefined` (if `result === true`).
Default message: `` `Expected a value of type \`${type}\`..., but received: \`${print(value)}\`` ``

### `toFailures(result, context, struct, value): IterableIterator<Failure>`
Wraps non-iterable result in array, maps each through `toFailure`, yields
non-undefined failures.

### `run<T,S>(value, struct, options?): IterableIterator<[Failure,undefined]|[undefined,T]>`
Core traversal generator:
1. Optionally coerces value.
2. Yields failures from `struct.validator`.
3. Recursively runs `run` for each entry from `struct.entries`; collects coerced child values back when `coerce` is true.
4. Runs `struct.refiner` only if status is not `'not_valid'` (i.e., skips refiners when validators failed).
5. Yields `[undefined, value]` if status remains `'valid'`.

## Type utilities (exported)
- `UnionToIntersection<U>` — converts union to intersection
- `Assign<T, U>` — `U & Omit<T, keyof U>` simplified
- `ObjectSchema` — `Record<string, Struct<any,any>>`
- `ObjectType<S>` — infers object shape from schema, normalising optionals
- `Optionalize<S>` — makes properties that can be `undefined` optional
- `PartialObjectSchema<S>` — all values become `Struct<T|undefined>`
- `StructSchema<T>` — maps TypeScript type T to its schema type
- `AnyStruct` — `Struct<any,any>`
- `InferStructTuple<Tuple>` — maps tuple of structs to tuple of their types
