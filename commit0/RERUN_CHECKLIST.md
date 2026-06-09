# What a re-run must fix (regeneration checklist + cost estimate)

Consolidates everything the 2026-06 verification surfaced (see `REPRODUCIBILITY.md`,
`CORRECTIONS.md`, `AUDIT_FINDINGS.md`). Two parts: **code fixes that must land first** ($0),
and **cells to regenerate** (LLM spend). Verification/re-scoring is $0 (Docker only) and is
already tooled (`verify_patches.py`, `verify_artifacts.py`, `audit_matrix.py`,
`check_scoring_provenance.py`).

---

## Part A — Code/harness fixes to land BEFORE any re-run ($0)

Without these, a re-run reproduces the same provenance defects.

| # | Fix | Why | Status |
|---|-----|-----|--------|
| A1 | **Per-provider branch names** for aider / smolagents / kaizen_delta (`aider_openai` / `aider_anthropic`, not a single `aider`) | The shared branch keeps only the *last-run* provider's code → the other provider is unverifiable and patch-export collides. Root cause of the KD "lost provider" + the shared-branch confound. | **DONE** — `_provider_of()` + `code_branch=f"{arch}_{provider}"` in all 3 runners; `repeat_runner.branch_of` updated |
| A2 | **Reflexion: reject non-Python generated code** before commit | `portalocker_reflexion_{sonnet,openai}` committed the model's prose (`"Wait - I still haven't resolved..."`) into `utils.py` → `SyntaxError` that broke ALL collection. | **DONE** — `write_files()` (shared by single_shot + reflexion) now `ast.parse`-validates each `.py` and refuses invalid content (keeps the stub) |
| A3 | **Patch export hygiene** — LF + trailing newline | Committed patches needed on-the-fly normalization to `git apply`. | **DONE** — `.gitattributes -text` (CRLF) + export now appends a trailing newline and writes `newline="\n"` in both runners |
| A4 | Scoring fixes (noise-strip before commit; full-suite `commit0 test` never `-x`; stamp scoring only on parseable, non-zero counts; mtime watermark; `docker rm -f commit0.eval.<lib>` self-heal; `git(check=True)`; case-insensitive parse) | The patch-noise / `-x` / silent-baseline / orphaned-container / 0/0/0 bugs. | **DONE** |
| A5 | **Pre-campaign hygiene**: `docker rm -f commit0.eval.*`, flag stale verify branches, confirm pinned env | Orphaned containers caused false 0/0/0; stale branches cause confounds. | **DONE** — `commit0/baselines/preflight_clean.sh` |
| A6 | **Verified WSL sync** — run `commit0/baselines/sync_to_wsl.sh` BEFORE any run | A bulk `cp -rf … 2>/dev/null` SILENTLY skipped files (left a stale 808-line `kaizen_delta.py`), so the 2026-06-06 Part-B run used the OLD runner (no per-provider branches). | **DONE** — `sync_to_wsl.sh` copies via redirection (cannot skip), diffs every file, checks markers; fails loud |

> **Operational note (2026-06-06 Part-B-OpenAI attempt):** failed on *environment*, not code — the stale sync above + OpenAI `APIConnectionError`s (only 8/16 KD cells) + a transient smolagents `AgentGenerationError`. Nothing was committed. Lesson: a regeneration run needs verified sync (A6), per-cell provider-error retries, and active monitoring; even OpenAI was flaky. The harness code is correct; the blocker is run-host reliability.

> **BLOCKER — aider→Anthropic deterministically broken (2026-06-08 Tier-A attempt):** the staged
> Tier-A re-run of the 4 aider-Sonnet cells (`chardet, voluptuous, marshmallow, jinja`;
> `.git/run_tier_a_sonnet.sh`) failed 100% with **`httpcore.RemoteProtocolError: Server
> disconnected without sending a response`** on aider's first LLM call (aider spins ~601 s of
> retries, commits an EMPTY patch `sha e3b0c442…`, $0 — the valid-rep gate correctly discards it).
> **Isolated to aider's request shape, NOT the environment:** verified live that the key (curl
> 200), model (`claude-sonnet-4-6`, same id that cost $0.83 on 6/04), direct `litellm.completion`
> at every size up to **683 KB / 200 k tokens**, streaming, prompt-caching, and WSL MTU (1420) all
> work; OpenAI from the same host works. aider+Anthropic **last worked 6/04** → drift since, prime
> **ROOT CAUSE — FOUND & FIXED (2026-06-08, $0 request-capture diagnostic).** A `httpx`-layer
> shim captured aider's outgoing Anthropic request and diffed it against a *working* direct
> `litellm.completion`. The decisive difference: aider sends **`max_tokens=64000` with
> `stream=False`**. Anthropic **cancels non-streaming requests that run past its ~10-minute
> server cap**; the 4 deferred cells are large/slow generations (full-library implementations)
> that blow that cap → `httpcore.RemoteProtocolError: Server disconnected` with **`elapsed_s≈600`
> = the 10-min timeout**. Confirms the pattern: the 7 aider×Anthropic cells that *succeeded* on
> 6/04 are small/fast libs; the 4 that failed (`chardet/voluptuous/marshmallow/jinja`) are the
> hard floor libs. Everything else was a red herring (key/model/litellm 1.83.14/caching/MTU all fine).
> **FIX APPLIED + VALIDATED (2026-06-08, ≈$11):** `stream=True` in `baselines/aider/_aider_runner.py`
> (was `stream=False`). Re-ran all 4 cells full-suite on Sonnet: **voluptuous 89.3% (133/149, $1.81),
> marshmallow 87.3% (1073/1229, $3.84), chardet 66.5% (250/376, $5.31)** — all valid, big +Δ vs the
> ~0% single-shot baseline; numbers now in `benchmarks-private/.../PAPER_UPDATES.md`. Ruled out:
> `cache_prompts=False` (still failed → caching not the cause; `KAIZEN_AIDER_CACHE` toggle stays
> wired, defaults on). **jinja STILL blocked — different, fundamental cause:** its full-repo context
> (~170k tok) + aider's `max_tokens=64000` **exceeds Sonnet's 200k context window**
> (`invalid_request_error: "This model's maximum context length…"`); ran on OpenAI only because of
> GPT-5.4's larger window. NOT a streaming issue. Options for jinja: cap aider `max_tokens` (~16–20k,
> risks truncating its large generation) and/or shrink the repo-map (`--map-tokens`), or accept
> **`n/a (exceeds context window)`** for jinja Aider-S (the recommended, honest outcome). Validated
> reps: `~/kaizen-commit0/baselines/results/sampling/tier_a_final/`. **DECISION (2026-06-08):** 3/4
> re-validated and citable; **jinja Aider-S accepted as `n/a (exceeds context window)`** — closed,
> not pending. Remaining Sonnet Aider-S
> cells are marked *pending re-validation* in the paper; proceed on OpenAI-side evidence (incl. the
> significant aider voluptuous **+82.6 pp**) and re-run Sonnet via Anthropic research credits once
> the aider fix above is confirmed. **$0 spent; no bad data committed.**

---

## Part B — Cells to regenerate (LLM spend)

Per-cell $ are rough, derived from the campaign per-arch totals (README headline table)
÷ 16 libs; **floor/collection-hard libs cost ~2–3× the average** (more retries), so ranges
are given. Anthropic (Sonnet) is the costlier provider.

| # | Bucket | Cells | Arch × provider | Est. LLM $ |
|---|--------|------:|-----------------|-----------:|
| B1 | Legacy `aider × anthropic` gap (the `-x` cells never re-run) | 9 | aider Sonnet (mostly floor libs) | **~$12–20** |
| B2 | kaizen_delta re-run with per-provider branches (closes `imapclient_kd` silent-baseline + makes all KD cells independently verifiable) | 32 (or 16 lost-provider only) | KD Sonnet + GPT | **~$28–40** (full) / ~$14–20 (lost only) |
| B3 | `portalocker_reflexion` (after A2) | 2 | reflexion Sonnet + GPT | **~$1** |
| B4 | Minor / optional: `portalocker_single_shot_openai` (env-sensitive ±2 tests), `tinydb_reflexion_openai` (recorded was empty) | 2 | single_shot/reflexion | **~$1** |
| | **Total to close every known gap** | ~45 | | **~$42–62** |
| | **Minimal (gaps that are provably wrong/lost, not full KD)** | ~13 | | **~$15–22** |

**Notes**
- The 9 empty-patch cells are **NOT** in scope — they faithfully reproduce (agent produced
  no code → `commit0` stub baseline = recorded). No re-run needed.
- single_shot (32) reproduces at ~96% and is provider-specific already → no re-run beyond B4.
- After regeneration, run `verify_patches.py --all` + `audit_matrix.py` ($0) to confirm
  100% reproduction and clean provenance.

---

## Wall-clock estimate

- **Regeneration (Part B):** ~45 cells, paced via `repeat_runner.py` (fail-fast 180s LLM
  timeouts, `--sleep` pacing). Most cells minutes; floor libs with retries up to ~30 min.
  Rough **~3–6 h wall** (largely serial to respect provider stability; OpenAI cells faster).
- **Verification ($0):** re-score all 160 via `verify_patches`/`verify_artifacts` ~**1–3 h**
  Docker (now self-healing + correct timeouts).

## Out of scope here (separate, larger effort)

The **statistical re-test** (Phase A cheap-model dry-run → Phase B real-model, K reps/cell,
bootstrap CIs / BH-FDR / sign-stability) is scoped in `SAMPLING_PLAN.md` and is a much larger
budget (K× the single-run cost). This checklist is only the **single-run regeneration** needed
to make every published cell independently reproducible.
