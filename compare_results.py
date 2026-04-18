"""
Compare CD-AOR benchmark results against published baselines.

Usage:
    python -m benchmarks.compare_results --results-dir ./benchmark_results
    python -m benchmarks.compare_results --results-dir ./benchmark_results --benchmark humaneval

Produces formatted comparison tables showing CD-AOR performance vs
Related Work systems (Reflexion, LATS, MetaGPT, SWE-agent, Meta-Harness).
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Published baselines from Related Work
BASELINES: Dict[str, List[Dict[str, Any]]] = {
    "humaneval": [
        {"system": "GPT-4 (single-shot)", "pass@1": 67.0, "year": 2023, "paper": "OpenAI"},
        {"system": "MetaGPT", "pass@1": 87.7, "year": 2023, "paper": "Hong et al."},
        {"system": "Reflexion", "pass@1": 91.0, "year": 2023, "paper": "Shinn et al."},
        {"system": "LATS", "pass@1": 94.4, "year": 2023, "paper": "Zhou et al."},
    ],
    "mbpp": [
        {"system": "Reflexion", "pass@1": 77.1, "year": 2023, "paper": "Shinn et al."},
        {"system": "LATS", "pass@1": 81.0, "year": 2023, "paper": "Zhou et al."},
    ],
    "swebench": [
        {"system": "SWE-agent", "resolved": 12.5, "year": 2024, "paper": "Princeton"},
        {"system": "AutoCodeRover", "resolved": 22.7, "year": 2024, "paper": "Zhang et al."},
        {"system": "CodeR", "resolved": 28.3, "year": 2024, "paper": "Chen et al."},
    ],
    "terminalbench": [
        {"system": "Meta-Harness (Opus 4.6)", "passed": 76.4, "year": 2026, "paper": "Lee et al."},
        {"system": "Meta-Harness (Haiku 4.5)", "passed": 37.6, "year": 2026, "paper": "Lee et al."},
    ],
}


def load_latest_result(results_dir: Path, benchmark: str) -> Optional[Dict[str, Any]]:
    """Load the most recent result file for a benchmark."""
    pattern = f"{benchmark}_*.json"
    files = sorted(results_dir.glob(pattern), reverse=True)
    if not files:
        return None
    path = files[0]
    logger.info("Loading %s", path)
    return json.loads(path.read_text())


def format_comparison_table(benchmark: str, cdaor_result: Optional[Dict[str, Any]]) -> str:
    """Format a comparison table for a benchmark."""
    baselines = BASELINES.get(benchmark, [])
    if not baselines:
        return f"No baselines available for {benchmark}"

    # Determine the metric name
    if benchmark in ("humaneval", "mbpp"):
        metric = "pass@1"
        metric_label = "pass@1 (%)"
    elif benchmark == "swebench":
        metric = "resolved"
        metric_label = "Resolved (%)"
    elif benchmark == "terminalbench":
        metric = "passed"
        metric_label = "Passed (%)"
    else:
        metric = "score"
        metric_label = "Score (%)"

    lines = []
    lines.append(f"\n{'=' * 70}")
    lines.append(f"  {benchmark.upper()} — Comparison with Related Work")
    lines.append(f"{'=' * 70}")
    lines.append(f"  {'System':<35s} {metric_label:>12s}  {'Year':>6s}  {'Source'}")
    lines.append(f"  {'-' * 35} {'-' * 12}  {'-' * 6}  {'-' * 15}")

    for b in baselines:
        val = b.get(metric, 0)
        lines.append(f"  {b['system']:<35s} {val:>11.1f}%  {b['year']:>6d}  {b['paper']}")

    # CD-AOR result
    if cdaor_result:
        cdaor_val = cdaor_result.get("pass@1", cdaor_result.get("resolved", cdaor_result.get("passed", 0)))
        cdaor_pct = cdaor_val * 100 if cdaor_val <= 1.0 else cdaor_val
        lines.append(f"  {'-' * 35} {'-' * 12}  {'-' * 6}  {'-' * 15}")
        lines.append(f"  {'CD-AOR (ours)':<35s} {cdaor_pct:>11.1f}%  {'2026':>6s}  {'This work'}")

        # Additional CD-AOR details
        lines.append(f"\n  CD-AOR Details:")
        lines.append(f"    Tasks:          {cdaor_result.get('total', 'N/A')}")
        lines.append(f"    Passed:         {cdaor_result.get('passed', 'N/A')}")
        lines.append(f"    Avg Confidence:  {cdaor_result.get('avg_confidence', 'N/A')}")
        lines.append(f"    Avg Steps:       {cdaor_result.get('avg_steps', 'N/A')}")
        lines.append(f"    Avg Duration:    {cdaor_result.get('avg_duration_s', 'N/A')}s")
        lines.append(f"    Total Cost:      ${cdaor_result.get('total_cost_usd', 'N/A')}")
    else:
        lines.append(f"  {'-' * 35} {'-' * 12}  {'-' * 6}  {'-' * 15}")
        lines.append(f"  {'CD-AOR (ours)':<35s} {'[not run]':>12s}  {'2026':>6s}  {'This work'}")

    lines.append(f"{'=' * 70}")
    return "\n".join(lines)


def format_ablation_summary(results_dir: Path) -> str:
    """Look for multiple result files per benchmark and summarize ablation data."""
    lines = ["\n" + "=" * 70, "  ABLATION STUDY SUMMARY", "=" * 70]

    for benchmark in BASELINES:
        pattern = f"{benchmark}_*.json"
        files = sorted(results_dir.glob(pattern))
        if len(files) < 2:
            continue

        lines.append(f"\n  {benchmark.upper()} ({len(files)} runs):")
        lines.append(f"  {'Run File':<40s} {'pass@1':>10s} {'Steps':>8s} {'Cost':>8s}")
        lines.append(f"  {'-' * 40} {'-' * 10} {'-' * 8} {'-' * 8}")

        for f in files:
            data = json.loads(f.read_text())
            val = data.get("pass@1", data.get("resolved", data.get("passed", 0)))
            pct = val * 100 if val <= 1.0 else val
            steps = data.get("avg_steps", "N/A")
            cost = data.get("total_cost_usd", "N/A")
            lines.append(f"  {f.name:<40s} {pct:>9.1f}% {steps:>8s} ${cost:>7s}")

    if len(lines) == 3:
        lines.append("\n  No ablation data found (need 2+ runs per benchmark)")

    lines.append("=" * 70)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare CD-AOR results against published baselines")
    parser.add_argument("--results-dir", type=Path, default=Path("./benchmark_results"))
    parser.add_argument("--benchmark", choices=list(BASELINES.keys()), default=None,
                        help="Show only one benchmark (default: all)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.results_dir.exists():
        print(f"\nResults directory not found: {args.results_dir}")
        print("Run benchmarks first: python -m benchmarks.runner --benchmark humaneval --data-dir ./data/benchmarks")
        return

    benchmarks = [args.benchmark] if args.benchmark else list(BASELINES.keys())

    print("\nCD-AOR Benchmark Comparison Report")
    print("Generated from:", args.results_dir)

    for benchmark in benchmarks:
        result = load_latest_result(args.results_dir, benchmark)
        print(format_comparison_table(benchmark, result))

    # Ablation summary if multiple runs exist
    print(format_ablation_summary(args.results_dir))


if __name__ == "__main__":
    main()
