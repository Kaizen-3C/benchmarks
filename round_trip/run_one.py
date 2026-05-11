"""End-to-end round-trip runner for ONE commit0-lite library.

Pipeline (per ADR-0063, with Garbage-In pre-flight added):
    0. Pre-flight (Garbage In check) — verify original_dir exists, is a
       Python source tree, has a test suite. If a pre-existing spec_dir
       is present, run the drift gates against it BEFORE spending money
       on decompose. Garbage in -> garbage out.
    1. Decompose working code    -> spec/<lib>/{adrs,contracts,oracles}/
    2. Run 5 spec-quality gates  (coverage, specificity, consistency,
                                  test_oracle_alignment, implementation_leak)
    3. Recompose from ADRs only  -> recomposed/<lib>/
    4. Run 4 fidelity metrics    (Q1 test / Q2 behavioral / Q3 structural /
                                  Q4 information-loss)
    5. Write results/<lib>_round_trip.json

Phase 1 validation: this must run end-to-end on wcwidth with ZERO LLM
calls, exit 0, print a 5-line progress log, and emit a JSON file whose
shape matches the documented schema.

Run:
    python benchmarks/round_trip/run_one.py wcwidth
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from decompose_from_reference import decompose_from_reference, DEFAULT_REPOS_ROOT  # noqa: E402
from recompose_from_adrs import recompose_from_adrs  # noqa: E402
from remediation import remediate  # noqa: E402
from smoke_test import smoke_test  # noqa: E402
from code_edit_loop import iterate_to_smoke_pass  # noqa: E402
from gates import ALL_GATES  # noqa: E402
from metrics import ALL_METRICS  # noqa: E402


DEFAULT_SPEC_DIR = HERE / "spec"
DEFAULT_RECOMPOSED_DIR = HERE / "recomposed"
DEFAULT_RESULTS_DIR = HERE / "results"


def _write_json(path: Path, payload: dict) -> None:
    """UTF-8 + LF newlines — Windows→Linux-container safe (Python 3.9+)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) + "\n"
    with open(path, "wb") as fh:
        fh.write(text.encode("utf-8"))


def _preflight(lib: str, original_dir: Path, lib_spec_dir: Path) -> dict:
    """Garbage-In check: validate inputs BEFORE spending money on decompose.

    Returns a dict with `pass` (bool), `inputs` (what we found), and
    `pre_decompose_gates` (drift gates run if a pre-existing spec exists).

    Hard failures (pass=False) abort the pipeline; the runner returns the
    pre-flight payload alone so the caller can see why.
    """
    inputs: dict = {
        "original_dir_exists": original_dir.is_dir(),
        "spec_dir_pre_existing": lib_spec_dir.is_dir(),
        "py_files_seen": 0,
        "test_files_seen": 0,
    }

    if not inputs["original_dir_exists"]:
        return {
            "pass": False,
            "inputs": inputs,
            "pre_decompose_gates": {},
            "reason": f"original_dir missing: {original_dir}",
        }

    skip_dirs = {".git", ".tox", "__pycache__", "build", "dist"}
    for py in original_dir.rglob("*.py"):
        if any(part in skip_dirs for part in py.parts):
            continue
        inputs["py_files_seen"] += 1
        if py.name.startswith("test_") or py.name.endswith("_test.py"):
            inputs["test_files_seen"] += 1

    if inputs["py_files_seen"] == 0:
        return {
            "pass": False,
            "inputs": inputs,
            "pre_decompose_gates": {},
            "reason": "no Python source files under original_dir",
        }

    pre_gates: dict[str, dict] = {}
    if inputs["spec_dir_pre_existing"]:
        for gate_mod in ALL_GATES:
            r = gate_mod.check(lib_spec_dir, original_dir)
            pre_gates[r["gate"]] = {
                "pass": r.get("pass"),
                "failures": r.get("failures", []),
                "stats": r.get("stats", {}),
            }

    return {
        "pass": True,
        "inputs": inputs,
        "pre_decompose_gates": pre_gates,
        "reason": "ok",
    }


def run_one(
    lib: str,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
    spec_dir: Path = DEFAULT_SPEC_DIR,
    recomposed_dir: Path = DEFAULT_RECOMPOSED_DIR,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    repos_root: Path = DEFAULT_REPOS_ROOT,
    skip_decompose: bool = False,
    timeout: float | None = None,
    remediate_enabled: bool = False,
    code_edit_loop_enabled: bool = False,
    code_edit_max_iters: int = 3,
) -> dict:
    t0 = time.time()
    original_dir = repos_root / lib
    lib_spec_dir = spec_dir / lib

    # 0. Pre-flight (Garbage In check)
    preflight = _preflight(lib, original_dir, lib_spec_dir)
    pre_gate_count = len(preflight["pre_decompose_gates"])
    print(
        f"[0/5] preflight: pass={preflight['pass']} "
        f"py_files={preflight['inputs']['py_files_seen']} "
        f"tests={preflight['inputs']['test_files_seen']} "
        f"pre_decompose_gates={pre_gate_count}"
    )
    if not preflight["pass"]:
        print(f"      ABORT: {preflight['reason']}")
        out_path = results_dir / f"{lib}_round_trip.json"
        payload = {
            "lib": lib,
            "preflight": preflight,
            "aborted_at": "preflight",
            "totals": {"cost_usd": 0.0, "elapsed_s": round(time.time() - t0, 3)},
        }
        _write_json(out_path, payload)
        return payload

    # 1. Decompose (skip if caller pre-staged the spec, e.g. customer mode)
    if skip_decompose:
        decomp = {"cost_usd": 0.0, "elapsed_s": 0.0, "files_in_spec": -1, "skipped": True}
    else:
        decomp = decompose_from_reference(
            lib, spec_dir, provider, model, repos_root, timeout=timeout,
        )
    print(f"[1/5] decompose: files_in_spec={decomp['files_in_spec']} "
          f"cost=${decomp['cost_usd']:.4f} elapsed={decomp['elapsed_s']}s")

    # 2. Gates (post-decompose drift check)
    gate_results: dict[str, dict] = {}
    for gate_mod in ALL_GATES:
        r = gate_mod.check(lib_spec_dir, original_dir)
        gate_results[r["gate"]] = {
            "pass": r.get("pass"),
            "failures": r.get("failures", []),
            "stats": r.get("stats", {}),
        }
    gates_passing = sum(1 for r in gate_results.values() if r["pass"] is True)
    print(f"[2/5] gates: {gates_passing}/{len(gate_results)} pass "
          f"({', '.join(gate_results.keys())})")

    # 2.5. Remediation (optional) — amend spec if any gates failed.
    remediation_result: dict | None = None
    post_remediation_gates: dict[str, dict] | None = None
    if remediate_enabled and gates_passing < len(gate_results):
        remediation_result = remediate(
            gate_results, lib_spec_dir, provider, model, timeout=timeout,
        )
        print(f"[2.5/5] remediation: amendments={remediation_result.get('amendments_applied', 0)} "
              f"cost=${remediation_result.get('cost_usd', 0):.4f} "
              f"elapsed={remediation_result.get('elapsed_s', 0)}s")
        # Re-run gates against the amended spec for diagnostics.
        post_remediation_gates = {}
        for gate_mod in ALL_GATES:
            r = gate_mod.check(lib_spec_dir, original_dir)
            post_remediation_gates[r["gate"]] = {
                "pass": r.get("pass"),
                "failures": r.get("failures", []),
                "stats": r.get("stats", {}),
            }
        post_pass = sum(1 for r in post_remediation_gates.values() if r["pass"] is True)
        print(f"        post-remediation gates: {post_pass}/{len(post_remediation_gates)} pass")

    # 3. Recompose
    recomp = recompose_from_adrs(
        lib, spec_dir, recomposed_dir, provider, model, timeout=timeout,
    )
    print(f"[3/5] recompose: files_emitted={recomp['files_emitted']} "
          f"cost=${recomp['cost_usd']:.4f} elapsed={recomp['elapsed_s']}s")

    # 3.5. Smoke test (zero LLM) + optional traceback-driven remediation pass.
    lib_recomp_dir = recomposed_dir / lib
    smoke = smoke_test(original_dir, lib_recomp_dir)
    print(f"[3.5/5] smoke: import_ok={smoke['import']['ok']} "
          f"collect_ok={smoke['collect'].get('ok')} pkg={smoke.get('package_name')}")
    smoke_remediation: dict | None = None
    if remediate_enabled and not smoke["ok"] and smoke["first_traceback"]:
        smoke_remediation = remediate(
            gate_results, lib_spec_dir, provider, model,
            timeout=timeout, smoke_traceback=smoke["first_traceback"],
        )
        print(f"        traceback-driven remediation: "
              f"amendments={smoke_remediation.get('amendments_applied', 0)} "
              f"cost=${smoke_remediation.get('cost_usd', 0):.4f}")
        # Re-recompose against the amended spec.
        recomp2 = recompose_from_adrs(
            lib, spec_dir, recomposed_dir, provider, model, timeout=timeout,
        )
        print(f"        re-recompose: files_emitted={recomp2['files_emitted']} "
              f"cost=${recomp2['cost_usd']:.4f}")
        # Roll the second recompose's cost into the totals; replace the
        # primary recompose record with a combined one for accounting clarity.
        recomp = {
            **recomp2,
            "cost_usd": round(recomp["cost_usd"] + recomp2["cost_usd"], 4),
            "elapsed_s": round(recomp["elapsed_s"] + recomp2["elapsed_s"], 3),
            "remediated": True,
        }
        # Re-smoke for the result record.
        smoke = smoke_test(original_dir, lib_recomp_dir)
        print(f"        post-remediation smoke: import_ok={smoke['import']['ok']} "
              f"collect_ok={smoke['collect'].get('ok')}")

    # 3.75. Stage 2 (ADR-0064): code-editing iteration loop.
    code_edit_result: dict | None = None
    if code_edit_loop_enabled and not smoke["ok"]:
        code_edit_result = iterate_to_smoke_pass(
            original_dir, lib_recomp_dir,
            max_iters=code_edit_max_iters,
            provider=provider, model=model, timeout=timeout,
        )
        print(f"[3.75/5] code-edit loop: ok={code_edit_result['ok']} "
              f"iters={code_edit_result['iterations']} "
              f"cost=${code_edit_result['cost_usd']:.4f}")
        smoke = code_edit_result["final_smoke"]

    # 4. Metrics
    metric_results: dict[str, dict] = {}
    for metric_mod in ALL_METRICS:
        r = metric_mod.compute(original_dir, lib_recomp_dir, spec_dir=lib_spec_dir)
        metric_results[r["metric"]] = {"value": r.get("value"), "detail": r.get("detail", {})}
    print(f"[4/5] metrics: {len(metric_results)} computed "
          f"({', '.join(metric_results.keys())})")

    # 5. Emit result
    rem_cost = remediation_result["cost_usd"] if remediation_result else 0.0
    smoke_rem_cost = smoke_remediation["cost_usd"] if smoke_remediation else 0.0
    code_edit_cost = code_edit_result["cost_usd"] if code_edit_result else 0.0
    totals = {
        "cost_usd": round(
            decomp["cost_usd"] + recomp["cost_usd"] + rem_cost
            + smoke_rem_cost + code_edit_cost, 4
        ),
        "elapsed_s": round(time.time() - t0, 3),
    }
    payload = {
        "lib": lib,
        "provider": provider,
        "model": model,
        "preflight": preflight,
        "decompose": decomp,
        "gates": gate_results,
        "remediation": remediation_result,
        "smoke_test": {
            "ok": smoke["ok"],
            "import_ok": smoke["import"]["ok"],
            "collect_ok": smoke["collect"].get("ok"),
            "first_traceback": smoke.get("first_traceback", ""),
            "package_name": smoke.get("package_name"),
        },
        "smoke_remediation": smoke_remediation,
        "code_edit_loop": code_edit_result,
        "post_remediation_gates": post_remediation_gates,
        "recompose": recomp,
        "metrics": metric_results,
        "totals": totals,
    }
    out_path = results_dir / f"{lib}_round_trip.json"
    _write_json(out_path, payload)
    print(f"[5/5] wrote: {out_path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lib", help="commit0-lite library name (e.g., wcwidth)")
    parser.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--repos-root", type=Path, default=DEFAULT_REPOS_ROOT)
    parser.add_argument("--spec-dir", type=Path, default=DEFAULT_SPEC_DIR)
    parser.add_argument("--recomposed-dir", type=Path, default=DEFAULT_RECOMPOSED_DIR)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--skip-decompose",
        action="store_true",
        help="Skip decompose; assume spec_dir/<lib>/ is pre-staged (customer mode).",
    )
    parser.add_argument(
        "--timeout", type=float, default=None,
        help="Per-LLM-call timeout in seconds (default: LLMClient default of 300).",
    )
    parser.add_argument(
        "--remediate", action="store_true",
        help="Run a single-pass spec amendment loop after gates fire (Phase 3).",
    )
    parser.add_argument(
        "--code-edit-loop", action="store_true",
        help="Run Stage 2 code-editing iteration loop (ADR-0064).",
    )
    parser.add_argument(
        "--code-edit-max-iters", type=int, default=3,
        help="Max iterations for the code-edit loop (default: 3).",
    )
    args = parser.parse_args()

    run_one(
        args.lib,
        provider=args.provider,
        model=args.model,
        spec_dir=args.spec_dir,
        recomposed_dir=args.recomposed_dir,
        results_dir=args.results_dir,
        repos_root=args.repos_root,
        skip_decompose=args.skip_decompose,
        timeout=args.timeout,
        remediate_enabled=args.remediate,
        code_edit_loop_enabled=args.code_edit_loop,
        code_edit_max_iters=args.code_edit_max_iters,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
