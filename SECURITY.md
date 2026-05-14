# Security Policy

## Reporting a vulnerability

**Please do not open public GitHub issues for security vulnerabilities.**

Instead, report security issues via email to:

> **security@kaizen-3c.dev**

Include, where possible:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, or a proof-of-concept.
- The affected file(s), commit SHA, or release version.
- Any suggested fix or mitigation.

PGP-encrypted reports welcome (key published at https://kaizen-3c.dev when available; until then, plain email is fine — please don't include sensitive credentials in plaintext, redact them).

## Response timeline

| Stage | Target |
|---|---|
| Acknowledgement of receipt | Within 72 hours |
| Initial triage + severity assessment | Within 7 days |
| Status update (fix / mitigation / dispute) | Within 30 days |
| Public disclosure window | 90 days from initial report (coordinated) |

We follow a **90-day coordinated-disclosure** model. If you have a stricter or looser disclosure preference, mention it in your initial report and we will work with you.

## Scope

This policy covers all repositories under the [Kaizen-3C](https://github.com/Kaizen-3C) GitHub organization, including (but not limited to):

- `Kaizen-3C/benchmarks` — this repository
- Future Kaizen-3C public repositories as they are launched

## What is NOT a security vulnerability

To save everyone time, the following are **not** security issues for this repository:

- **Benchmark results showing a particular architecture performs poorly.** That's the methodology working as intended — please open a regular issue or PR if you'd like to discuss methodology.
- **LLM outputs containing problematic content.** Model behavior is the upstream provider's concern; please report directly to the model vendor.
- **Test failures in commit0 libraries themselves.** Those are upstream commit0 issues, not benchmark-suite issues.
- **High API costs from running the sweep.** The expected aggregate numbers are documented in [`commit0/CAMPAIGN_README.md`](commit0/CAMPAIGN_README.md). If your spend exceeds the documented numbers significantly, that's a reproducibility issue (open a regular issue), not a security one.

## What IS in scope

- Code-execution vulnerabilities in the benchmark runners or analysis scripts. Sandbox / host-execution policy is governed by [ADR-0042: Sandbox Bypass Policy](https://github.com/Kaizen-3C/kaizen-staging/blob/main/.architecture/decisions/ADR-0042-sandbox-bypass-policy.md) in the staging repository — cite ADR-0042 in any disclosure that touches host-execution semantics.
- Credential or API-key leakage in scripts, CI configs, or committed artifacts.
- Supply-chain risks (e.g., dependency confusion, typosquatted packages we depend on).
- Vulnerabilities in any future hosted infrastructure (dashboards, leaderboards) that ship from this org.

## Recognition

We are grateful to security researchers who report responsibly. With your permission, we will acknowledge your contribution in the release notes for the fix and (if you wish) in a future SECURITY-HALL-OF-FAME.md as the contributor base grows.

---

Thank you for helping keep Kaizen-3C secure.
