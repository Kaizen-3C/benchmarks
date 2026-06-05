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

## Why this is a separate pull request

These 55 patches are ~135k lines of generated data. They are split into their own
data-only PR so the code/docs PR stays within automated-review size limits
(GitHub Copilot reviews up to 20,000 changed lines). This directory is **data, not
human-authored code** — no line-level review is expected. After both PRs merge to
`main`, the result JSONs and these patches sit together and the provenance check
above resolves.
