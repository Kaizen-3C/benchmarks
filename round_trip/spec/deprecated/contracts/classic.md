# Contract: deprecated.classic

## Public API

### `deprecated(reason=None, version=None, category=DeprecationWarning, action=None, extra_stacklevel=0)`

**Type**: Callable — either a decorator factory or a bare decorator (see ADR-0001).

**Parameters**:
- `reason` (`str | None | callable`): Human-readable deprecation reason, or the decorated object when used bare. Must be `str` or `None` when not the decorated object; raises `TypeError` otherwise.
- `version` (`str | None`): Version string when the item was deprecated.
- `category` (`type`): Warning category class; must be a subclass of `Warning`. Default: `DeprecationWarning`.
- `action` (`str | None`): One of `"error"`, `"ignore"`, `"always"`, `"default"`, `"once"`, `"module"`, `"all"`, or `None`. See ADR-0002.
- `extra_stacklevel` (`int`): Additional frames to skip in stack attribution. Default `0`. See ADR-0003.

**Returns**: The decorated object (class or callable) with warning behaviour injected, or a decorator when given parameters.

**Behaviour**:
- Decorating a class patches `cls.__new__` (ADR-0004).
- Decorating a callable wraps it with `functools.wraps` preserving `__name__`, `__doc__`, etc.
- Every call/instantiation emits one `warnings.warn` with the message from `_build_message` (ADR-0008).

---

### `_build_message(kind, name, reason=None, version=None) -> str`

Internal helper. Returns the formatted warning message string per ADR-0008. Not part of public API but behaviour is specified for oracle purposes.

---

### `_validate_reason(reason)`

Raises `TypeError` if `reason` is not `str` and not `None`.

---

### `_warn(msg, category, action, stacklevel)`

Internal. Emits `warnings.warn`. Wraps in `catch_warnings` + `simplefilter` when `action` is not `None` (ADR-0002).
