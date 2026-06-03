# ⚠ Scoring notice — Aider & smolagents cells are pending re-validation

The **Aider** and **smolagents** result JSONs in this directory were scored with
`pytest -x` (stop at the first failure), which **truncates the denominator** to the
tests that ran before the first failure. Every other architecture here (single-shot,
reflexion, kaizen_delta) scores the **full suite** via `commit0 test`.

**Consequence:** the per-lib pass *rates* and `value_add_pp` for these cells are **not
comparable** to the full-suite cells and are **not reproducible** under
[`../PROTOCOL.md` §6](../PROTOCOL.md) (full-suite scoring). They are an upper-biased
artifact, not a measurement.

These files are retained as-is (not deleted) for provenance. Do not cite their rates
until the re-run lands.

**Affected files**
- `*_aider_anthropic.json`, `*_aider_openai.json` (per-lib + `aggregate_lite_aider_*`)
- `*_smolagents_anthropic.json`, `*_smolagents_openai.json` (per-lib + `aggregate_lite_smolagents_*`)

**What to do:** see [`../RE-VALIDATION.md`](../RE-VALIDATION.md) for the full-suite re-run plan
(≈$65) and the list of what is vs is not validated.

**Not affected:** single-shot (B2), reflexion (B3), kaizen_delta (KD), and OpenHands (OH)
cells — those are full-suite scored and remain valid.
