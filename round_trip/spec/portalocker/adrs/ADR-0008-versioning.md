# ADR-0008: Versioning via __about__

## Status
Accepted

## Context
Version needs to be accessible as `portalocker.__version__` and from `pyproject.toml` dynamic version discovery.

## Decision
- `portalocker/__about__.py` is the single source of truth for version (`"2.10.1"`), package name, author, email, description, and URL.
- `pyproject.toml` reads version via `attr = 'portalocker.__about__.__version__'`.
- `portalocker/__init__.py` copies all `__about__` attributes to module-level names.

## Consequences
- `portalocker.__version__ == "2.10.1"`.
- `portalocker.__package_name__ == "portalocker"`.
