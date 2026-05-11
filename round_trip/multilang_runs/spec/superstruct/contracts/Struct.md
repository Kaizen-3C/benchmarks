# Contract: `Struct<T, S>` (src/struct.ts)

## Class `Struct<T, S>`

### Properties
| Name | Type | Description |
|------|------|-------------|
| `TYPE` | `T` (phantom) | TypeScript type extraction helper |
| `type` | `string` | Name used in error messages |
| `schema` | `S` | Raw schema for introspection |
| `coercer` | `(value: unknown, ctx: Context) => unknown` | Transforms input before validation; identity by default |
| `validator` | `(value: unknown, ctx: Context) => Iterable<Failure>` | Structural check; returns empty iterable if valid |
| `refiner` | `(value: T, ctx: Context) => Iterable<Failure>` | Constraint check after structure passes; returns empty iterable if valid |
| `entries` | `(value: unknown, ctx: Context) => Iterable<[string\|number, unknown, Struct]>` | Yields child key/value/struct triples for recursive traversal |

### Constructor
```ts
new Struct<T, S>(props: {
  type: string; schema: S;
  coercer?: Coercer; validator?: Validator;
  refiner?: Refiner<T>; entries?: Struct<T,S>['entries']
})
```
`coercer` defaults to identity. `entries` defaults to empty generator.
`validator` and `refiner` wrap supplied functions via `toFailures`.

### Instance Methods
- `assert(value: unknown, message?: string): asserts value is T` — throws `StructError` if invalid
- `create(value: unknown, message?: string): T` — coerces then validates; throws on failure
- `is(value: unknown): value is T` — returns `boolean`
- `mask(value: unknown, message?: string): T` — coerces with masking then validates
- `validate(value: unknown, options?: { coerce?: boolean; mask?: boolean; message?: string }): [StructError, undefined] | [undefined, T]`

## Module-level helpers

### `assert<T,S>(value, struct, message?): asserts value is T`
Runs `validate`; throws first `StructError` if invalid.

### `create<T,S>(value, struct, message?): T`
Runs `validate` with `coerce: true`; throws on failure, returns coerced value.

### `mask<T,S>(value, struct, message?): T`
Runs `validate` with `coerce: true, mask: true`; strips unknown object keys recursively.

### `is<T,S>(value, struct): value is T`
Returns `true` iff validation produces no errors.

### `validate<T,S>(value, struct, options?): [StructError, undefined] | [undefined, T]`
Returns a result tuple. On failure index 0 is a `StructError` with lazy `.failures()`.

## Types
```ts
type Context = { branch: any[]; path: any[]; mask?: boolean }
type Infer<T extends Struct<any,any>> = T['TYPE']
type Describe<T> = Struct<T, StructSchema<T>>
type Result = boolean | string | Partial<Failure> | Iterable<boolean | string | Partial<Failure>>
type Coercer<T = unknown> = (value: T, ctx: Context) => unknown
type Validator = (value: unknown, ctx: Context) => Result
type Refiner<T> = (value: T, ctx: Context) => Result
```
