# Contract: deprecated.sphinx

## Public API

### `deprecated(reason=None, version=None, category=DeprecationWarning, action=None, line_length=70, extra_stacklevel=0)`

Dual-mode decorator (see ADR-0001 for bare vs parameterised).

- Injects Sphinx `.. deprecated::` directive into `__doc__` (ADR-0006).
- Strips Sphinx role markup from `reason` before passing to runtime warning (ADR-0007).
- Delegates runtime warning to `classic.deprecated`.

---

### `versionadded(reason=None, version=None, line_length=70)`

Returns a `SphinxAdapter` for the `versionadded` directive. Does **not** emit runtime warnings. Only modifies `__doc__`.

---

### `versionchanged(reason=None, version=None, line_length=70)`

Returns a `SphinxAdapter` for the `versionchanged` directive. Does **not** emit runtime warnings. Only modifies `__doc__`.

---

### `class SphinxAdapter`

**Constructor**: `SphinxAdapter(directive, reason=None, version=None, line_length=70)`
- `directive`: one of `"deprecated"`, `"versionadded"`, `"versionchanged"`.
- Raises `TypeError` if `reason` is not `str` or `None`.

**`__call__(wrapped)`**: Appends directive block to `wrapped.__doc__`. Returns `wrapped`.

**`get_deprecated_msg(wrapped, kind)`**: Returns the runtime warning message string (via `classic._build_message`) using `_clean_reason(self.reason)`. `kind` defaults to `"class"` for types and `"function (or staticmethod)"` otherwise.
