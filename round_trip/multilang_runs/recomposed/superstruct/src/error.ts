export type Failure = {
  value: any
  key: any
  type: string
  refinement: string | undefined
  message: string
  explanation?: string
  branch: any[]
  path: any[]
}

export class StructError extends TypeError {
  value!: any
  key!: any
  type!: string
  refinement!: string | undefined
  path!: any[]
  branch!: any[]
  [x: string]: any

  private _failures: Array<Failure> | undefined
  private _remainingFailures: (() => Generator<Failure>) | undefined
  private _firstFailure: Failure

  constructor(failure: Failure, failures: () => Generator<Failure>) {
    const { explanation, message, path } = failure
    const msg =
      path.length === 0 ? message : `At path: ${path.join('.')} -- ${message}`
    const displayMessage = explanation ?? msg

    super(displayMessage)

    this.name = this.constructor.name

    if (explanation != null) {
      this.cause = msg
    }

    const { message: _msg, explanation: _exp, ...rest } = failure
    Object.assign(this, rest)

    this._firstFailure = failure
    this._remainingFailures = failures
  }

  failures(): Array<Failure> {
    if (this._failures == null) {
      const remaining: Failure[] = []
      const gen = this._remainingFailures!()
      let result = gen.next()
      while (!result.done) {
        remaining.push(result.value)
        result = gen.next()
      }
      this._failures = [this._firstFailure, ...remaining]
    }
    return this._failures
  }
}
