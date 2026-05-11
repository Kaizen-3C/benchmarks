# Contract: Refinements (src/structs/refinements.ts)

Refinement functions receive a value already confirmed to be of the struct's
type, so their argument is typed `T`.

### `refine<T,S>(struct, name, refiner): Struct<T,S>`
Layers an additional refiner on top of an existing struct. Failures from the
new refiner have `refinement` set to `name`. The original struct's refiner runs
first.

### `empty<T extends string|any[]|Map|Set, S>(struct): Struct<T,S>`
Refines with name `'empty'`. Passes iff `size === 0`.

### `nonempty<T extends string|any[]|Map|Set, S>(struct): Struct<T,S>`
Refines with name `'nonempty'`. Passes iff `size > 0`.

### `min<T extends number|Date, S>(struct, threshold, options?): Struct<T,S>`
Refines with name `'min'`. `options.exclusive` makes the check `>` instead of `>=`.

### `max<T extends number|Date, S>(struct, threshold, options?): Struct<T,S>`
Refines with name `'max'`. `options.exclusive` makes the check `<` instead of `<=`.

### `pattern<T extends string, S>(struct, regexp): Struct<T,S>`
Refines with name `'pattern'`. Passes iff `regexp.test(value)`.

### `size<T extends string|number|Date|any[]|Map|Set, S>(struct, min, max?): Struct<T,S>`
Refines with name `'size'`. `max` defaults to `min` (exact size).
- For `number`/`Date`: checks `min <= value <= max`.
- For `Map`/`Set`: checks `min <= .size <= max`.
- For `string`/`Array`: checks `min <= .length <= max`.
