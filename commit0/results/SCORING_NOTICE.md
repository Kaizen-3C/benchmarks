# Scoring notice — mostly RESOLVED (re-validated 2026-06-04)

The Aider & smolagents cells were originally scored with `pytest -x` (truncated denominators) plus
a patch-noise scoring bug. **Re-validated full-suite (`commit0 test --branch`) on 2026-06-04** —
see [`../AAR_2026-06-04_REVALIDATION.md`](../AAR_2026-06-04_REVALIDATION.md). Valid now:
all OpenAI cells, all smolagents×Sonnet cells, and 7/16 aider×Sonnet cells (carry a `scoring` tag).

**Still pending (do NOT cite):** the **9 aider×Sonnet** cells without a `scoring` tag (voluptuous,
chardet, simpy = provider-limited; jinja, marshmallow, cookiecutter, imapclient, babel, minitorch =
genuine fails). They retain old `-x` values. Old data archived under `_pre_revalidation/`.

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
