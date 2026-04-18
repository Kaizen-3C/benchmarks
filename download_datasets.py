"""
Download benchmark datasets for CD-AOR evaluation.

Usage:
    python -m benchmarks.download_datasets --dataset humaneval --output-dir ./data/benchmarks
    python -m benchmarks.download_datasets --dataset all --output-dir ./data/benchmarks

Supported datasets:
    humaneval      - OpenAI HumanEval (164 Python problems)
    mbpp           - Google MBPP sanitized (427 Python problems)
    swebench       - SWE-bench Lite (300 GitHub issues)
    all            - Download all available datasets

Note: TerminalBench is managed separately via scripts/download_terminalbench.py
which clones github.com/laude-institute/terminal-bench and converts it to
data/terminalbench2.jsonl (241 tasks, directory-tree → JSONL conversion).
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DATASETS = {
    "humaneval": {
        "description": "OpenAI HumanEval (164 Python function-completion problems)",
        "filename": "HumanEval.jsonl",
        "source": "https://github.com/openai/human-eval",
        "instructions": [
            "git clone https://github.com/openai/human-eval /tmp/human-eval",
            "cp /tmp/human-eval/data/HumanEval.jsonl {output_dir}/",
        ],
    },
    "mbpp": {
        "description": "Google MBPP sanitized (427 Python problems)",
        "filename": "mbpp_sanitized.jsonl",
        "source": "https://github.com/google-research/google-research/tree/master/mbpp",
        "instructions": [
            "# Option 1: From HuggingFace",
            "pip install datasets",
            'python -c "from datasets import load_dataset; ds = load_dataset(\'mbpp\', \'sanitized\', split=\'test\'); [open(\'{output_dir}/mbpp_sanitized.jsonl\', \'a\').write(json.dumps(dict(task_id=r[\'task_id\'], text=r[\'text\'], code=r[\'code\'], test_list=r[\'test_list\'])) + \'\\n\') for r in ds]"',
            "# Option 2: From Google Research repo",
            "git clone https://github.com/google-research/google-research /tmp/google-research",
            "cp /tmp/google-research/mbpp/mbpp.jsonl {output_dir}/mbpp_sanitized.jsonl",
        ],
    },
    "swebench": {
        "description": "SWE-bench Lite (300 real GitHub issues)",
        "filename": "swe-bench-lite.jsonl",
        "source": "https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite",
        "instructions": [
            "pip install datasets",
            'python -c "from datasets import load_dataset; ds = load_dataset(\'princeton-nlp/SWE-bench_Lite\', split=\'test\'); [open(\'{output_dir}/swe-bench-lite.jsonl\', \'a\').write(json.dumps(dict(instance_id=r[\'instance_id\'], repo=r[\'repo\'], base_commit=r[\'base_commit\'], problem_statement=r[\'problem_statement\'], hints_text=r[\'hints_text\'], test_patch=r[\'test_patch\'], patch=r[\'patch\'], version=r.get(\'version\', \'\'))) + \'\\n\') for r in ds]"',
        ],
    },
}


def check_dataset(name: str, output_dir: Path) -> bool:
    """Check if a dataset file already exists."""
    info = DATASETS[name]
    path = output_dir / info["filename"]
    if path.exists():
        lines = len(path.read_text().splitlines())
        logger.info("[%s] Already exists: %s (%d entries)", name, path, lines)
        return True
    return False


def print_instructions(name: str, output_dir: Path) -> None:
    """Print download instructions for a dataset."""
    info = DATASETS[name]
    print(f"\n{'=' * 60}")
    print(f"  {name.upper()}: {info['description']}")
    print(f"  Source: {info['source']}")
    print(f"  Target: {output_dir / info['filename']}")
    print(f"{'=' * 60}")
    print("\n  Download commands:\n")
    for cmd in info["instructions"]:
        formatted = cmd.format(output_dir=output_dir)
        print(f"    {formatted}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Download benchmark datasets for CD-AOR")
    parser.add_argument(
        "--dataset",
        required=True,
        choices=list(DATASETS.keys()) + ["all"],
        help="Dataset to download (or 'all')",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./data/benchmarks"),
        help="Directory to save dataset files",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    datasets = list(DATASETS.keys()) if args.dataset == "all" else [args.dataset]

    print("\nCD-AOR Benchmark Dataset Setup")
    print("=" * 60)

    for name in datasets:
        if check_dataset(name, args.output_dir):
            continue
        print_instructions(name, args.output_dir)

    # Summary
    print("\nStatus Summary:")
    for name in datasets:
        info = DATASETS[name]
        path = args.output_dir / info["filename"]
        status = "READY" if path.exists() else "MISSING"
        print(f"  [{status:7s}] {name:15s} -> {path}")
    print()


if __name__ == "__main__":
    main()
