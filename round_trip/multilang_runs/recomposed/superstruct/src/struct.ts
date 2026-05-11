import { toFailures, shiftIterator, run } from './utils.js'
import type { StructSchema } from './utils.js'
import { StructError, Failure } from './error.js'

export type Context = {
  branch: any[]
  path: any[]
  mask?: boolean
}

export type Result =
  | boolean
  | string
  | Partial<Failure>
  | Iterable<boolean | string | Partial<Failure>>

export type Coercer<T = unknown> = (value: T, ctx: Context) => unknown
export type Validator = (value: unknown, ctx: Context) => Result
export type Refiner<T> = (value: T, ctx: Context) => Result

export type Infer<T extends Struct<any, any>> = T['TYPE']
export type Describe<T> = Struct<T, StructSchema<T>>

export class Struct<T, S> {
  readonly TYPE!: T
  type: string
  schema: S
  coercer: (value: unknown, ctx: Context) => unknown
  validator: (value: unknown, ctx: Context) => Iterable<Failure>
  refiner: (value: T, ctx: Context) => Iterable<Failure>
  entries: (
    value: unknown,
    ctx: Context
  ) => Iterable<[string | number, unknown, Struct<any, any>]>

  constructor(props: {
    type: string
    schema: S
    coercer?: (value: unknown, ctx: Context) => unknown
    validator?: Validator
    refiner?: Refiner<T>
    entries?: Struct<T, S>['entries']
  }) {
    const {
      type,
      schema,
      coercer = (x: unknown) => x,
      validator,
      refiner,
      entries = function* () {},
    } = props

    this.type = type
    this.schema = schema
    this.coercer = coercer
    this.entries = entries

    if (validator) {
      this.validator = (value, ctx) => toFailures(validator(value, ctx), ctx, this, value)
    } else {
      this.validator = function* () {}
    }

    if (refiner) {
      this.refiner = (value, ctx) => toFailures(refiner(value, ctx), ctx, this, value)
    } else {
      this.refiner = function* () {}
    }
  }

  assert(value: unknown, message?: string): asserts value is T {
    assert(value, this, message)
  }

  create(value: unknown, message?: string): T {
    return create(value, this, message)
  }

  is(value: unknown): value is T {
    return is(value, this)
  }

  mask(value: unknown, message?: string): T {
    return mask(value, this, message)
  }

  validate(
    value: unknown,
    options?: { coerce?: boolean; mask?: boolean; message?: string }
  ): [StructError, undefined] | [undefined, T] {
    return validate(value, this, options)
  }
}

export function assert<T, S>(
  value: unknown,
  struct: Struct<T, S>,
  message?: string
): asserts value is T {
  const result = validate(value, struct, { message })
  if (result[0]) {
    throw result[0]
  }
}

export function create<T, S>(
  value: unknown,
  struct: Struct<T, S>,
  message?: string
): T {
  const result = validate(value, struct, { coerce: true, message })
  if (result[0]) {
    throw result[0]
  }
  return result[1]!
}

export function mask<T, S>(
  value: unknown,
  struct: Struct<T, S>,
  message?: string
): T {
  const result = validate(value, struct, { coerce: true, mask: true, message })
  if (result[0]) {
    throw result[0]
  }
  return result[1]!
}

export function is<T, S>(value: unknown, struct: Struct<T, S>): value is T {
  const result = validate(value, struct)
  return !result[0]
}

export function validate<T, S>(
  value: unknown,
  struct: Struct<T, S>,
  options: { coerce?: boolean; mask?: boolean; message?: string } = {}
): [StructError, undefined] | [undefined, T] {
  const iter = run(value, struct, options)
  const first = shiftIterator(iter)

  if (first == null) {
    return [undefined, value as T]
  }

  const [failure, coerced] = first

  if (failure == null) {
    return [undefined, coerced as T]
  }

  const explanation = options.message

  const finalFailure: Failure = explanation
    ? { ...failure, explanation }
    : failure

  const error = new StructError(finalFailure, function* () {
    let next = iter.next()
    while (!next.done) {
      const [f] = next.value
      if (f != null) {
        yield f
      }
      next = iter.next()
    }
  })

  return [error, undefined]
}
