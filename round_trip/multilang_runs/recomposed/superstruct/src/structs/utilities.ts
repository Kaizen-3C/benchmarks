import { Context, Struct, Validator } from '../struct.js'
import { Assign, ObjectSchema, ObjectType, PartialObjectSchema } from '../utils.js'
import { object, optional, type } from './types.js'

export function define<T>(name: string, validator: Validator): Struct<T, null> {
  return new Struct<T, null>({ type: name, schema: null, validator })
}

type TwoToFive<A, B, C = undefined, D = undefined, E = undefined> = C extends undefined
  ? [A, B]
  : D extends undefined
  ? [A, B, C]
  : E extends undefined
  ? [A, B, C, D]
  : [A, B, C, D, E]

export function assign<A extends ObjectSchema, B extends ObjectSchema>(
  a: Struct<ObjectType<A>, A>,
  b: Struct<ObjectType<B>, B>
): Struct<ObjectType<Assign<A, B>>, Assign<A, B>>
export function assign<
  A extends ObjectSchema,
  B extends ObjectSchema,
  C extends ObjectSchema
>(
  a: Struct<ObjectType<A>, A>,
  b: Struct<ObjectType<B>, B>,
  c: Struct<ObjectType<C>, C>
): Struct<ObjectType<Assign<Assign<A, B>, C>>, Assign<Assign<A, B>, C>>
export function assign(...structs: Struct<any, any>[]): Struct<any, any> {
  const schema = Object.assign({}, ...structs.map((s) => s.schema))
  const first = structs[0]
  if (first.type === 'type') {
    return type(schema)
  }
  return object(schema)
}

export function deprecated<T>(
  struct: Struct<T, any>,
  log: (value: unknown, ctx: Context) => void
): Struct<T, any> {
  return new Struct({
    ...struct,
    validator(value, ctx) {
      if (value !== undefined) {
        log(value, ctx)
        return struct.validator(value, ctx)
      }
      return []
    },
    refiner(value, ctx) {
      if (value === undefined) return []
      return struct.refiner(value as T, ctx)
    },
  })
}

export function dynamic<T>(
  fn: (value: unknown, ctx: Context) => Struct<T, any>
): Struct<T, null> {
  return new Struct({
    type: 'dynamic',
    schema: null,
    coercer(value, ctx) {
      return fn(value, ctx).coercer(value, ctx)
    },
    validator(value, ctx) {
      return fn(value, ctx).validator(value, ctx)
    },
    refiner(value, ctx) {
      return fn(value, ctx).refiner(value as T, ctx)
    },
    entries(value, ctx) {
      return fn(value, ctx).entries(value, ctx)
    },
  })
}

export function lazy<T>(fn: () => Struct<T, any>): Struct<T, null> {
  let cached: Struct<T, any> | undefined
  return new Struct({
    type: 'lazy',
    schema: null,
    coercer(value, ctx) {
      cached ??= fn()
      return cached.coercer(value, ctx)
    },
    validator(value, ctx) {
      cached ??= fn()
      return cached.validator(value, ctx)
    },
    refiner(value, ctx) {
      cached ??= fn()
      return cached.refiner(value as T, ctx)
    },
    entries(value, ctx) {
      cached ??= fn()
      return cached.entries(value, ctx)
    },
  })
}

export function omit<S extends ObjectSchema, K extends keyof S>(
  struct: Struct<ObjectType<S>, S>,
  keys: K[]
): Struct<ObjectType<Omit<S, K>>, Omit<S, K>> {
  const schema = { ...struct.schema }
  for (const key of keys) {
    delete schema[key as string]
  }
  if (struct.type === 'type') {
    return type(schema as any) as any
  }
  return object(schema as any) as any
}

export function partial<S extends ObjectSchema>(
  structOrSchema: Struct<ObjectType<S>, S> | S
): Struct<ObjectType<PartialObjectSchema<S>>, PartialObjectSchema<S>> {
  const schema: ObjectSchema =
    structOrSchema instanceof Struct ? { ...structOrSchema.schema } : { ...structOrSchema }
  const isType =
    structOrSchema instanceof Struct && structOrSchema.type === 'type'

  const partialSchema: ObjectSchema = {}
  for (const key of Object.keys(schema)) {
    partialSchema[key] = optional(schema[key])
  }

  if (isType) {
    return type(partialSchema as any) as any
  }
  return object(partialSchema as any) as any
}

export function pick<S extends ObjectSchema, K extends keyof S>(
  struct: Struct<ObjectType<S>, S>,
  keys: K[]
): Struct<ObjectType<Pick<S, K>>, Pick<S, K>> {
  const schema: ObjectSchema = {}
  for (const key of keys) {
    schema[key as string] = struct.schema[key as string]
  }
  if (struct.type === 'type') {
    return type(schema as any) as any
  }
  return object(schema as any) as any
}

export function struct<T>(name: string, validator: Validator): Struct<T, null> {
  console.warn(
    'superstruct: The `struct` helper is deprecated. Use `define` instead.'
  )
  return define(name, validator)
}
