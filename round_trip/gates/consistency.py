"""Consistency gate: no dangling cross-references in contracts/ADRs.

Per ADR-0063: if Contract A says "use Schema B" and Schema B doesn't exist,
Recompose will fail or invent. This gate parses every cross-reference in
the spec and verifies its target is present.

References we resolve:
    - `ADR-NNNN` (or `ADR-NNNN-slug`) — must match an ADR file by number.
    - `contracts/<name>` or `Contract <Name>` — must match a contract file.
    - `oracles/<name>.jsonl` — must match an oracle file.

Self-references (an ADR mentioning its own ID in its title) are excluded.
"""

from __future__ import annotations

import re
from pathlib import Path


_ADR_REF = re.compile(r"\bADR-(\d{4})\b")
_CONTRACT_REF = re.compile(
    r"`contracts/([A-Za-z0-9_./-]+?)(?:\.md)?`|"
    r"\bContract\s+([A-Za-z0-9_-]+)\b"
)
_ORACLE_REF = re.compile(r"`oracles/([A-Za-z0-9_./-]+?)(?:\.jsonl)?`")


def _adr_id_from_filename(path: Path) -> str | None:
    m = re.match(r"ADR-(\d{4})", path.stem)
    return m.group(1) if m else None


def _existing_targets(spec_dir: Path) -> dict[str, set[str]]:
    adrs: set[str] = set()
    contracts: set[str] = set()
    oracles: set[str] = set()

    adrs_dir = spec_dir / "adrs"
    if adrs_dir.is_dir():
        for f in adrs_dir.rglob("*.md"):
            aid = _adr_id_from_filename(f)
            if aid:
                adrs.add(aid)

    contracts_dir = spec_dir / "contracts"
    if contracts_dir.is_dir():
        for f in contracts_dir.rglob("*"):
            if f.is_file():
                contracts.add(f.stem)
                contracts.add(f.relative_to(contracts_dir).with_suffix("").as_posix())

    oracles_dir = spec_dir / "oracles"
    if oracles_dir.is_dir():
        for f in oracles_dir.rglob("*.jsonl"):
            oracles.add(f.stem)
            oracles.add(f.relative_to(oracles_dir).with_suffix("").as_posix())

    return {"adrs": adrs, "contracts": contracts, "oracles": oracles}


def _spec_files(spec_dir: Path) -> list[Path]:
    out: list[Path] = []
    for sub in ("adrs", "contracts", "oracles"):
        d = spec_dir / sub
        if d.is_dir():
            for f in d.rglob("*"):
                if f.is_file() and f.suffix in {".md", ".markdown", ".txt", ".jsonl"}:
                    out.append(f)
    return out


def check(spec_dir: Path, original_dir: Path) -> dict:
    if not spec_dir.is_dir():
        return {
            "gate": "consistency",
            "pass": False,
            "failures": [{"reason": "spec_dir_missing", "path": str(spec_dir)}],
        }

    targets = _existing_targets(spec_dir)
    failures: list[dict] = []
    refs_total = 0

    for f in _spec_files(spec_dir):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = f.relative_to(spec_dir).as_posix()
        self_adr = _adr_id_from_filename(f)

        for m in _ADR_REF.finditer(text):
            refs_total += 1
            target = m.group(1)
            if target == self_adr:
                continue
            if target not in targets["adrs"]:
                failures.append(
                    {
                        "in_file": rel,
                        "ref_kind": "adr",
                        "ref": f"ADR-{target}",
                        "remediation": (
                            f"{rel} references ADR-{target}, which does not exist "
                            f"under {spec_dir}/adrs/. Either author the missing "
                            f"ADR or correct the reference."
                        ),
                    }
                )

        for m in _CONTRACT_REF.finditer(text):
            refs_total += 1
            target = (m.group(1) or m.group(2) or "").strip()
            if not target:
                continue
            if target not in targets["contracts"] and target.split("/")[-1] not in targets["contracts"]:
                failures.append(
                    {
                        "in_file": rel,
                        "ref_kind": "contract",
                        "ref": target,
                        "remediation": (
                            f"{rel} references contract `{target}`, which does not "
                            f"exist under {spec_dir}/contracts/. Author it or "
                            f"correct the reference."
                        ),
                    }
                )

        for m in _ORACLE_REF.finditer(text):
            refs_total += 1
            target = m.group(1).strip()
            if target not in targets["oracles"] and target.split("/")[-1] not in targets["oracles"]:
                failures.append(
                    {
                        "in_file": rel,
                        "ref_kind": "oracle",
                        "ref": target,
                        "remediation": (
                            f"{rel} references oracle `{target}`, which does not "
                            f"exist under {spec_dir}/oracles/. Author it or "
                            f"correct the reference."
                        ),
                    }
                )

    return {
        "gate": "consistency",
        "pass": len(failures) == 0,
        "failures": failures,
        "stats": {
            "refs_checked": refs_total,
            "refs_dangling": len(failures),
            "targets_indexed": {k: len(v) for k, v in targets.items()},
        },
    }
