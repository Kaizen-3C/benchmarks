import { Struct, is, Coercer } from '../struct.js'
import { isPlainObject } from '../utils.js'
import { string, unknown } from './types.js'

export function coerce<T, S, C>(
  struct: Struct<T, S>,
  condition: Struct<C, any>,
  coercer: (value: C, ctx: any) => unknown
): Struct<T, S> {
  return new Struct({
    ...struct,
    coercer(value, ctx) {
      if (is(value, condition)) {
        return struct.coercer(coercer(value as C, ctx), ctx)
      }
      return struct.coercer(value, ctx)
    },
  })
}

export function defaulted<T, S>(
  struct: Struct<T, S>,
  fallback: any,
  options?: { strict?: boolean }
): Struct<T, S> {
  return coerce(struct, unknown(), (value) => {
    const f = typeof fallback === 'function' ? fallback() : fallback
    if (value === undefined) {
      return f
    }
    if (!options?.strict && isPlainObject(value) && isPlainObject(f)) {
      const result = { ...value }
      for (const key of Object.keys(f)) {
        if ((result as any)[key] === undefined) {
          ;(result as any)[key] = (f as any)[key]
        }
      }
      return result
    }
    return value
  })
}

export function trimmed<T extends string, S>(struct: Struct<T, S>): Struct<T, S> {
  return coerce(struct, string(), (x) => x.trim()) as Struct<T, S>
}
