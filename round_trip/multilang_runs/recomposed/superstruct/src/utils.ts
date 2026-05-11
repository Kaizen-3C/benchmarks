import { Struct, Infer, Result, Context } from './struct.js'
import { Failure } from './error.js'

export type UnionToIntersection<U> = (
  U extends any ? (k: U) => void : never
) extends (k: infer I) => void
  ? I
  : never

export type Assign<T, U> = U & Omit<T, keyof U>

export type ObjectSchema = Record<string, Struct<any, any>>

export type ObjectType<S extends ObjectSchema> = Optionalize<{
  [K in keyof S]: Infer<S[K]>
}>

export type Optionalize<S> = {
  [K in keyof S as undefined extends S[K] ? never : K]: S[K]
} & {
  [K in keyof S as undefined extends S[K] ? K : never]?: S[K]
}

export type PartialObjectSchema<S extends ObjectSchema> = {
  [K in keyof S]: Struct<Infer<S[K]> | undefined, any>
}

export type StructSchema<T> = T extends string
  ? null
  : T extends number
  ? null
  : T extends boolean
  ? null
  : T extends symbol
  ? null
  : T extends bigint
  ? null
  : T extends undefined
  ? null
  : T extends null
  ? null
  : T extends Array<infer E>
  ? Struct<E, any>
  : T extends Map<any, any>
  ? null
  : T extends Set<any>
  ? null
  : T extends object
  ? { [K in keyof T]: Describe<T[K]> }
  : null

export type Describe<T> = Struct<T, StructSchema<T>>

export type AnyStruct = Struct<any, any>

export type InferStructTuple<Tuple extends AnyStruct[]> = {
  [Index in keyof Tuple]: Infer<Tuple[Index]>
}

export function isObject(x: unknown): x is object {
  return typeof x === 'object' && x != null
}

export function isNonArrayObject(x: unknown): x is object {
  return isObject(x) && !Array.isArray(x)
}

export function isPlainObject(x: unknown): x is { [key: string]: any } {
  if (!isObject(x)) return false
  const proto = Object.getPrototypeOf(x)
  return proto === null || proto === Object.prototype
}

export function print(value: unknown): string {
  if (typeof value === 'string') {
    return JSON.stringify(value)
  }
  if (typeof value === 'symbol') {
    return value.toString()
  }
  return String(value)
}

export function shiftIterator<T>(input: Iterator<T>): T | undefined {
  const { value, done } = input.next()
  return done ? undefined : value
}

export function toFailure(
  result: boolean | string | Partial<Failure>,
  context: Context,
  struct: Struct<any, any>,
  value: unknown
): Failure | undefined {
  if (result === true) {
    return undefined
  }

  const { path, branch } = context
  const { type } = struct

  const failure: Failure = {
    value,
    key: path[path.length - 1],
    type,
    refinement: undefined,
    message: `Expected a value of type \`${type}\` but received: \`${print(value)}\``,
    branch,
    path,
  }

  if (result === false) {
    return failure
  }

  if (typeof result === 'string') {
    return { ...failure, message: result }
  }

  return { ...failure, ...result }
}

export function* toFailures(
  result: Result,
  context: Context,
  struct: Struct<any, any>,
  value: unknown
): IterableIterator<Failure> {
  if (
    typeof result !== 'boolean' &&
    typeof result !== 'string' &&
    result != null &&
    typeof (result as any)[Symbol.iterator] === 'function'
  ) {
    for (const r of result as Iterable<boolean | string | Partial<Failure>>) {
      const failure = toFailure(r, context, struct, value)
      if (failure != null) {
        yield failure
      }
    }
  } else {
    const failure = toFailure(
      result as boolean | string | Partial<Failure>,
      context,
      struct,
      value
    )
    if (failure != null) {
      yield failure
    }
  }
}

type RunOptions = {
  coerce?: boolean
  mask?: boolean
}

export function* run<T, S>(
  value: unknown,
  struct: Struct<T, S>,
  options: RunOptions = {}
): IterableIterator<[Failure, undefined] | [undefined, T]> {
  const { coerce = false, mask = false } = options

  const ctx: Context = {
    branch: [value],
    path: [],
    mask,
  }

  yield* runWithContext(value, struct, ctx, coerce)
}

function* runWithContext<T, S>(
  value: unknown,
  struct: Struct<T, S>,
  ctx: Context,
  coerce: boolean
): IterableIterator<[Failure, undefined] | [undefined, T]> {
  if (coerce) {
    value = struct.coercer(value, ctx)
    ctx = { ...ctx, branch: [...ctx.branch.slice(0, -1), value] }
  }

  let status: 'valid' | 'not_valid' | 'not_refined' = 'valid'

  for (const failure of struct.validator(value, ctx)) {
    status = 'not_valid'
    yield [failure, undefined]
  }

  if (status !== 'not_valid') {
    for (const [key, childValue, childStruct] of struct.entries(value, ctx)) {
      const childCtx: Context = {
        branch: [...ctx.branch, childValue],
        path: [...ctx.path, key],
        mask,
      }

      let childCoercedValue = childValue
      let childStatus: 'valid' | 'not_valid' | 'not_refined' = 'valid'

      if (coerce) {
        childCoercedValue = childStruct.coercer(childValue, childCtx)
        childCtx.branch = [...childCtx.branch.slice(0, -1), childCoercedValue]
      }

      for (const failure of childStruct.validator(childCoercedValue, childCtx)) {
        childStatus = 'not_valid'
        status = 'not_valid'
        yield [failure, undefined]
      }

      if (childStatus !== 'not_valid') {
        // Recurse deeper
        const childIter = runWithContext(childCoercedValue, childStruct, childCtx, coerce)
        let next = childIter.next()
        while (!next.done) {
          const item = next.value
          if (item[0] != null) {
            if (item[0].refinement != null) {
              if (childStatus === 'valid') childStatus = 'not_refined'
              if (status === 'valid') status = 'not_refined'
            } else {
              childStatus = 'not_valid'
              status = 'not_valid'
            }
            yield [item[0], undefined]
          } else {
            // coerced child value
            childCoercedValue = item[1] as unknown
          }
          next = childIter.next()
        }
      }

      if (coerce && childCoercedValue !== childValue) {
        if (isObject(value)) {
          ;(value as any)[key] = childCoercedValue
        }
      }

      if (childStatus === 'not_refined' && status === 'valid') {
        status = 'not_refined'
      }
    }
  }

  if (status !== 'not_valid') {
    for (const failure of struct.refiner(value as T, ctx)) {
      status = 'not_refined'
      yield [failure, undefined]
    }
  }

  if (status === 'valid') {
    yield [undefined, value as T]
  }
}

function isObject(x: unknown): x is object {
  return typeof x === 'object' && x != null
}
