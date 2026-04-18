"""MBPP (Mostly Basic Python Problems) benchmark adapter for CD-AOR."""
from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from ..base_adapter import BenchmarkAdapter, BenchmarkTask, TaskResult

logger = logging.getLogger(__name__)


class MBPPAdapter(BenchmarkAdapter):
    """Adapter for Google MBPP benchmark (427 sanitized Python problems).

    Published baselines:
        Reflexion: 77.1% pass@1
        LATS:      ~81%  pass@1
    """

    def name(self) -> str:
        return "mbpp"

    def load_tasks(self) -> List[BenchmarkTask]:
        """Load tasks from mbpp_sanitized.jsonl."""
        path = self.data_dir / "mbpp_sanitized.jsonl"
        if not path.exists():
            raise FileNotFoundError(
                f"mbpp_sanitized.jsonl not found at {path}.\n"
                "Download from: https://github.com/google-research/google-research/tree/master/mbpp\n"
                "  Or via HuggingFace: https://huggingface.co/datasets/mbpp"
            )

        tasks = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            test_list = d.get("test_list", [])
            # Support both "text" (original Google dataset) and "prompt" (HuggingFace dataset)
            prompt_text = d.get("prompt") or d.get("text")
            if not prompt_text:
                raise KeyError(f"Task {d.get('task_id')} missing 'prompt' or 'text' field")
            # Extract the real function name from the canonical solution so the
            # orchestrator can tell the Write agent what to implement.  MBPP tasks
            # do not carry an explicit entry_point field, but the canonical code
            # always starts with a `def <name>(` statement.  Fall back to the
            # first function called in the test assertions if canonical is absent.
            canonical = d.get("code", "")
            entry_point = ""
            if canonical:
                m = re.search(r'def\s+([A-Za-z_]\w*)\s*\(', canonical)
                if m:
                    entry_point = m.group(1)
            if not entry_point and test_list:
                m = re.search(r'assert\s+([A-Za-z_]\w*)\s*\(', test_list[0])
                if m:
                    entry_point = m.group(1)

            tasks.append(
                BenchmarkTask(
                    task_id=str(d["task_id"]),
                    prompt=prompt_text,
                    test_code="\n".join(test_list),
                    entry_point=entry_point,
                    canonical_solution=canonical or None,
                )
            )
        logger.info("Loaded %d MBPP tasks", len(tasks))
        return tasks

    def task_to_workspace(self, task: BenchmarkTask, workspace_path: Path) -> None:
        """Set up workspace with prompt and test files."""
        workspace_path.mkdir(parents=True, exist_ok=True)
        (workspace_path / "prompt.txt").write_text(task.prompt, encoding="utf-8")
        (workspace_path / "tests.py").write_text(task.test_code, encoding="utf-8")

    def evaluate_output(self, task: BenchmarkTask, workspace_path: Path) -> TaskResult:
        """Evaluate generated code against MBPP assert-based tests."""
        code = self._find_generated_code(workspace_path)
        if code is None:
            return TaskResult(
                task_id=task.task_id,
                passed=False,
                generated_code="",
                error="No generated code found in workspace",
            )

        # MBPP tests are assert statements — concatenate code + asserts
        test_script = f"{code}\n\n{task.test_code}\n"

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

    def _find_generated_code(self, workspace_path: Path) -> Optional[str]:
        """Find the generated code in the workspace."""
        solution = workspace_path / "solution.py"
        if solution.exists():
            return solution.read_text(encoding="utf-8")

        skip = {"prompt.txt", "tests.py", "__init__.py"}
        for py_file in sorted(workspace_path.glob("*.py")):
            if py_file.name not in skip:
                return py_file.read_text(encoding="utf-8")

        return None
