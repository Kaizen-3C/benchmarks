# ADR-0009: Sequence Validation Strategy

## Status
Accepted

## Context
Lists, tuples, sets and frozensets each have different semantics and must be validated accordingly.

## Decision
- **List schema** (`[v1, v2, ...]`): each data element is tested against each schema element in order; first match wins. `Remove` elements are checked first; if the value validates against a `Remove` schema it is omitted from output. Type of output matches type of input (list or tuple coerced to list).
- **Tuple schema** (`(v1, v2, ...)`): same algorithm as list but enforces `isinstance(data, (list, tuple))` and returns a tuple. If the schema has `_fields` (namedtuple), reconstructs as `type(schema)(*result)`.
- **Set/frozenset schema**: each data item must pass at least one compiled schema element; output is a `set` or `frozenset` matching the schema type.
- **ExactSequence**: requires data length == number of validators; validates element i against validator i exactly.
- **Unordered**: each data element must match at least one validator (greedy assignment); each validator is consumed at most once.

`_compile_sequence(schema, seq_type)` is the shared implementation for list and tuple.

## Consequences
List schemas act as "any of these element validators" per element. This is distinct from `ExactSequence` which is positional.
