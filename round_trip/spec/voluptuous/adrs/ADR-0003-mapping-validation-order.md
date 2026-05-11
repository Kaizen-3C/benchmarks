# ADR-0003: Mapping Key Candidate Ordering

## Status
Accepted

## Context
When validating dict keys, schema keys of different kinds (literals, types, callables, markers, Remove, Extra) must be tried in a deterministic order to ensure predictable matching.

## Decision
Schema items are sorted by `_compile_itemsort` before validation. The sort produces a 3-tuple key `(priority, 0, str(k))`:

| Priority | Condition |
|---|---|
| 0 | `Remove` marker |
| 1 | Literal marker or bare literal value |
| 2 | Type or marker wrapping a type |
| 3 | Callable or marker wrapping a callable |
| 4 | `Extra` sentinel |

Within the mapping validator, keys are further split into:
- `required_specific` / `optional_specific` — literal (non-type, non-callable) schema keys tried first.
- `required_generic` / `optional_generic` — type/callable schema keys tried as fallback.
- `remove_keys` — tried after specific, before generic.

Extra keys not matched by any schema key are handled according to `Schema.extra`: `PREVENT_EXTRA` (0) raises `Invalid`, `ALLOW_EXTRA` (1) passes through, `REMOVE_EXTRA` (2) silently drops.

## Consequences
Literal keys always take precedence over type/callable keys. `Remove` keys always take precedence over all others. `Extra` is a last resort.
