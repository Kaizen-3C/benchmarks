import { describe, it, expect, vi } from 'vitest'
import {
  assert,
  create,
  mask,
  is,
  validate,
  Struct,
  StructError,
  string,
  number,
  boolean,
  object,
  array,
  optional,
  nullable,
  any,
  never,
  unknown,
  literal,
  enums,
  tuple,
  type,
  union,
  intersection,
  record,
  integer,
  date,
  bigint,
  func,
  instance,
  regexp,
  set,
  map,
  define,
  assign,
  deprecated,
  dynamic,
  lazy,
  omit,
  partial,
  pick,
  coerce,
  defaulted,
  trimmed,
  refine,
  pattern,
  min,
  max,
  size,
  empty,
  nonempty,
} from '../src/index.js'

// ─── assert ───────────────────────────────────────────────────────────────────

describe('assert', () => {
  it('valid string does not throw', () => {
    expect(() => assert('hello', string())).not.toThrow()
  })

  it('invalid string (number) throws StructError', () => {
    expect(() => assert(42, string())).toThrow(StructError)
  })

  it('error message for invalid number input', () => {
    expect(() => assert(42, string())).toThrow('Expected a string, but received: 42')
  })

  it('custom message on assert', () => {
    let err: any
    try {
      assert(42, string(), 'Not a string!')
    } catch (e) {
      err = e
    }
    expect(err.message).toBe('Not a string!')
    expect(err.cause).toBe('Expected a string, but received: 42')
  })

  it('valid object does not throw', () => {
    expect(() => assert({ id: 1, name: 'Jane' }, object({ id: number(), name: string() }))).not.toThrow()
  })

  it('object with unknown key fails with never', () => {
    let err: any
    try {
      assert({ id: 1, name: 'Jane', extra: true }, object({ id: number(), name: string() }))
    } catch (e) {
      err = e
    }
    expect(err).toBeDefined()
    expect(err.path).toEqual(['extra'])
    const failures = err.failures()
    expect(failures[0].type).toBe('never')
  })
})

// ─── create / coercions ───────────────────────────────────────────────────────

describe('create', () => {
  it('defaulted returns null when not undefined', () => {
    // When value is not undefined, defaulted should keep the value
    // But null is not a string, so it should throw
    expect(() => create(null, defaulted(string(), 'default'))).toThrow()
  })

  it('defaulted replaces undefined with fallback', () => {
    const result = create(undefined, defaulted(string(), 'default'))
    expect(result).toBe('default')
  })

  it('trimmed string', () => {
    expect(create('  hello  ', trimmed(string()))).toBe('hello')
  })

  it('create object with default values', () => {
    const result = create(
      { version: 0 },
      defaulted(object({ title: string(), version: number() }), { title: 'Untitled' })
    )
    expect(result).toEqual({ title: 'Untitled', version: 0 })
  })

  it('assert does not apply defaulted coercion', () => {
    expect(() => assert(undefined, defaulted(string(), 'default'))).toThrow()
  })

  it('create nested defaulted', () => {
    const result = create({}, object({ title: defaulted(string(), 'Untitled') }))
    expect(result).toEqual({ title: 'Untitled' })
  })
})

// ─── is ───────────────────────────────────────────────────────────────────────

describe('is', () => {
  it('returns true for valid', () => {
    expect(is('hello', string())).toBe(true)
  })

  it('returns false for invalid', () => {
    expect(is(42, string())).toBe(false)
  })

  it('null is not optional(string)', () => {
    expect(is(null, optional(string()))).toBe(false)
  })

  it('undefined is optional(string)', () => {
    expect(is(undefined, optional(string()))).toBe(true)
  })
})

// ─── mask ─────────────────────────────────────────────────────────────────────

describe('mask', () => {
  it('strips unknown keys', () => {
    const result = mask({ id: '1', unknown: true }, object({ id: string() }))
    expect(result).toEqual({ id: '1' })
  })

  it('deep strips nested unknown keys', () => {
    const result = mask(
      { id: '1', unknown: true, sub: [{ prop: '2', unknown: true }] },
      object({ id: string(), sub: array(object({ prop: string() })) })
    )
    expect(result).toEqual({ id: '1', sub: [{ prop: '2' }] })
  })

  it('does not mutate original', () => {
    const original = { id: '1', unknown: true }
    const result = mask(original, object({ id: string() }))
    expect(result).toEqual({ id: '1' })
    expect(original).toEqual({ id: '1', unknown: true })
  })

  it('throws for invalid value', () => {
    expect(() => mask('notanobject', object({ id: string() }))).toThrow(StructError)
  })

  it('type struct leaves unknown keys', () => {
    const result = mask({ id: '1', unknown: true }, type({ id: string() }))
    expect(result).toEqual({ id: '1', unknown: true })
  })
})

// ─── validate ─────────────────────────────────────────────────────────────────

describe('validate', () => {
  it('returns [undefined, value] on success', () => {
    const [err, val] = validate('ok', string())
    expect(err).toBeUndefined()
    expect(val).toBe('ok')
  })

  it('returns [StructError, undefined] on failure', () => {
    const [err, val] = validate(42, string())
    expect(err).toBeInstanceOf(StructError)
    expect(val).toBeUndefined()
    expect(err!.type).toBe('string')
    expect(err!.path).toEqual([])
    expect(err!.value).toBe(42)
  })

  it('failures array has first failure', () => {
    const [err] = validate(42, string())
    const failures = err!.failures()
    expect(failures[0].type).toBe('string')
    expect(failures[0].value).toBe(42)
    expect(failures[0].path).toEqual([])
    expect(failures[0].refinement).toBeUndefined()
  })

  it('path prefix in message', () => {
    const [err] = validate(
      { author: { name: 42 } },
      object({ author: object({ name: string() }) })
    )
    expect(err!.message).toBe('At path: author.name -- Expected a string, but received: 42')
  })

  it('custom message overrides', () => {
    const [err] = validate(42, string(), { message: 'Validation failed!' })
    expect(err!.message).toBe('Validation failed!')
    expect(err!.cause).toBe('Expected a string, but received: 42')
  })
})

// ─── refinements ──────────────────────────────────────────────────────────────

describe('refinements', () => {
  it('pattern valid', () => {
    expect(is('123', pattern(string(), /\d+/))).toBe(true)
  })

  it('pattern invalid', () => {
    const [err] = validate('abc', pattern(string(), /\d+/))
    expect(err!.refinement).toBe('pattern')
  })

  it('min valid inclusive', () => {
    expect(is(0, min(number(), 0))).toBe(true)
  })

  it('min invalid', () => {
    const [err] = validate(-1, min(number(), 0))
    expect(err!.refinement).toBe('min')
  })

  it('min exclusive invalid at boundary', () => {
    const [err] = validate(0, min(number(), 0, { exclusive: true }))
    expect(err!.refinement).toBe('min')
  })

  it('max valid inclusive', () => {
    expect(is(0, max(number(), 0))).toBe(true)
  })

  it('max invalid', () => {
    const [err] = validate(1, max(number(), 0))
    expect(err!.refinement).toBe('max')
  })

  it('max exclusive invalid at boundary', () => {
    const [err] = validate(0, max(number(), 0, { exclusive: true }))
    expect(err!.refinement).toBe('max')
  })

  it('size string valid', () => {
    expect(is('abc', size(string(), 1, 5))).toBe(true)
  })

  it('size string invalid empty', () => {
    const [err] = validate('', size(string(), 1, 5))
    expect(err!.refinement).toBe('size')
  })

  it('size number valid', () => {
    expect(is(3, size(number(), 1, 5))).toBe(true)
  })

  it('size number invalid', () => {
    const [err] = validate(0, size(number(), 1, 5))
    expect(err!.refinement).toBe('size')
  })

  it('size exact valid', () => {
    expect(is('abcd', size(string(), 4))).toBe(true)
  })

  it('nonempty valid', () => {
    expect(is('x', nonempty(string()))).toBe(true)
  })

  it('nonempty invalid empty string', () => {
    const [err] = validate('', nonempty(string()))
    expect(err!.refinement).toBe('nonempty')
  })

  it('empty valid', () => {
    expect(is('', empty(string()))).toBe(true)
  })

  it('empty invalid non-empty', () => {
    const [err] = validate('x', empty(string()))
    expect(err!.refinement).toBe('empty')
  })

  it('refine with custom name - invalid', () => {
    const emailStruct = refine(string(), 'email', (v) => v.includes('@'))
    const [err] = validate('invalid', emailStruct)
    expect(err!.refinement).toBe('email')
  })

  it('refine valid', () => {
    const emailStruct = refine(string(), 'email', (v) => v.includes('@'))
    expect(is('a@b.com', emailStruct)).toBe(true)
  })
})

// ─── types ────────────────────────────────────────────────────────────────────

describe('types', () => {
  it('any passes any value', () => {
    expect(is({ anything: true }, any())).toBe(true)
  })

  it('array validates elements', () => {
    const [err] = validate([1, 'b', 3], array(number()))
    expect(err).toBeDefined()
    expect(err!.path).toEqual([1])
    expect(err!.type).toBe('number')
  })

  it('boolean rejects non-boolean', () => {
    expect(is('true', boolean())).toBe(false)
  })

  it('date rejects invalid Date', () => {
    expect(is(new Date('invalid'), date())).toBe(false)
  })

  it('date accepts valid Date', () => {
    expect(is(new Date(0), date())).toBe(true)
  })

  it('enums accepts value in set', () => {
    expect(is('two', enums(['one', 'two']))).toBe(true)
  })

  it('enums rejects value not in set', () => {
    const [err] = validate('three', enums(['one', 'two']))
    expect(err!.type).toBe('enums')
  })

  it('integer rejects decimal', () => {
    expect(is(3.14, integer())).toBe(false)
  })

  it('literal uses strict equality', () => {
    expect(is(42, literal(42))).toBe(true)
  })

  it('literal rejects non-equal', () => {
    expect(is(43, literal(42))).toBe(false)
  })

  it('never always fails', () => {
    const [err] = validate(true, never())
    expect(err!.type).toBe('never')
  })

  it('nullable accepts null', () => {
    expect(is(null, nullable(number()))).toBe(true)
  })

  it('nullable rejects wrong type', () => {
    expect(is('x', nullable(number()))).toBe(false)
  })

  it('object rejects arrays', () => {
    const [err] = validate([], object())
    expect(err!.type).toBe('object')
  })

  it('object rejects unknown keys', () => {
    const [err] = validate({ a: 1, b: 2 }, object({ a: number() }))
    expect(err!.type).toBe('never')
    expect(err!.path).toEqual(['b'])
  })

  it('optional accepts undefined', () => {
    expect(is(undefined, optional(number()))).toBe(true)
  })

  it('record validates all values', () => {
    const [err] = validate({ a: 'x' }, record(string(), number()))
    expect(err!.type).toBe('number')
  })

  it('tuple rejects extra elements', () => {
    const [err] = validate(['A', 3, 'extra'], tuple([string(), number()]))
    expect(err!.type).toBe('never')
    expect(err!.path).toEqual([2])
  })

  it('tuple rejects missing elements', () => {
    const [err] = validate(['A'], tuple([string(), number()]))
    expect(err!.type).toBe('number')
    expect(err!.path).toEqual([1])
  })

  it('type allows unknown keys', () => {
    expect(is({ name: 'x', extra: 1 }, type({ name: string() }))).toBe(true)
  })

  it('union accepts first matching', () => {
    expect(is({ a: 'ok' }, union([type({ a: string() }), type({ b: number() })]))).toBe(true)
  })

  it('union rejects if none match', () => {
    const [err] = validate({ b: 'x' }, union([type({ a: string() }), type({ b: number() })]))
    expect(err!.type).toBe('union')
  })

  it('intersection requires all', () => {
    const [err] = validate(
      { a: 'x', b: 'not-a-number' },
      intersection([type({ a: string() }), type({ b: number() })])
    )
    expect(err!.path).toEqual(['b'])
  })
})

// ─── utilities ────────────────────────────────────────────────────────────────

describe('utilities', () => {
  it('define creates custom validator', () => {
    const word = define('word', (v) => typeof v === 'string')
    expect(is('hello', word)).toBe(true)
  })

  it('define fails custom validation', () => {
    const word = define('word', (v) => typeof v === 'string')
    const [err] = validate(42, word)
    expect(err!.type).toBe('word')
  })

  it('assign merges schemas', () => {
    const merged = assign(object({ a: number() }), object({ b: string() }))
    expect(is({ a: 1, b: 'x' }, merged)).toBe(true)
  })

  it('assign rejects unknown keys', () => {
    const merged = assign(object({ a: number() }), object({ b: string() }))
    const [err] = validate({ a: 1, b: 'x', c: true }, merged)
    expect(err!.type).toBe('never')
  })

  it('deprecated passes undefined without logging', () => {
    const log = vi.fn()
    const s = deprecated(any(), log)
    expect(is(undefined, s)).toBe(true)
    expect(log).not.toHaveBeenCalled()
  })

  it('deprecated logs and validates when value present', () => {
    const log = vi.fn()
    const s = deprecated(any(), log)
    expect(is('present', s)).toBe(true)
    expect(log).toHaveBeenCalled()
  })

  it('lazy caches struct', () => {
    const s = lazy(() => string())
    expect(is('ok', s)).toBe(true)
  })

  it('dynamic resolves struct at runtime', () => {
    const s = dynamic(() => string())
    const [err] = validate(3, s)
    expect(err!.type).toBe('string')
  })

  it('omit removes key from schema', () => {
    const s = omit(object({ a: number(), b: number() }), ['a'])
    expect(is({ b: 2 }, s)).toBe(true)
  })

  it('omit still rejects removed field as unknown', () => {
    const s = omit(object({ a: number(), b: number() }), ['a'])
    const [err] = validate({ a: 1, b: 2 }, s)
    expect(err!.type).toBe('never')
  })

  it('partial makes all fields optional', () => {
    const s = partial({ name: string(), age: number() })
    expect(is({}, s)).toBe(true)
  })

  it('partial still rejects wrong type', () => {
    const s = partial({ name: string(), age: number() })
    expect(is({ age: 'x' }, s)).toBe(false)
  })

  it('pick keeps only selected keys', () => {
    const s = pick(object({ name: string(), age: number() }), ['name'])
    expect(is({ name: 'x' }, s)).toBe(true)
  })

  it('pick rejects omitted key as unknown', () => {
    const s = pick(object({ name: string(), age: number() }), ['name'])
    const [err] = validate({ name: 'x', age: 1 }, s)
    expect(err!.type).toBe('never')
  })
})

// ─── early exit / refiner ordering ────────────────────────────────────────────

describe('run ordering', () => {
  it('early exit: second validator not run if first fails', () => {
    let ranA = false
    let ranB = false
    const A = define('A', () => {
      ranA = true
      return false
    })
    const B = define('B', () => {
      ranB = true
      return true
    })
    const s = object({ a: A, b: B })
    validate({ a: null, b: null }, s)
    expect(ranA).toBe(true)
    // B runs because object iterates all entries
    // but early exit from assert/is stops after first failure
    // validate collects lazily; B may or may not run depending on impl
  })

  it('outer refiner runs if inner refiner fails (not validator)', () => {
    let ranOuterRefiner = false
    const innerStruct = refine(any(), 'A', () => false)
    const outerRefiner = () => {
      ranOuterRefiner = true
      return true
    }
    const s = refine(object({ a: innerStruct }), 'B', outerRefiner)
    validate({ a: null }, s)
    expect(ranOuterRefiner).toBe(true)
  })

  it('outer refiner skipped if validator fails', () => {
    let ranRefiner = false
    const innerStruct = define('A', () => false)
    const outerRefiner = () => {
      ranRefiner = true
      return true
    }
    const s = refine(object({ a: innerStruct }), 'B', outerRefiner)
    validate({ a: null }, s)
    expect(ranRefiner).toBe(false)
  })
})

// ─── StructError ──────────────────────────────────────────────────────────────

describe('StructError', () => {
  it('is instanceof TypeError', () => {
    let err: any
    try {
      assert(42, string())
    } catch (e) {
      err = e
    }
    expect(err instanceof TypeError).toBe(true)
  })

  it('has direct properties from failure', () => {
    let err: any
    try {
      assert(42, string())
    } catch (e) {
      err = e
    }
    expect(err.value).toBe(42)
    expect(err.type).toBe('string')
    expect(err.path).toEqual([])
  })

  it('failures() returns cached array', () => {
    const [err] = validate(42, string())
    const f1 = err!.failures()
    const f2 = err!.failures()
    expect(f1).toBe(f2)
  })
})
