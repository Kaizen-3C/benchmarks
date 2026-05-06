"""Aider single-cell wrapper for one commit0 library — OpenAI GPT-5.4.

Day 14 deliverable. Mirrors aider_sonnet.py with a different model_id and key.

Run:
  python baselines/aider/aider_openai.py <repo_name>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from _aider_runner import WORKSPACE, load_dotenv, run_aider_on_lib

MODEL_ID = "openai/gpt-5.4"
RESULTS_DIR = WORKSPACE / "baselines" / "results"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("lib")
    args = parser.parse_args()

    load_dotenv(WORKSPACE / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    repo_dir = WORKSPACE / "repos" / args.lib
    if not repo_dir.exists():
        print(f"ERROR: repo not found at {repo_dir}", file=sys.stderr)
        return 2

    out_path = RESULTS_DIR / f"{args.lib}_aider_openai.json"
    result = run_aider_on_lib(args.lib, repo_dir, MODEL_ID, out_path)

    print(f"\nWrote {out_path}")
    print(f"  passed={result['final_counts']['passed']} "
          f"failed={result['final_counts']['failed']} "
          f"errors={result['final_counts']['errors']} "
          f"cost=${result['totals']['cost_usd']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
