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
