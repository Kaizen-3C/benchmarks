# ADR-0006: Sphinx Directive Injection into Docstrings

## Status
Accepted

## Context
The `sphinx` sub-module provides decorators that, in addition to emitting runtime warnings, also augment the decorated callable's `__doc__` with reStructuredText Sphinx directives (`.. deprecated::`, `.. versionadded::`, `.. versionchanged::`).

## Decision
`SphinxAdapter.__call__(wrapped)` appends a formatted Sphinx directive block to `wrapped.__doc__`. The block format is:

```
.. <directive>:: <version>
   <reason line 1>
   <reason line 2>
```

Reason text is dedented via `textwrap.dedent`, stripped of leading/trailing newlines, then each line is individually wrapped to `line_length` characters (default 70) with 3-space indentation. Lines that are empty after stripping are emitted as empty strings (blank lines preserved). If `line_length` is 0 or negative, wrapping is skipped and each line receives only the 3-space indent.

If `wrapped.__doc__` already exists, the block is appended after a `\n\n` separator following `rstrip()` of the existing doc. If no docstring exists, the new `__doc__` is `"\n" + block`.

## Consequences
- The directive block is appended unconditionally on each decoration; stacking multiple sphinx decorators on one function appends multiple blocks.
- `sphinx.deprecated` both injects the docstring directive AND applies `classic.deprecated` for runtime warning behaviour.
