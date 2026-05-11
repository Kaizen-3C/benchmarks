"""Multi-library, multi-language round-trip sweep runner.

Lays out repos as `<repos_root>/<lib>/`. For each lib in --libs, picks the
adapter (auto-detect from repo layout, or override via --lang), runs
`multilang_one.round_trip`, and aggregates per-lang Q1 means.

Run:
    python benchmarks/round_trip/multilang_lite.py \\
        --lang rust \\
        --libs ru_lru ru_intervals ru_derives \\
        --repos-root ~/kaizen-rust-corpus/repos \\
        --rerun-dir <out>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from multilang_one import round_trip  # noqa: E402
import lang_adapter  # noqa: E402


def _aggregate(results: dict[str, dict]) -> dict:
    libs = list(results.values())
    cost = sum(r.get("totals", {}).get("cost_usd", 0) for r in libs if "totals" in r)
    wall = sum(r.get("totals", {}).get("elapsed_s", 0) for r in libs if "totals" in r)

    q1_vals: list[float] = []
    smoke_pass = smoke_fail = 0
    per_lib: dict[str, float | None] = {}
    for lib, r in results.items():
        v = r.get("metrics", {}).get("q1_test_parity", {}).get("value")
        per_lib[lib] = v
        if isinstance(v, (int, float)):
            q1_vals.append(v)
        s = r.get("smoke", {}).get("ok")
        if s is True:
            smoke_pass += 1
        elif s is False:
            smoke_fail += 1

    return {
        "libs_total": len(libs),
        "cost_usd_total": round(cost, 4),
        "wall_seconds_total": round(wall, 1),
        "smoke_pass": smoke_pass,
        "smoke_fail": smoke_fail,
        "q1_mean": (round(sum(q1_vals) / len(q1_vals), 4)
                    if q1_vals else None),
        "q1_per_lib": per_lib,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lang", required=True,
                    choices=["python", "rust", "typescript"])
    ap.add_argument("--libs", nargs="+", required=True)
    ap.add_argument("--repos-root", type=Path, required=True)
    ap.add_argument("--rerun-dir", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=2,
                    help="Parallel libraries (default 2; lower than Python "
                         "sweeps because cargo / vitest can be CPU heavy).")
    ap.add_argument("--provider", default="anthropic")
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--max-cost-usd", type=float, default=10.0)
    args = ap.parse_args()

    rerun_dir: Path = args.rerun_dir.resolve()
    rerun_dir.mkdir(parents=True, exist_ok=True)

    print(f"[multilang_lite] {len(args.libs)} libs · lang={args.lang} · "
          f"workers={args.workers}")
    print(f"[multilang_lite] output: {rerun_dir}")
    print()

    t0 = time.time()
    results: dict[str, dict] = {}
    cost_so_far = 0.0
    aborted = False

    def _do_one(lib: str) -> tuple[str, dict]:
        return lib, round_trip(
            lib, args.lang, args.repos_root.resolve(), rerun_dir,
            args.provider, args.model, args.timeout, clean=True,
        )

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_do_one, lib): lib for lib in args.libs}
        for fut in as_completed(futs):
            lib = futs[fut]
            try:
                _lib, r = fut.result()
                results[lib] = r
                lib_cost = r.get("totals", {}).get("cost_usd", 0)
                lib_wall = r.get("totals", {}).get("elapsed_s", 0)
                q1 = r.get("metrics", {}).get("q1_test_parity", {}).get("value")
                smoke_ok = r.get("smoke", {}).get("ok")
                cost_so_far += lib_cost
                print(
                    f"  {'ok' if smoke_ok else 'FAIL':<5} "
                    f"{lib:18} q1={q1 if isinstance(q1, float) else q1!r:>6} "
                    f"smoke={smoke_ok!s:5} cost=${lib_cost:.3f} wall={lib_wall:.0f}s "
                    f"(running ${cost_so_far:.2f})",
                    flush=True,
                )
                if cost_so_far >= args.max_cost_usd and not aborted:
                    print(f"  ! cost ceiling ${args.max_cost_usd:.2f} reached")
                    aborted = True
            except Exception as e:
                print(f"  X {lib:18} ERROR: {type(e).__name__}: {e}",
                      flush=True)
                results[lib] = {"error": f"{type(e).__name__}: {e}"}

    aggregate = _aggregate(results)
    aggregate["wall_seconds_total_actual"] = round(time.time() - t0, 1)
    aggregate["lang"] = args.lang
    aggregate["provider"] = args.provider

    out = {"aggregate": aggregate, "per_library": results,
            "completed": list(results.keys())}
    out_path = rerun_dir / f"aggregate_{args.lang}.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    print()
    print("=" * 60)
    print("AGGREGATE")
    print("=" * 60)
    print(f"libs:        {aggregate['libs_total']}")
    print(f"smoke pass:  {aggregate['smoke_pass']}/{aggregate['libs_total']}")
    print(f"Q1 mean:     {aggregate['q1_mean']}")
    print(f"cost total:  ${aggregate['cost_usd_total']:.2f}")
    print(f"wall actual: {aggregate['wall_seconds_total_actual']:.0f}s")
    print(f"wrote:       {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
