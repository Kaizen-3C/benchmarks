"""
Confidence Calibration Analysis for CD-AOR.

Analyzes correlation between CD-AOR's composite confidence score
and actual pass/fail on benchmark tasks. A well-calibrated system
should show higher confidence on passing tasks.

Usage:
    python -m benchmarks.calibration --results-dir ./benchmark_results
    python -m benchmarks.calibration --results-dir ./benchmark_results --benchmark humaneval
"""
from __future__ import annotations

import argparse
import json
import math
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def load_per_task_results(results_dir: Path, benchmark: str) -> List[Dict]:
    """Load per-task results from the latest benchmark result file."""
    pattern = f"{benchmark}_*.json"
    files = sorted(results_dir.glob(pattern), reverse=True)
    if not files:
        return []
    data = json.loads(files[0].read_text())
    return data.get("per_task", [])


def compute_calibration_stats(tasks: List[Dict]) -> Dict:
    """Compute calibration statistics from per-task results."""
    if not tasks:
        return {"error": "No task results found"}

    passed = [t for t in tasks if t.get("passed", False)]
    failed = [t for t in tasks if not t.get("passed", False)]

    def avg_conf(task_list):
        confs = [t["confidence"] for t in task_list if t.get("confidence", 0) > 0]
        return sum(confs) / len(confs) if confs else 0.0

    def std_conf(task_list):
        confs = [t["confidence"] for t in task_list if t.get("confidence", 0) > 0]
        if len(confs) < 2:
            return 0.0
        mean = sum(confs) / len(confs)
        variance = sum((c - mean) ** 2 for c in confs) / (len(confs) - 1)
        return math.sqrt(variance)

    stats = {
        "total_tasks": len(tasks),
        "passed": len(passed),
        "failed": len(failed),
        "pass_rate": len(passed) / len(tasks) if tasks else 0,
        "avg_confidence_passed": round(avg_conf(passed), 4),
        "avg_confidence_failed": round(avg_conf(failed), 4),
        "std_confidence_passed": round(std_conf(passed), 4),
        "std_confidence_failed": round(std_conf(failed), 4),
        "confidence_gap": round(avg_conf(passed) - avg_conf(failed), 4),
    }

    # Calibration buckets: group by confidence range, compute actual pass rate
    buckets = {}
    for t in tasks:
        conf = t.get("confidence", 0)
        if conf <= 0:
            continue
        bucket = int(conf * 10) / 10  # 0.0, 0.1, 0.2, ...
        bucket_key = f"{bucket:.1f}-{bucket + 0.1:.1f}"
        if bucket_key not in buckets:
            buckets[bucket_key] = {"total": 0, "passed": 0}
        buckets[bucket_key]["total"] += 1
        if t.get("passed", False):
            buckets[bucket_key]["passed"] += 1

    calibration_curve = {}
    for key in sorted(buckets.keys()):
        b = buckets[key]
        calibration_curve[key] = {
            "total": b["total"],
            "passed": b["passed"],
            "actual_pass_rate": round(b["passed"] / b["total"], 3) if b["total"] > 0 else 0,
        }
    stats["calibration_curve"] = calibration_curve

    # Point-biserial correlation approximation
    # r_pb = (M1 - M0) / S * sqrt(n1*n0 / N^2)
    all_confs = [t["confidence"] for t in tasks if t.get("confidence", 0) > 0]
    if all_confs and len(passed) > 0 and len(failed) > 0:
        m1 = avg_conf(passed)
        m0 = avg_conf(failed)
        n = len(all_confs)
        mean_all = sum(all_confs) / n
        s = math.sqrt(sum((c - mean_all) ** 2 for c in all_confs) / max(n - 1, 1))
        if s > 0:
            n1 = len([t for t in passed if t.get("confidence", 0) > 0])
            n0 = len([t for t in failed if t.get("confidence", 0) > 0])
            r_pb = (m1 - m0) / s * math.sqrt(n1 * n0 / (n * n))
            stats["point_biserial_r"] = round(r_pb, 4)

    return stats


def format_calibration_report(benchmark: str, stats: Dict) -> str:
    """Format a human-readable calibration report."""
    lines = []
    lines.append(f"\n{'=' * 65}")
    lines.append(f"  CONFIDENCE CALIBRATION: {benchmark.upper()}")
    lines.append(f"{'=' * 65}")

    if "error" in stats:
        lines.append(f"  {stats['error']}")
        return "\n".join(lines)

    lines.append(f"  Total tasks:     {stats['total_tasks']}")
    lines.append(f"  Passed:          {stats['passed']} ({stats['pass_rate']*100:.1f}%)")
    lines.append(f"  Failed:          {stats['failed']}")
    lines.append("")
    lines.append(f"  Avg confidence (passed):  {stats['avg_confidence_passed']:.4f} +/- {stats['std_confidence_passed']:.4f}")
    lines.append(f"  Avg confidence (failed):  {stats['avg_confidence_failed']:.4f} +/- {stats['std_confidence_failed']:.4f}")
    lines.append(f"  Confidence gap:           {stats['confidence_gap']:.4f}")

    if "point_biserial_r" in stats:
        r = stats["point_biserial_r"]
        strength = "strong" if abs(r) > 0.5 else "moderate" if abs(r) > 0.3 else "weak"
        lines.append(f"  Point-biserial r:         {r:.4f} ({strength} correlation)")

    curve = stats.get("calibration_curve", {})
    if curve:
        lines.append("")
        lines.append(f"  {'Confidence':>12s}  {'Tasks':>6s}  {'Passed':>7s}  {'Actual':>8s}  {'Bar'}")
        lines.append(f"  {'-'*12}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*20}")
        for bucket, data in curve.items():
            bar = "#" * int(data["actual_pass_rate"] * 20)
            lines.append(
                f"  {bucket:>12s}  {data['total']:>6d}  {data['passed']:>7d}  "
                f"{data['actual_pass_rate']*100:>7.1f}%  {bar}"
            )

    lines.append("")
    lines.append("  Interpretation:")
    if stats.get("confidence_gap", 0) > 0.1:
        lines.append("    GOOD: Higher confidence on passing tasks (gap > 0.1)")
    elif stats.get("confidence_gap", 0) > 0:
        lines.append("    FAIR: Slightly higher confidence on passing tasks")
    else:
        lines.append("    POOR: Confidence does not discriminate pass/fail")

    lines.append(f"{'=' * 65}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="CD-AOR Confidence Calibration Analysis")
    parser.add_argument("--results-dir", type=Path, default=Path("./benchmark_results"))
    parser.add_argument("--benchmark", default=None, help="Specific benchmark (default: all found)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.results_dir.exists():
        print(f"Results directory not found: {args.results_dir}")
        print("Run benchmarks first with --run-cdaor flag")
        return

    benchmarks = [args.benchmark] if args.benchmark else ["humaneval", "mbpp", "swebench", "terminalbench"]

    print("\nCD-AOR Confidence Calibration Report")

    all_stats = {}
    for benchmark in benchmarks:
        tasks = load_per_task_results(args.results_dir, benchmark)
        if not tasks:
            continue
        stats = compute_calibration_stats(tasks)
        all_stats[benchmark] = stats
        print(format_calibration_report(benchmark, stats))

    if not all_stats:
        print("\nNo benchmark results found. Run benchmarks first:")
        print("  python -m benchmarks.runner --benchmark humaneval --data-dir ./data/benchmarks --run-cdaor")

    # Save calibration data
    if all_stats:
        output = args.results_dir / "calibration_analysis.json"
        output.write_text(json.dumps(all_stats, indent=2))
        print(f"\nCalibration data saved to: {output}")


if __name__ == "__main__":
    main()
