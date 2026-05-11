# ADR-0013: URL and Email Validation via Regex

## Status
Accepted

## Context
Simple URL and email validation is needed without heavy dependencies.

## Decision
Two compiled regex patterns in `validators.py`:

- `USER_REGEX` — validates the local part of an email address (before `@`). Accepts dot-atom and quoted-string forms, case-insensitive.
- `DOMAIN_REGEX` — validates a domain name (after `@` for email, `netloc` for FQDN URL). Accepts standard dot-separated labels or IPv4 bracket notation, case-insensitive.

`Email(v)`: splits on last `@`, validates user part with `USER_REGEX`, domain part with `DOMAIN_REGEX`.

`Url(v)`: uses `urllib.parse.urlparse`; requires non-empty `scheme` and `netloc`.

`FqdnUrl(v)`: like `Url` but additionally validates `netloc` (minus port) with `DOMAIN_REGEX`.

All three are decorated with `@message(...)` so they raise typed `Invalid` subclasses.

## Consequences
No external dependencies for URL/email validation. Complex edge cases (IDN, IPv6) may not be handled.
