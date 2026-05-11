import { Infer, Struct } from '../struct.js'
import { define } from './utilities.js'
import {
  ObjectSchema,
  ObjectType,
  print,
  isObject,
  isNonArrayObject,
  AnyStruct,
  InferStructTuple,
  UnionToIntersection,
} from '../utils.js'

export function any(): Struct<any, null> {
  return new Struct({
    type: 'any',
    schema: null,
    validator: () => true,
  })
}

export function array(): Struct<unknown[], undefined>
export function array<T extends AnyStruct>(element: T): Struct<Infer<T>[], T>
export function array<T extends AnyStruct>(element?: T): any {
  return new Struct({
    type: 'array',
    schema: element,
    coercer: (value) => (Array.isArray(value) ? value.slice() : value),
    validator(value) {
      return Array.isArray(value) || `Expected an array, but received: ${print(value)}`
    },
    entries:
      element == null
        ? undefined
        : function* (value) {
            if (Array.isArray(value)) {
              for (let i = 0; i < value.length; i++) {
                yield [i, value[i], element]
              }
            }
          },
  })
}

export function bigint(): Struct<bigint, null> {
  return define('bigint', (value) => {
    return typeof value === 'bigint' || `Expected a bigint, but received: ${print(value)}`
  })
}

export function boolean(): Struct<boolean, null> {
  return define('boolean', (value) => {
    return typeof value === 'boolean' || `Expected a boolean, but received: ${print(value)}`
  })
}

export function date(): Struct<Date, null> {
  return define('date', (value) => {
    return (
      (value instanceof Date && !isNaN(value.getTime())) ||
      `Expected a valid Date, but received: ${print(value)}`
    )
  })
}

export function enums<T extends string | number>(
  values: readonly T[]
): Struct<T, { [K in T]: K }> {
  const schema: any = {}
  for (const val of values) {
    schema[val] = val
  }
  const set = new Set(values)
  return new Struct({
    type: 'enums',
    schema,
    validator(value) {
      return (
        set.has(value as T) ||
        `Expected one of \`${values.map(print).join(', ')}\`, but received: ${print(value)}`
      )
    },
  })
}

export function func(): Struct<Function, null> {
  return define('func', (value) => {
    return typeof value === 'function' || `Expected a function, but received: ${print(value)}`
  })
}

export function instance<T extends new (...args: any[]) => any>(
  Class: T
): Struct<InstanceType<T>, null> {
  return define('instance', (value) => {
    return (
      value instanceof Class ||
      `Expected an instance of \`${Class.name}\`, but received: ${print(value)}`
    )
  })
}

export function integer(): Struct<number, null> {
  return define('integer', (value) => {
    return (
      (typeof value === 'number' && !isNaN(value) && Number.isInteger(value)) ||
      `Expected an integer, but received: ${print(value)}`
    )
  })
}

export function intersection<A extends AnyStruct, B extends AnyStruct[]>(
  structs: [A, ...B]
): Struct<Infer<A> & UnionToIntersection<Infer<B[number]>>, null> {
  return new Struct({
    type: 'intersection',
    schema: null,
    validator(value, ctx) {
      return structs.flatMap((s) => [...s.validator(value, ctx)])
    },
    refiner(value, ctx) {
      return structs.flatMap((s) => [...s.refiner(value as any, ctx)])
    },
    entries: function* (value, ctx) {
      for (const s of structs) {
        yield* s.entries(value, ctx)
      }
    },
  })
}

export function literal<T extends string | number | boolean | null | undefined>(
  constant: T
): Struct<T, T extends string | number | boolean ? T : null> {
  const schema: any =
    typeof constant === 'string' ||
    typeof constant === 'number' ||
    typeof constant === 'boolean'
      ? constant
      : null
  return new Struct({
    type: 'literal',
    schema,
    validator(value) {
      return (
        value === constant ||
        `Expected the literal \`${print(constant)}\`, but received: ${print(value)}`
      )
    },
  })
}

export function map(): Struct<Map<unknown, unknown>, null>
export function map<K extends AnyStruct, V extends AnyStruct>(
  key: K,
  value: V
): Struct<Map<Infer<K>, Infer<V>>, null>
export function map(key?: AnyStruct, value?: AnyStruct): any {
  return new Struct({
    type: 'map',
    schema: null,
    coercer: (val) => (val instanceof Map ? new Map(val as Map<any, any>) : val),
    validator(val) {
      return val instanceof Map || `Expected a Map, but received: ${print(val)}`
    },
    entries:
      key == null || value == null
        ? undefined
        : function* (val) {
            if (val instanceof Map) {
              for (const [k, v] of val) {
                yield [k, k, key]
                yield [k, v, value]
              }
            }
          },
  })
}

export function never(): Struct<never, null> {
  return define('never', () => false)
}

export function nullable<T, S>(
  struct: Struct<T, S>
): Struct<T | null, S> {
  return new Struct({
    ...struct,
    validator(value, ctx) {
      return value === null ? [] : struct.validator(value, ctx)
    },
    refiner(value, ctx) {
      return value === null ? [] : struct.refiner(value as T, ctx)
    },
  })
}

export function number(): Struct<number, null> {
  return define('number', (value) => {
    return (
      (typeof value === 'number' && !isNaN(value)) ||
      `Expected a number, but received: ${print(value)}`
    )
  })
}

export function object(): Struct<Record<string, unknown>, null>
export function object<S extends ObjectSchema>(
  schema: S
): Struct<ObjectType<S>, S>
export function object(schema?: ObjectSchema): any {
  const knowns = schema ? Object.keys(schema) : []
  const Never = never()

  return new Struct({
    type: 'object',
    schema: schema ?? null,
    coercer(value, ctx) {
      if (!isNonArrayObject(value)) return value
      const output: any = { ...(value as object) }
      if (ctx.mask && schema) {
        for (const key of Object.keys(output)) {
          if (!(key in schema)) {
            delete output[key]
          }
        }
      }
      return output
    },
    validator(value) {
      return (
        isNonArrayObject(value) ||
        `Expected an object, but received: ${print(value)}`
      )
    },
    entries:
      schema == null
        ? undefined
        : function* (value) {
            if (!isNonArrayObject(value)) return
            const obj = value as Record<string, unknown>
            for (const key of knowns) {
              yield [key, obj[key], schema[key]]
            }
            const unknownKeys = Object.keys(obj).filter((k) => !knowns.includes(k))
            for (const key of unknownKeys) {
              yield [key, obj[key], Never]
            }
          },
  })
}

export function optional<T, S>(
  struct: Struct<T, S>
): Struct<T | undefined, S> {
  return new Struct({
    ...struct,
    validator(value, ctx) {
      return value === undefined ? [] : struct.validator(value, ctx)
    },
    refiner(value, ctx) {
      return value === undefined ? [] : struct.refiner(value as T, ctx)
    },
  })
}

export function record<K extends string, V extends AnyStruct>(
  key: Struct<K, any>,
  value: V
): Struct<Record<K, Infer<V>>, null> {
  return new Struct({
    type: 'record',
    schema: null,
    coercer: (val) => (isNonArrayObject(val) ? { ...(val as object) } : val),
    validator(val) {
      return (
        isNonArrayObject(val) ||
        `Expected an object, but received: ${print(val)}`
      )
    },
    entries: function* (val) {
      if (isNonArrayObject(val)) {
        const obj = val as Record<string, unknown>
        for (const k of Object.keys(obj)) {
          yield [k, k, key]
          yield [k, obj[k], value]
        }
      }
    },
  })
}

export function regexp(): Struct<RegExp, null> {
  return define('regexp', (value) => {
    return value instanceof RegExp || `Expected a RegExp, but received: ${print(value)}`
  })
}

export function set(): Struct<Set<unknown>, null>
export function set<T extends AnyStruct>(element: T): Struct<Set<Infer<T>>, null>
export function set(element?: AnyStruct): any {
  return new Struct({
    type: 'set',
    schema: null,
    coercer: (value) => (value instanceof Set ? new Set(value as Set<any>) : value),
    validator(value) {
      return value instanceof Set || `Expected a Set, but received: ${print(value)}`
    },
    entries:
      element == null
        ? undefined
        : function* (value) {
            if (value instanceof Set) {
              for (const val of value) {
                yield [val, val, element]
              }
            }
          },
  })
}

export function string(): Struct<string, null> {
  return define('string', (value) => {
    return typeof value === 'string' || `Expected a string, but received: ${print(value)}`
  })
}

export function tuple<T extends AnyStruct[]>(
  structs: [...T]
): Struct<InferStructTuple<T>, null> {
  const Never = never()
  return new Struct({
    type: 'tuple',
    schema: null,
    coercer: (value) => (Array.isArray(value) ? value.slice() : value),
    validator(value) {
      return Array.isArray(value) || `Expected an array, but received: ${print(value)}`
    },
    entries: function* (value) {
      if (!Array.isArray(value)) return
      for (let i = 0; i < structs.length; i++) {
        yield [i, value[i], structs[i]]
      }
      for (let i = structs.length; i < value.length; i++) {
        yield [i, value[i], Never]
      }
    },
  })
}

export function type<S extends ObjectSchema>(schema: S): Struct<ObjectType<S>, S> {
  const knowns = Object.keys(schema)
  return new Struct({
    type: 'type',
    schema,
    coercer: (value) => (isNonArrayObject(value) ? { ...(value as object) } : value),
    validator(value) {
      return (
        isNonArrayObject(value) ||
        `Expected an object, but received: ${print(value)}`
      )
    },
    entries: function* (value) {
      if (!isNonArrayObject(value)) return
      const obj = value as Record<string, unknown>
      for (const key of knowns) {
        yield [key, obj[key], schema[key]]
      }
    },
  })
}

export function union<T extends AnyStruct[]>(
  structs: [...T]
): Struct<Infer<T[number]>, null> {
  return new Struct({
    type: 'union',
    schema: null,
    coercer(value, ctx) {
      for (const s of structs) {
        const coerced = s.coercer(value, ctx)
        let valid = true
        for (const _ of s.validator(coerced, ctx)) {
          valid = false
          break
        }
        if (valid) return coerced
      }
      return value
    },
    validator(value, ctx) {
      const failures = []
      for (const s of structs) {
        let valid = true
        for (const f of s.validator(value, ctx)) {
          valid = false
          break
        }
        if (valid) {
          // also check entries
          return []
        }
      }
      return [
        {
          type: 'union',
          refinement: undefined,
          value,
          key: ctx.path[ctx.path.length - 1],
          path: ctx.path,
          branch: ctx.branch,
          message: `Expected a value of type \`union\`, but received: \`${print(value)}\``,
        },
      ]
    },
  })
}

export function unknown(): Struct<unknown, null> {
  return new Struct({
    type: 'unknown',
    schema: null,
    validator: () => true,
  })
}
