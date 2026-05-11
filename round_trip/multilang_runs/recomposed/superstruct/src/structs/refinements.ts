import { Struct, Refiner } from '../struct.js'
import { toFailures } from '../utils.js'

export function refine<T, S>(
  struct: Struct<T, S>,
  name: string,
  refiner: Refiner<T>
): Struct<T, S> {
  return new Struct({
    ...struct,
    refiner(value, ctx) {
      return (function* () {
        yield* struct.refiner(value, ctx)
        const result = refiner(value, ctx)
        for (const failure of toFailures(result, ctx, struct, value)) {
          yield { ...failure, refinement: name }
        }
      })()
    },
  })
}

export function empty<T extends string | any[] | Map<any, any> | Set<any>, S>(
  struct: Struct<T, S>
): Struct<T, S> {
  return refine(struct, 'empty', (value) => {
    const size =
      value instanceof Map || value instanceof Set
        ? value.size
        : (value as string | any[]).length
    return size === 0 || `Expected an empty value, but received one with size \`${size}\``
  })
}

export function nonempty<T extends string | any[] | Map<any, any> | Set<any>, S>(
  struct: Struct<T, S>
): Struct<T, S> {
  return refine(struct, 'nonempty', (value) => {
    const size =
      value instanceof Map || value instanceof Set
        ? value.size
        : (value as string | any[]).length
    return size > 0 || `Expected a nonempty value, but received an empty one`
  })
}

export function min<T extends number | Date, S>(
  struct: Struct<T, S>,
  threshold: T,
  options?: { exclusive?: boolean }
): Struct<T, S> {
  return refine(struct, 'min', (value) => {
    const v = value instanceof Date ? value.getTime() : (value as number)
    const t = threshold instanceof Date ? threshold.getTime() : (threshold as number)
    return options?.exclusive
      ? v > t || `Expected a value greater than \`${print(threshold)}\`, but received: \`${print(value)}\``
      : v >= t || `Expected a value greater than or equal to \`${print(threshold)}\`, but received: \`${print(value)}\``
  })
}

export function max<T extends number | Date, S>(
  struct: Struct<T, S>,
  threshold: T,
  options?: { exclusive?: boolean }
): Struct<T, S> {
  return refine(struct, 'max', (value) => {
    const v = value instanceof Date ? value.getTime() : (value as number)
    const t = threshold instanceof Date ? threshold.getTime() : (threshold as number)
    return options?.exclusive
      ? v < t || `Expected a value less than \`${print(threshold)}\`, but received: \`${print(value)}\``
      : v <= t || `Expected a value less than or equal to \`${print(threshold)}\`, but received: \`${print(value)}\``
  })
}

export function pattern<T extends string, S>(
  struct: Struct<T, S>,
  regexp: RegExp
): Struct<T, S> {
  return refine(struct, 'pattern', (value) => {
    return (
      regexp.test(value) ||
      `Expected a value matching \`${regexp}\`, but received: \`${print(value)}\``
    )
  })
}

export function size<
  T extends string | number | Date | any[] | Map<any, any> | Set<any>,
  S
>(
  struct: Struct<T, S>,
  min: number,
  max: number = min
): Struct<T, S> {
  return refine(struct, 'size', (value) => {
    if (typeof value === 'number' || value instanceof Date) {
      const v = value instanceof Date ? value.getTime() : (value as number)
      return (
        (v >= min && v <= max) ||
        `Expected a value between \`${min}\` and \`${max}\`, but received: \`${print(value)}\``
      )
    }
    const len =
      value instanceof Map || value instanceof Set
        ? value.size
        : (value as string | any[]).length
    return (
      (len >= min && len <= max) ||
      `Expected a value with size between \`${min}\` and \`${max}\`, but received one with size \`${len}\``
    )
  })
}

function print(value: unknown): string {
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'symbol') return value.toString()
  return String(value)
}
