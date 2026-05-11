# ADR-0007: Sphinx Role Markup Stripped from Runtime Warning Messages

## Status
Accepted

## Context
Reason strings passed to `sphinx.deprecated` may contain Sphinx cross-reference markup such as `:func:`statistics.mean``. This markup is meaningful in HTML docs but looks noisy in runtime warning messages.

## Decision
Before passing `reason` to `classic.deprecated` (for runtime warnings), `sphinx.deprecated` applies `_clean_reason(reason)`, which uses the regular expression `:(?:[A-Za-z0-9_]+:)?(?:[A-Za-z0-9_]+):`([^`]*)`` to replace each Sphinx role with just its content in backticks (e.g., `:func:`statistics.mean`` → `` `statistics.mean` ``).

The raw (unstripped) reason is still used for docstring injection via `SphinxAdapter`.

## Consequences
- Runtime warnings are human-readable without Sphinx role syntax.
- Docstrings retain full Sphinx markup for documentation generation.
