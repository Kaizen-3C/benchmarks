# Phase-1 result patches (agent-generated provenance)

Each `*.patch` here is the exact code one agent produced for one
`{lib}_{arch}_{provider}` cell during the 2026-06 Phase-1 re-validation — the
`git diff` of the agent's branch against the pinned `commit0` starter, with
non-code noise excluded (`.aider*`, `spec.md`, `__pycache__`).

## How these are used

The corresponding result JSON at `commit0/results/{lib}_{arch}_{provider}.json`
records, for each cell:

- `code_branch`  — the git branch the agent's code was committed to
- `patch_file`   — the relative path to the `.patch` here
- `patch_sha256` — the SHA-256 of the patch bytes

So a reviewer can verify provenance end-to-end: the JSON's `patch_sha256` must
match `sha256sum patches/<file>.patch`, and the patch is the literal code that was
scored full-suite via `commit0 test --branch` (see
[`../../../CORRECTIONS.md`](../../../CORRECTIONS.md) for why this matters — a prior
bug committed binary noise that made the container silently score the baseline).

```bash
# verify one cell's patch matches its recorded hash
python - <<'PY'
import json, hashlib, pathlib
j = json.load(open("commit0/results/cachetools_aider_openai.json"))
p = pathlib.Path("commit0/results") / j["patch_file"]
assert hashlib.sha256(p.read_bytes()).hexdigest() == j["patch_sha256"], "MISMATCH"
print("ok:", j["patch_file"])
PY
```

## Applying a patch (re-deriving a cell's score, $0, no API keys)

The patches are **byte-faithful** to what the agents produced — including agent source files
that lack a trailing newline — so `patch_sha256` matches the exact bytes that were scored.
Two consequences for applying them:

- They are stored **LF** and `.gitattributes` marks `commit0/results/patches/** -text` so a
  checkout never converts them to CRLF (which would break both `git apply` and the sha check).
- Because some preserve a no-trailing-newline final line, plain `git apply` can report
  "corrupt patch"; apply with the tolerant invocation the verifier uses:

```bash
# canonical, robust apply (handles the no-trailing-newline tail):
python commit0/baselines/verify_patches.py --results-dir commit0/results \
    --patches-dir commit0/results/patches --only <lib>_<arch>_<provider>
# or manually: printf '\n' >> p.patch ; git apply --recount --whitespace=nowarn p.patch
```

**Empty patches.** 9 cells have a 0-byte patch — the agent produced no applyable change
(collection-crash floor libs, e.g. `*_aider_openai` on babel/jinja/marshmallow/minitorch).
An empty patch means "no change → the cell scores the `commit0` baseline"; their recorded
counts are the baseline collection-error counts. `verify_patches` treats an empty patch as a
baseline score. (`cookiecutter_aider_openai` is the one empty patch whose recorded counts are
non-baseline — a known provenance gap to re-derive; see REPRODUCIBILITY.md.)

## Why this is a separate pull request

These 55 patches are ~135k lines of generated data. They are split into their own
data-only PR so the code/docs PR stays within automated-review size limits
(GitHub Copilot reviews up to 20,000 changed lines). This directory is **data, not
human-authored code** — no line-level review is expected. After both PRs merge to
`main`, the result JSONs and these patches sit together and the provenance check
above resolves.
