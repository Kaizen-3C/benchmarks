"""Q4 Information Loss: % of public symbols mentioned in >=1 ADR.

Phase 2: enumerate public symbols in `original_dir` via static analysis,
grep the ADR/contract text under the matching spec directory, report
coverage fraction plus the list of orphan symbols.

Signature kept symmetric with q1-q3; `spec_dir` is passed via kwargs so
the shared runner can loop uniformly.
"""

from __future__ import annotations

from pathlib import Path


def compute(original_dir: Path, recomposed_dir: Path, **kwargs) -> dict:
    spec_dir = kwargs.get("spec_dir")
    return {
        "metric": "q4_information_loss",
        "value": None,
        "detail": {
            "todo": "phase 2: public-symbol coverage in ADR text",
            "spec_dir": str(spec_dir) if spec_dir else None,
        },
    }
