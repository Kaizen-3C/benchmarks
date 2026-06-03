"""Scoring-provenance guard for the commit0 result matrix.

Prevents a denominator-truncated (`pytest -x`) cell from silently re-entering the
matrix — the defect documented in ../RE-VALIDATION.md.

Rule: every *competitor* result JSON (Aider / smolagents) must carry a recognised
`"scoring"` tag written by the patched runners. Full-suite architectures
(single_shot / reflexion / kaizen_delta / kaizen_stage2 / OpenHands) score through
`commit0 test` by construction and are trusted whether or not they carry the tag.

The 68 Aider/smolagents JSONs committed *before* the scoring fix predate the tag and
are the `-x`-truncated data awaiting re-run; they are tolerated as a known-pending
baseline (EXPECTED_PENDING). The guard FAILS only when:
  * a NEW untagged competitor cell appears (pending count rises above the baseline), or
  * any result JSON fails to parse.
It WARNS (exit 0) when the pending count drops — i.e. the re-run is landing and
EXPECTED_PENDING should be lowered (set to 0 once re-validation completes).

Usage:
    python commit0/baselines/check_scoring_provenance.py          # CI-friendly
    python commit0/baselines/check_scoring_provenance.py --strict # any pending = failure
    python commit0/baselines/check_scoring_provenance.py --list   # list pending files

Wire into CI, e.g. a GitHub Actions step:
    - run: python commit0/baselines/check_scoring_provenance.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"

VALID_SCORING = {"commit0-test-full-suite", "full-suite-local-pytest"}
COMPETITOR_ARCHS = {"aider", "smolagents"}

# Known `-x`-truncated cells committed before the scoring fix (see RE-VALIDATION.md).
# Lower this to 0 once the Phase-1 re-run replaces them with tagged, full-suite JSONs.
EXPECTED_PENDING = 68


def classify(path: Path) -> tuple[str, bool]:
    """Return (arch, has_valid_scoring) for a result JSON.

    `arch` is "" for files that are not architecture result cells.
    Aggregates count as valid only if EVERY per_library entry is tagged.
    """
    j = json.loads(path.read_text(encoding="utf-8"))  # may raise -> caller handles
    arch = j.get("branch") or j.get("architecture") or ""
    if "per_library" in j:  # aggregate
        entries = (j.get("per_library") or {}).values()
        valid = bool(entries) and all(e.get("scoring") in VALID_SCORING for e in entries)
        return arch, valid
    return arch, j.get("scoring") in VALID_SCORING


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="treat any pending cell as a failure")
    ap.add_argument("--list", action="store_true", help="print each pending file")
    args = ap.parse_args()

    pending: list[str] = []
    parse_errors: list[str] = []

    for path in sorted(RESULTS.glob("*.json")):
        try:
            arch, valid = classify(path)
        except Exception as e:  # malformed JSON is always a hard failure
            parse_errors.append(f"{path.name}: {type(e).__name__}: {e}")
            continue
        if arch in COMPETITOR_ARCHS and not valid:
            pending.append(path.name)

    print(f"scoring-provenance guard — results/ scanned: {len(list(RESULTS.glob('*.json')))} JSONs")
    print(f"  competitor cells pending re-validation: {len(pending)} (baseline {EXPECTED_PENDING})")
    if args.list:
        for name in pending:
            print(f"    pending: {name}")
    if parse_errors:
        print(f"  PARSE ERRORS: {len(parse_errors)}")
        for e in parse_errors:
            print(f"    {e}")

    # --- exit policy ---
    if parse_errors:
        print("FAIL: unparseable result JSON(s).")
        return 1
    if args.strict and pending:
        print("FAIL (--strict): untagged competitor cells present; re-run + re-score them.")
        return 1
    if len(pending) > EXPECTED_PENDING:
        print(f"FAIL: {len(pending) - EXPECTED_PENDING} NEW untagged competitor cell(s) — a "
              f"`pytest -x` cell may have re-entered the matrix. See RE-VALIDATION.md.")
        return 1
    if len(pending) < EXPECTED_PENDING:
        print(f"WARN: pending dropped below baseline — re-validation is landing. "
              f"Lower EXPECTED_PENDING to {len(pending)} (0 when complete).")
        return 0
    print("OK: no new truncated cells (known legacy baseline unchanged).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
