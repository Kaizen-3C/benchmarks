"""HumanEval benchmark adapter for CD-AOR."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from ..base_adapter import BenchmarkAdapter, BenchmarkTask, TaskResult

logger = logging.getLogger(__name__)


class HumanEvalAdapter(BenchmarkAdapter):
    """Adapter for OpenAI HumanEval benchmark (164 Python problems).

    Published baselines:
        GPT-4 (single-shot): 67.0% pass@1
        MetaGPT:             87.7% pass@1
        Reflexion:           91.0% pass@1
        LATS:                94.4% pass@1
    """

    def name(self) -> str:
        return "humaneval"

    def load_tasks(self) -> List[BenchmarkTask]:
        """Load tasks from HumanEval.jsonl."""
        path = self.data_dir / "HumanEval.jsonl"
        if not path.exists():
            raise FileNotFoundError(
                f"HumanEval.jsonl not found at {path}.\n"
                "Download from: https://github.com/openai/human-eval\n"
                f"  git clone https://github.com/openai/human-eval && "
                f"cp human-eval/data/HumanEval.jsonl {self.data_dir}/"
            )

        tasks = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            tasks.append(
                BenchmarkTask(
                    task_id=d["task_id"],
                    prompt=d["prompt"],
                    test_code=d["test"],
                    entry_point=d["entry_point"],
                    canonical_solution=d.get("canonical_solution"),
                )
            )
        logger.info("Loaded %d HumanEval tasks", len(tasks))
        return tasks

    def task_to_workspace(self, task: BenchmarkTask, workspace_path: Path) -> None:
        """Set up workspace with prompt and test files."""
        workspace_path.mkdir(parents=True, exist_ok=True)
        # Use .txt so write agents don't mistake the prompt for a solution file.
        (workspace_path / "prompt.txt").write_text(task.prompt, encoding="utf-8")
        (workspace_path / "tests.py").write_text(task.test_code, encoding="utf-8")

    def evaluate_output(self, task: BenchmarkTask, workspace_path: Path) -> TaskResult:
        """Evaluate generated code against HumanEval test cases."""
        code = self._find_generated_code(task, workspace_path)
        if code is None:
            return TaskResult(
                task_id=task.task_id,
                passed=False,
                generated_code="",
                error="No generated code found in workspace",
            )

        # Build test script following the standard HumanEval evaluation protocol:
        #   prompt_context + generated_code + test_harness + check() call
        #
        # Prepending the prompt serves two purposes:
        #   1. Helper functions defined in the prompt (e.g. encode_cyclic for
        #      HumanEval/38) are available in scope for both the solution and
        #      the test harness.
        #   2. Python's duplicate-def rule means the complete implementation in
        #      `code` overrides any partial stub at the end of the prompt, so
        #      there is no conflict even when the stub has a docstring body.
        prompt_context = task.prompt or ""
        test_script = (
            f"{prompt_context}\n\n"
            f"{code}\n\n"
            f"{task.test_code}\n\n"
            f"check({task.entry_point})\n"
        )

        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(test_script)
                tmp_path = Path(tmp.name)

            result = subprocess.run(
                [sys.executable, str(tmp_path)],
                capture_output=True,
                timeout=30,
                text=True,
            )
            return TaskResult(
                task_id=task.task_id,
                passed=result.returncode == 0,
                generated_code=code,
                error=result.stderr[:500] if result.returncode != 0 else None,
            )
        except subprocess.TimeoutExpired:
            return TaskResult(
                task_id=task.task_id,
                passed=False,
                generated_code=code,
                error="Timeout (30s)",
            )
        except Exception as e:
            return TaskResult(
                task_id=task.task_id,
                passed=False,
                generated_code=code,
                error=str(e)[:500],
            )
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

    def _find_generated_code(
        self, task: BenchmarkTask, workspace_path: Path
    ) -> Optional[str]:
        """Find the generated code in the workspace."""
        # Prefer solution.py — CD-AOR writes this via pre_planned_files.
        solution = workspace_path / "solution.py"
        if solution.exists():
            return solution.read_text(encoding="utf-8")

        # Any top-level .py file that isn't prompt/tests/init
        skip = {"prompt.py", "prompt.txt", "tests.py", "__init__.py"}
        for py_file in sorted(workspace_path.glob("*.py")):
            if py_file.name not in skip:
                return py_file.read_text(encoding="utf-8")

        return None
