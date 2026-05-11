# Contract: Types (src/structs/types.ts)

Each factory returns a `Struct<T, S>` instance. Schemas and exact type
parameters are listed per function.

| Factory | Return Type | Schema | Notes |
|---------|-------------|--------|-------|
| `any()` | `Struct<any, null>` | null | Always passes |
| `array()` | `Struct<unknown[], undefined>` | undefined | No element iteration |
| `array(El)` | `Struct<Infer<El>[], El>` | El | Iterates elements |
| `bigint()` | `Struct<bigint, null>` | null | `typeof === 'bigint'` |
| `boolean()` | `Struct<boolean, null>` | null | `typeof === 'boolean'` |
| `date()` | `Struct<Date, null>` | null | instanceof Date AND !isNaN |
| `enums(values)` | `Struct<T[number], {[K in T[number]]: K}>` | schema object | Accepts string or number arrays |
| `func()` | `Struct<Function, null>` | null | `typeof === 'function'` |
| `instance(Class)` | `Struct<InstanceType<T>, null>` | null | `instanceof Class` |
| `integer()` | `Struct<number, null>` | null | number AND !isNaN AND Number.isInteger |
| `intersection([A,...B])` | `Struct<Infer<A> & ..., null>` | null | All structs' validators/refiners/entries run |
| `literal(c)` | `Struct<T, T\|null>` | constant (for primitives) | strict `===` equality |
| `map()` | `Struct<Map<unknown,unknown>, null>` | null | No key/value iteration |
| `map(K,V)` | `Struct<Map<K,V>, null>` | null | Iterates keys and values |
| `never()` | `Struct<never, null>` | null | Always fails |
| `nullable(struct)` | `Struct<T\|null, S>` | (inherits) | Passes if `=== null` OR original passes |
| `number()` | `Struct<number, null>` | null | `typeof === 'number'` AND !isNaN |
| `object()` | `Struct<Record<string,unknown>, null>` | null | No key iteration |
| `object(schema)` | `Struct<ObjectType<S>, S>` | schema | Rejects unknown keys via `never()` |
| `optional(struct)` | `Struct<T\|undefined, S>` | (inherits) | Passes if `=== undefined` OR original passes |
| `record(K,V)` | `Struct<Record<K,V>, null>` | null | Iterates all keys as K, all values as V |
| `regexp()` | `Struct<RegExp, null>` | null | `instanceof RegExp` |
| `set()` | `Struct<Set<unknown>, null>` | null | No element iteration |
| `set(El)` | `Struct<Set<T>, null>` | null | Iterates elements |
| `string()` | `Struct<string, null>` | null | `typeof === 'string'` |
| `tuple([A,...B])` | `Struct<[Infer<A>,...], null>` | null | Length checked; extra elements fail via `never()` |
| `type(schema)` | `Struct<ObjectType<S>, S>` | schema | Unknown keys allowed (open struct) |
| `union([A,...B])` | `Struct<Infer<A>\|..., null>` | null | First matching struct wins for coercion |
| `unknown()` | `Struct<unknown, null>` | null | Always passes |

### Coercer behaviour for mutable cloning
- `array`: `value.slice()`
- `map`: `new Map(value)`
- `set`: `new Set(value)`
- `object`/`type`/`record`: `{ ...value }`
- `tuple`: `value.slice()`
- `object` with `ctx.mask`: deletes keys not in schema before returning copy
