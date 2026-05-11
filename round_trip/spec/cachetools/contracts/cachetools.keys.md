# Contract: `cachetools.keys`

Importable as `from cachetools import keys` or
`from cachetools.keys import hashkey, ...`.
See ADR-0008.

---

## `hashkey(*args, **kwargs) -> _HashedTuple`
Returns a `_HashedTuple` of `args` extended with sorted `kwargs` items
(separated by the `_kwmark` singleton).  Keyword-free calls return
`_HashedTuple(args)`.

## `methodkey(self, *args, **kwargs) -> _HashedTuple`
Equivalent to `hashkey(*args, **kwargs)`; `self` is discarded.

## `typedkey(*args, **kwargs) -> _HashedTuple`
`hashkey` result concatenated with `tuple(type(v) for v in args)` and,
if kwargs present, `tuple(type(v) for _, v in sorted(kwargs.items()))`.

## `typedmethodkey(self, *args, **kwargs) -> _HashedTuple`
Equivalent to `typedkey(*args, **kwargs)`; `self` is discarded.

---

## `_HashedTuple`
Internal `tuple` subclass.  Hash is computed once and cached in
`self.__dict__["hashvalue"]`.  Supports `+` / `+=` returning
`_HashedTuple`.  `__getnewargs__` returns `(tuple(self),)`.
`__getstate__` returns `{}`; `__setstate__` is a no-op.
