"""1-lib smoke test for the Phase-1 re-validation runners.

Runs ONE library through the patched Aider/smolagents runner and asserts the new
full-suite-scoring + code-persistence invariants BEFORE committing to the ~$65
full sweep (see ../RE-VALIDATION.md). The point is to catch a broken branch /
patch-export / `commit0 test` wiring for a few cents, not at full-sweep cost.

Run on the WSL host (needs Docker, the agent SDK, and the commit0 CLI):

    python commit0/baselines/smoke_revalidation.py --arch aider      --provider anthropic
    python commit0/baselines/smoke_revalidation.py --arch smolagents --provider openai --lib wcwidth

Validate an already-produced JSON without re-running (works anywhere, no spend):

    python commit0/baselines/smoke_revalidation.py --arch aider --provider anthropic \
        --check-only --results-dir commit0/results

Exit code: 0 = all invariants pass (warnings allowed), 1 = a hard invariant failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path.home() / "kaizen-commit0"
DEFAULT_RESULTS_DIR = WORKSPACE / "baselines" / "results"   # where run_lite_*.py writes

VALID_SCORING = {"commit0-test-full-suite", "full-suite-local-pytest"}

# Full-suite test counts observed on the full-suite architectures (RE-VALIDATION.md §1).
# Used only as a sanity signal that the FULL suite ran (vs an -x-truncated handful).
EXPECTED_SUITE = {
    "wcwidth": 38, "deprecated": 171, "cachetools": 215, "voluptuous": 149,
    "portalocker": 40, "pyjwt": 259, "chardet": 376, "tinydb": 201, "simpy": 140,
    "imapclient": 267, "parsel": 206, "cookiecutter": 367, "babel": 1281,
}


def _run_one(arch: str, provider: str, lib: str) -> int:
    runner = Path(__file__).resolve().parent / arch / f"run_lite_{arch}.py"
    if not runner.exists():
        print(f"FAIL: runner not found: {runner}")
        return 1
    cmd = [sys.executable, str(runner), "--provider", provider, "--only", lib]
    print(f"  $ {' '.join(cmd)}  (cwd={WORKSPACE})")
    return subprocess.run(cmd, cwd=WORKSPACE).returncode


def validate_cell(path: Path, arch: str, lib: str) -> tuple[int, int]:
    """Check the re-validation invariants on one result JSON. Returns (fails, warns)."""
    fails = warns = 0

    def ok(msg):   print(f"  PASS  {msg}")
    def bad(msg):
        nonlocal fails; fails += 1; print(f"  FAIL  {msg}")
    def warn(msg):
        nonlocal warns; warns += 1; print(f"  WARN  {msg}")

    if not path.exists():
        bad(f"result JSON not found: {path}")
        return fails, warns
    try:
        j = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        bad(f"result JSON unparseable: {e}")
        return fails, warns
    ok(f"result JSON present and parses: {path.name}")

    # 1. tests actually ran
    fc = j.get("final_counts") or {}
    collected = fc.get("passed", 0) + fc.get("failed", 0) + fc.get("errors", 0)
    if collected > 0:
        ok(f"tests ran: collected={collected} (passed={fc.get('passed', 0)})")
    else:
        bad("final_counts shows 0 collected tests")

    # 2. scoring provenance
    scoring = j.get("scoring")
    if scoring in VALID_SCORING:
        ok(f"scoring tag valid: {scoring}")
        if scoring != "commit0-test-full-suite":
            warn("scored via LOCAL pytest fallback — commit0 test emitted no summary; investigate")
    else:
        bad(f"scoring tag missing/invalid: {scoring!r} (expected one of {sorted(VALID_SCORING)})")

    # 3. code branch
    if j.get("code_branch") == arch:
        ok(f"code_branch == {arch}")
    else:
        bad(f"code_branch is {j.get('code_branch')!r}, expected {arch!r}")

    # 4 + 5. patch artifact present, non-empty, hash matches
    patch_file = j.get("patch_file")
    if not patch_file:
        bad("patch_file not recorded")
    else:
        patch_path = (path.parent / patch_file).resolve()
        if not patch_path.exists():
            bad(f"patch_file recorded but missing on disk: {patch_path}")
        else:
            data = patch_path.read_bytes()
            if not data.strip():
                warn(f"patch is empty — agent made no changes vs commit0? ({patch_path.name})")
            else:
                ok(f"patch present, {len(data)} bytes: {patch_file}")
            recorded = j.get("patch_sha256")
            actual = hashlib.sha256(data).hexdigest()
            if recorded == actual:
                ok("patch_sha256 matches patch file")
            else:
                bad(f"patch_sha256 mismatch (recorded {recorded}, actual {actual})")

    # 6. full-suite sanity (informational)
    exp = EXPECTED_SUITE.get(lib)
    if exp is not None and collected:
        if collected >= 0.9 * exp:
            ok(f"full suite ran: collected {collected} ~ expected {exp}")
        else:
            warn(f"collected {collected} << expected full suite {exp} — possible truncation/collection error")
    return fails, warns


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", choices=["aider", "smolagents"], required=True)
    ap.add_argument("--provider", choices=["anthropic", "openai"], required=True)
    ap.add_argument("--lib", default="wcwidth", help="smoke library (default: wcwidth — small/fast)")
    ap.add_argument("--check-only", action="store_true", help="validate an existing JSON; do not run")
    ap.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR),
                    help=f"where the result JSON lives (default: {DEFAULT_RESULTS_DIR})")
    args = ap.parse_args()

    print(f"== smoke re-validation: {args.arch} x {args.provider} x {args.lib} ==")
    if not args.check_only:
        rc = _run_one(args.arch, args.provider, args.lib)
        if rc != 0:
            print(f"WARN: runner exited {rc}; validating whatever JSON was produced anyway")

    results_dir = Path(args.results_dir)
    json_path = results_dir / f"{args.lib}_{args.arch}_{args.provider}.json"
    print(f"-- validating {json_path} --")
    fails, warns = validate_cell(json_path, args.arch, args.lib)

    print(f"\n== smoke result: {fails} fail, {warns} warn ==")
    if fails:
        print("NOT READY for the full sweep — fix the runner wiring first (see RE-VALIDATION.md §5).")
        return 1
    print("READY: persistence + full-suite scoring verified on 1 lib. Proceed to the full sweep.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
