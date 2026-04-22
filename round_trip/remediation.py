"""Gate-failure -> suggested-fix mapper.

Phase 3: given a list of gate results, emit a structured remediation
report — per failure, propose a concrete fix (ADR amendment snippet,
oracle row to add, leaked snippet to rewrite, etc.). The report is what
a human or a second Decompose pass would consume to close the gap.

Phase 1: stub returns an empty report. Makes ZERO LLM calls.
"""

from __future__ import annotations


def remediate(gate_results: list[dict]) -> dict:
    """Return a report of suggested fixes for each failing gate.

    Args:
        gate_results: list of dicts as returned by each gate's `check()`.
    Returns:
        {"remediations": [{"gate": str, "failures": list[dict], "fix": str}, ...]}
    """
    return {"remediations": []}
