# Contract: `StructError` (src/error.ts)

## Type `Failure`
```ts
type Failure = {
  value: any; key: any; type: string;
  refinement: string | undefined; message: string;
  explanation?: string; branch: any[]; path: any[]
}
```

## Class `StructError extends TypeError`

### Constructor
```ts
new StructError(failure: Failure, failures: () => Generator<Failure>)
```
- Sets `message` to `explanation ?? (path.length === 0 ? message : "At path: <path> -- <message>")`
- Sets `this.cause = msg` when `explanation` is provided
- Spreads all `Failure` fields (except `message` and `explanation`) onto `this`
- Sets `this.name = this.constructor.name`

### Properties (copied from first Failure)
`value`, `key`, `type`, `refinement`, `path`, `branch` — all direct properties.
Additional index-signature `[x: string]: any` allows arbitrary custom properties.

### Method
- `failures(): Array<Failure>` — returns cached array: `[firstFailure, ...remainingFailures]`
