"""Specificity gate: ADRs must be concrete enough to rebuild from.

Per ADR-0063: vague ADRs ("we use a cache") give Recompose too much freedom
and the result diverges from the original. This gate scores each ADR for
concreteness using deterministic heuristics — no LLM dependency, no
training required.

Scoring (per ADR):
    base                        = 0
    + concrete signals
        + 1.0 for any digit run >=2 chars (e.g., "128", "0.5")
        + 1.0 for any quantitative phrase ("max", "min", "exactly N")
        + 0.5 for each named library/algorithm reference (LRU, JSON, etc.)
    - vagueness signals
        - 0.5 per vague modal ("may", "might", "could", "should",
          "typically", "usually", "often", "in some cases")
        - 0.5 per hedge ("approximately", "roughly", "about", "around")

    Final score = sum(signals); fail threshold = +1.0 (must clear vagueness
    AND have at least one concrete anchor).

A score below the threshold means: this ADR will not survive Recompose
without drift. The remediation hint names what's missing.
"""

from __future__ import annotations

import re
from pathlib import Path


_VAGUE_MODALS = re.compile(
    r"\b(may|might|could|should|typically|usually|often|sometimes)\b",
    re.IGNORECASE,
)
_HEDGES = re.compile(
    r"\b(approximately|roughly|about|around|some|several|various)\b",
    re.IGNORECASE,
)
_DIGIT_RUNS = re.compile(r"\b\d{2,}\b|\b\d+\.\d+\b|\b\d+\s*(ms|s|kb|mb|gb|%)\b", re.IGNORECASE)
_QUANTITATIVE = re.compile(
    r"\b(max|min|maximum|minimum|exactly|at\s+most|at\s+least|threshold|limit)\b",
    re.IGNORECASE,
)
_NAMED_REFS = re.compile(
    r"\b(LRU|FIFO|LIFO|TTL|JSON|YAML|XML|UTF-?8|ASCII|UNICODE|"
    r"O\(\d+\)|O\(n\)|O\(log\s*n\)|O\(n\^?2\)|O\(n\s*log\s*n\)|"
    r"sha-?256|sha-?512|md5|hmac|aes|rsa)\b",
    re.IGNORECASE,
)

FAIL_THRESHOLD = 1.0


def _score_adr(text: str) -> tuple[float, dict]:
    digit_hits = len(_DIGIT_RUNS.findall(text))
    quant_hits = len(_QUANTITATIVE.findall(text))
    named_hits = len(_NAMED_REFS.findall(text))
    vague_hits = len(_VAGUE_MODALS.findall(text))
    hedge_hits = len(_HEDGES.findall(text))

    score = (
        min(digit_hits, 5) * 1.0
        + min(quant_hits, 3) * 1.0
        + min(named_hits, 4) * 0.5
        - vague_hits * 0.5
        - hedge_hits * 0.5
    )
    return round(score, 2), {
        "digit_runs": digit_hits,
        "quantitative_phrases": quant_hits,
        "named_refs": named_hits,
        "vague_modals": vague_hits,
        "hedges": hedge_hits,
    }


def check(spec_dir: Path, original_dir: Path) -> dict:
    adrs_dir = spec_dir / "adrs"
    if not adrs_dir.is_dir():
        return {
            "gate": "specificity",
            "pass": False,
            "failures": [{"reason": "adrs_dir_missing", "path": str(adrs_dir)}],
        }

    failures: list[dict] = []
    scores: list[dict] = []

    for adr in sorted(adrs_dir.rglob("*.md")):
        try:
            text = adr.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        score, breakdown = _score_adr(text)
        rel = adr.relative_to(spec_dir).as_posix()
        scores.append({"adr": rel, "score": score, **breakdown})

        positive_signals = (
            breakdown["digit_runs"] + breakdown["quantitative_phrases"]
            + breakdown["named_refs"]
        )
        # Fail if score is below threshold OR if there are no concrete signals
        # at all (regardless of score). An ADR with zero positive anchors is
        # content-free even if it has zero negatives.
        if score < FAIL_THRESHOLD or positive_signals < 2:
            missing: list[str] = []
            if breakdown["digit_runs"] == 0 and breakdown["quantitative_phrases"] == 0:
                missing.append("concrete numbers or quantitative bounds")
            if breakdown["named_refs"] == 0:
                missing.append("named algorithm/library references")
            if breakdown["vague_modals"] > 0:
                missing.append(
                    f"vague modals ({breakdown['vague_modals']} hits — "
                    "replace 'may'/'should'/'typically' with concrete decisions)"
                )

            failures.append(
                {
                    "adr": rel,
                    "score": score,
                    "threshold": FAIL_THRESHOLD,
                    "breakdown": breakdown,
                    "remediation": (
                        f"ADR {rel} scored {score} (threshold {FAIL_THRESHOLD}). "
                        f"Add: {', '.join(missing) if missing else 'concrete decisions'}."
                    ),
                }
            )

    return {
        "gate": "specificity",
        "pass": len(failures) == 0,
        "failures": failures,
        "stats": {
            "adrs_scored": len(scores),
            "adrs_passed": len(scores) - len(failures),
            "scores": scores,
        },
    }
