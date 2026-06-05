"""Matrix-wide integrity audit for the commit0 result data ($0, no LLM, no Docker).

The provenance guard (check_scoring_provenance.py) checks KNOWN defect classes by
enumeration. This audit attacks UNKNOWNS by a different mechanism - it checks that
independent derivations agree and that invariants hold - so it can surface defects we
never named:

  TRIANGULATION   aggregate per_library entries must equal the standalone per-cell JSON
                  (counts + scoring). Two stored views of one fact; disagreement = bug.
  DENOMINATOR     for a given lib the collected count is a property of the fixed test
   INVARIANCE     suite, so it should be ~constant across architectures - EXCEPT floor
                  libs where the agent's code unlocks collection. Variance on a non-floor
                  lib is the generalized signature of the patch-noise / silent-baseline
                  family (the exact tell that exposed the original bug).
  SILENT-BASELINE a competitor cell whose counts EXACTLY equal the single-shot baseline
   TELL           for the same lib+provider may be a patch that never applied (scored the
                  baseline). Flagged for review.
  MIS-STAMP       a full-suite scoring tag with 0 collected is never a real score.
  PROVENANCE      competitor cells must carry scoring/code_branch/patch_file/patch_sha256.
  COST ANOMALY    passed tests but $0 spend (didn't really run) etc.
  PATCH SHA       patch_sha256 must equal sha256(patch file) - skipped when patches are
                  not in this checkout (they live in the data PR); run in WSL to verify.

Exit: non-zero if any HARD inconsistency is found (mis-stamp, aggregate/per-cell mismatch,
sha mismatch, missing provenance on a tagged cell). WARN/INFO findings (denominator
variance, baseline tells, cost anomalies) are surfaced for human review but do not fail.

Usage:
    python commit0/baselines/audit_matrix.py            # report + exit code
    python commit0/baselines/audit_matrix.py --strict   # WARNs also fail
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"

LIBS = [
    "wcwidth", "deprecated", "cachetools", "voluptuous", "portalocker",
    "pyjwt", "chardet", "tinydb", "simpy", "imapclient", "parsel",
    "marshmallow", "cookiecutter", "babel", "jinja", "minitorch",
]
# Libs whose *test collection* depends on the agent implementing importable code, so a
# varying denominator across architectures is EXPECTED (collection unlock), not a defect.
FLOOR = {"chardet", "marshmallow", "babel", "jinja", "minitorch", "voluptuous"}

VALID_SCORING = {"commit0-test-full-suite", "full-suite-local-pytest"}
COMPETITOR_ARCHS = {"aider", "smolagents"}
# competitor provider -> single-shot baseline provider suffix
BASE_PROVIDER = {"anthropic": "sonnet", "openai": "openai"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def counts_of(d: dict) -> dict | None:
    """Normalised {passed,failed,skipped,errors} from a cell or per_library entry."""
    c = d.get("final_counts") or d.get("counts")
    if c is None:
        if any(k in d for k in ("passed", "failed", "errors")):
            c = d
        else:
            return None
    return {k: int(c.get(k, 0) or 0) for k in ("passed", "failed", "skipped", "errors")}


def collected(c: dict | None) -> int:
    return 0 if not c else c["passed"] + c["failed"] + c["errors"]


def cell_path(lib: str, suffix: str) -> Path:
    return RESULTS / f"{lib}_{suffix}.json"


class Report:
    def __init__(self) -> None:
        self.hard: list[str] = []
        self.warn: list[str] = []
        self.info: list[str] = []

    def fail(self, m): self.hard.append(m)
    def warning(self, m): self.warn.append(m)
    def note(self, m): self.info.append(m)


def check_triangulation(rep: Report) -> None:
    print("\n[1] TRIANGULATION - aggregate per_library == standalone per-cell")
    n_checked = n_mismatch = 0
    for agg in sorted(RESULTS.glob("aggregate_lite_*.json")):
        suffix = agg.name[len("aggregate_lite_"):-len(".json")]   # e.g. aider_openai
        try:
            pl = (load(agg).get("per_library") or {})
        except Exception as e:
            rep.fail(f"aggregate unparseable: {agg.name}: {e}")
            continue
        for lib, entry in pl.items():
            cell = cell_path(lib, suffix)
            if not cell.exists():
                rep.warning(f"aggregate {suffix} lists {lib} but no standalone {cell.name}")
                continue
            n_checked += 1
            try:
                cd = load(cell)
            except Exception as e:
                rep.fail(f"per-cell unparseable: {cell.name}: {e}")
                continue
            ac, sc = counts_of(entry), counts_of(cd)
            if ac is not None and sc is not None and ac != sc:
                n_mismatch += 1
                rep.fail(f"counts mismatch {suffix}/{lib}: aggregate={ac} standalone={sc}")
            if entry.get("scoring") and cd.get("scoring") and entry.get("scoring") != cd.get("scoring"):
                rep.fail(f"scoring mismatch {suffix}/{lib}: agg={entry.get('scoring')!r} cell={cd.get('scoring')!r}")
    print(f"    checked {n_checked} aggregate<->cell pairs | {n_mismatch} count mismatch(es)")


def check_denominator_invariance(rep: Report, strict: bool) -> None:
    print("\n[2] DENOMINATOR INVARIANCE - fully-collected cells must agree on collected")
    # The hardcoded-FLOOR heuristic is itself a 'known known' and mislabels libs whose
    # collection unlocks only under some architectures (simpy, imapclient, ...). Instead
    # use a floor-free invariant: among cells that actually RAN a substantial fraction of
    # the suite (passed+failed >= 50% of this lib's max), the *collected* total is a
    # property of the fixed test suite and MUST agree. Collection-crash cells (errors-only)
    # are excluded by construction, so collection-unlock is not a false positive.
    per_lib: dict[str, list[tuple[str, dict]]] = {lib: [] for lib in LIBS}
    for f in RESULTS.glob("*.json"):
        if f.name.startswith("aggregate_") or "_pre_revalidation" in str(f):
            continue
        lib = next((l for l in LIBS if f.name.startswith(l + "_")), None)
        if lib is None:
            continue
        try:
            c = counts_of(load(f))
        except Exception:
            continue
        if c:
            per_lib[lib].append((f.name[len(lib) + 1:-len(".json")], c))
    flagged = 0
    for lib in LIBS:
        cells = per_lib[lib]
        max_pf = max((c["passed"] + c["failed"] for _, c in cells), default=0)
        if max_pf == 0:
            continue
        healthy = [(s, collected(c)) for s, c in cells
                   if (c["passed"] + c["failed"]) >= 0.5 * max_pf]
        distinct = {coll for _, coll in healthy}
        if len(distinct) > 1:
            lo, hi = min(distinct), max(distinct)
            spread = (hi - lo) / hi
            detail = ", ".join(f"{s}={coll}" for s, coll in sorted(healthy))
            line = f"{lib}: fully-collected cells DISAGREE on denominator {lo}..{hi} (spread {spread:.0%}): {detail}"
            flagged += 1
            (rep.fail if (strict or spread > 0.05) else rep.warning)(line)
    print(f"    libs whose fully-collected cells disagree on denominator: {flagged}")


def check_silent_baseline(rep: Report) -> None:
    print("\n[3] SILENT-BASELINE TELL - competitor counts identical to single-shot baseline")
    hits = 0
    for arch in ("aider", "smolagents", "kaizen_delta", "reflexion"):
        for prov in ("anthropic", "openai"):
            base_suffix = f"single_shot_{BASE_PROVIDER[prov] if arch in ('aider','smolagents','kaizen_delta') else prov}"
            comp_suffix = f"{arch}_{prov if arch in ('aider','smolagents','kaizen_delta') else BASE_PROVIDER[prov]}"
            for lib in LIBS:
                comp, base = cell_path(lib, comp_suffix), cell_path(lib, base_suffix)
                if not (comp.exists() and base.exists()):
                    continue
                try:
                    cc, bc = counts_of(load(comp)), counts_of(load(base))
                except Exception:
                    continue
                # Only flag HEALTHY cells (tests actually ran). A collection-crash collapses
                # every architecture to the same 0/0/x/errors as the baseline — that's the
                # floor lib failing identically for all, not a silent-baseline bug.
                if cc and bc and cc == bc and (cc["passed"] + cc["failed"]) > 0:
                    hits += 1
                    rep.warning(f"{comp_suffix}/{lib} counts == baseline {base_suffix} ({cc}) - "
                                f"verify the patch applied (not a silent baseline)")
    print(f"    healthy cells identical to baseline (review): {hits}")


def check_misstamp_and_provenance(rep: Report) -> None:
    print("\n[4/5] MIS-STAMP (full-suite + 0 collected) & PROVENANCE completeness")
    misstamp = prov_bad = legacy_pending = pending_regen = 0
    for f in sorted(RESULTS.glob("*.json")):
        if f.name.startswith("aggregate_") or "_pre_revalidation" in str(f):
            continue
        try:
            d = load(f)
        except Exception as e:
            rep.fail(f"per-cell unparseable: {f.name}: {e}")
            continue
        arch = d.get("branch") or d.get("architecture") or ""
        sc = d.get("scoring")
        if sc in VALID_SCORING and collected(counts_of(d)) == 0:
            misstamp += 1
            rep.fail(f"MIS-STAMP {f.name}: scoring={sc!r} but collected=0")
        if arch in COMPETITOR_ARCHS:
            if sc == "pending-regeneration":
                pending_regen += 1                       # honestly re-marked
            elif sc is None and not d.get("patch_file"):
                legacy_pending += 1                      # legacy -x cell, known pending (guard tracks it)
            elif sc in VALID_SCORING:
                # claims a valid score -> MUST carry full provenance
                for field in ("code_branch", "patch_file", "patch_sha256"):
                    if not d.get(field):
                        prov_bad += 1
                        rep.fail(f"PROVENANCE {f.name}: scoring={sc!r} but missing {field}")
            else:
                rep.warning(f"{f.name}: unexpected scoring tag {sc!r}")
    print(f"    mis-stamps: {misstamp} | tagged-cell provenance gaps: {prov_bad} | "
          f"pending-regen: {pending_regen} | legacy-pending (known): {legacy_pending}")
    if legacy_pending:
        rep.note(f"{legacy_pending} legacy untagged competitor cells (the known aider/anthropic "
                 f"-x gap; tracked by check_scoring_provenance EXPECTED_PENDING)")


def check_cost_anomaly(rep: Report) -> None:
    print("\n[6] COST ANOMALY - passed tests with non-positive recorded spend")
    hits = 0
    for f in RESULTS.glob("*.json"):
        if f.name.startswith("aggregate_") or "_pre_revalidation" in str(f):
            continue
        try:
            d = load(f)
        except Exception:
            continue
        if (d.get("branch") or "") not in (COMPETITOR_ARCHS | {"kaizen_delta"}):
            continue
        c = counts_of(d)
        cost = float((d.get("totals") or {}).get("cost_usd", 0) or 0)
        # Only meaningful for cells that claim a real (recent) score; legacy untagged
        # cells legitimately lack recorded cost.
        if c and c["passed"] > 0 and cost <= 0 and d.get("scoring") in VALID_SCORING:
            hits += 1
            rep.warning(f"{f.name}: passed={c['passed']} but cost_usd={cost} (did the LLM run?)")
    print(f"    cost anomalies on tagged cells (review): {hits}")


def check_patch_sha(rep: Report) -> None:
    print("\n[7] PATCH SHA - patch_sha256 == sha256(patch file)")
    pdir = RESULTS / "patches"
    if not pdir.is_dir():
        print("    SKIPPED - patches/ not in this checkout (they live in the data PR). "
              "Run in WSL / on a checkout with patches to verify.")
        rep.note("patch-sha verification skipped (patches/ absent in this checkout)")
        return
    checked = bad = 0
    for f in sorted(RESULTS.glob("*.json")):
        if f.name.startswith("aggregate_"):
            continue
        try:
            d = load(f)
        except Exception:
            continue
        pf, recorded = d.get("patch_file"), d.get("patch_sha256")
        if not pf or not recorded:
            continue
        pp = (f.parent / pf)
        if not pp.exists():
            rep.fail(f"{f.name}: patch_file {pf} missing on disk")
            continue
        checked += 1
        actual = hashlib.sha256(pp.read_bytes()).hexdigest()
        if actual != recorded:
            bad += 1
            rep.fail(f"{f.name}: patch_sha256 mismatch (recorded {recorded[:12]}..., actual {actual[:12]}...)")
    print(f"    verified {checked} patch hashes | {bad} mismatch(es)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="treat WARN/denominator-variance as failures")
    args = ap.parse_args()

    print(f"matrix audit - scanning {len(list(RESULTS.glob('*.json')))} result JSONs in {RESULTS}")
    rep = Report()
    check_triangulation(rep)
    check_denominator_invariance(rep, args.strict)
    check_silent_baseline(rep)
    check_misstamp_and_provenance(rep)
    check_cost_anomaly(rep)
    check_patch_sha(rep)

    print("\n" + "=" * 64)
    print(f"SUMMARY: {len(rep.hard)} hard | {len(rep.warn)} warn | {len(rep.info)} info")
    for m in rep.hard:
        print(f"  HARD  {m}")
    for m in rep.warn:
        print(f"  WARN  {m}")
    for m in rep.info:
        print(f"  INFO  {m}")

    if rep.hard:
        print("\nFAIL: hard inconsistencies present.")
        return 1
    if args.strict and rep.warn:
        print("\nFAIL (--strict): WARN findings present.")
        return 1
    print("\nOK: no hard inconsistencies. (Review WARN/INFO above.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
