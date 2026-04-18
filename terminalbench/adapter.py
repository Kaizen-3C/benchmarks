"""TerminalBench-2 adapter for CD-AOR benchmarking.

TerminalBench-2 is a benchmark of terminal-based system administration tasks
requiring agents to navigate command-line interfaces and execute complex
multi-step workflows. Each task specifies a Docker environment, initial setup
commands, and an evaluation script to determine pass/fail.

Published baselines (pass@1):
  - Meta-Harness (Opus 4.6):  76.4%
  - Meta-Harness (Haiku 4.5): 37.6%

Dataset:
    Contact Meta-Harness authors (Lee et al., arXiv 2603.28052v1)

Full evaluation requires Docker environment matching the task's docker_image.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base_adapter import BenchmarkAdapter, BenchmarkTask, TaskResult

logger = logging.getLogger(__name__)


class TerminalBenchAdapter(BenchmarkAdapter):
    """Adapter for TerminalBench-2 — terminal-based system administration tasks."""

    def name(self) -> str:
        return "terminalbench"

    # ------------------------------------------------------------------
    # Task loading
    # ------------------------------------------------------------------

    def load_tasks(self) -> List[BenchmarkTask]:
        """Load tasks from terminalbench2.jsonl.

        Each line is a JSON object with the TerminalBench-2 schema:
            task_id, description, docker_image, eval_script,
            setup_commands (optional), ...

        Raises:
            FileNotFoundError: When the data file is absent, with
                instructions to contact the Meta-Harness authors.
        """
        data_file = self.data_dir / "terminalbench2.jsonl"
        if not data_file.exists():
            raise FileNotFoundError(
                f"TerminalBench-2 data file not found: {data_file}\n"
                "Download from Meta-Harness authors (Lee et al., arXiv 2603.28052v1):\n"
                "  https://github.com/meta-llm/meta-harness\n"
                "Then copy terminalbench2.jsonl to: " + str(self.data_dir)
            )

        tasks: List[BenchmarkTask] = []
        with data_file.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning("Skipping malformed JSON on line %d: %s", lineno, exc)
                    continue

                task = self._record_to_task(record)
                tasks.append(task)

        logger.info("Loaded %d TerminalBench-2 tasks from %s", len(tasks), data_file)
        return tasks

    def _record_to_task(self, record: Dict[str, Any]) -> BenchmarkTask:
        """Convert a raw JSONL record to a BenchmarkTask."""
        task_id: str = record.get("task_id", "")
        description: str = record.get("description", "")
        docker_image: str = record.get("docker_image", "")
        eval_script: str = record.get("eval_script", "")
        setup_commands: List[str] = record.get("setup_commands", [])

        return BenchmarkTask(
            task_id=task_id,
            prompt=description,
            test_code=eval_script,
            entry_point="",
            metadata={
                "docker_image": docker_image,
                "setup_commands": setup_commands,
            },
        )

    # ------------------------------------------------------------------
    # Workspace setup
    # ------------------------------------------------------------------

    def task_to_workspace(self, task: BenchmarkTask, workspace_path: Path) -> None:
        """Populate a workspace directory with the task artefacts.

        Creates:
            task.md           — the task description / problem statement
            eval.sh           — the evaluation script
            metadata.json     — docker_image, setup_commands
        """
        workspace_path.mkdir(parents=True, exist_ok=True)

        (workspace_path / "task.md").write_text(task.prompt, encoding="utf-8")
        (workspace_path / "eval.sh").write_text(task.test_code, encoding="utf-8")

        meta = {
            "task_id": task.task_id,
            "docker_image": task.metadata.get("docker_image", ""),
            "setup_commands": task.metadata.get("setup_commands", []),
        }
        (workspace_path / "metadata.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

        logger.debug("Workspace ready: %s", workspace_path)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate_output(self, task: BenchmarkTask, workspace_path: Path) -> TaskResult:
        """Evaluate generated output for a TerminalBench-2 task.

        Full pass/fail evaluation runs each task's Docker image via
        ``scripts/score_terminalbench_docker.sh`` and records the outcome
        in ``<run_dir>/harness_results.json``. This method inspects that
        file (if present) to determine pass/fail; otherwise it falls back
        to reporting that Docker evaluation is required.

        The generated solution (if found) is stored in ``generated_code``
        so downstream tooling / scoring can submit it for Docker evaluation.
        """
        solution_content, solution_source = self._find_generated_output(workspace_path)

        if solution_content is None:
            return TaskResult(
                task_id=task.task_id,
                passed=False,
                generated_code="",
                error=(
                    "No solution found in workspace. "
                    "Expected solution.sh, commands.sh, or any *.sh file. "
                    "Full evaluation requires running eval.sh in Docker container: "
                    f"docker run {task.metadata.get('docker_image', 'IMAGE')} /bin/bash eval.sh"
                ),
            )

        logger.info(
            "Found solution for %s at %s (%d bytes)",
            task.task_id,
            solution_source,
            len(solution_content),
        )

        # Look up harness result if the scoring script has already run.
        # Convention: workspace_path = benchmark_workspaces/<run_name>/terminalbench/<task_id>
        # Harness output:             benchmark_results/<run_name>/harness_results.json
        harness = self._load_harness_results(workspace_path)
        if harness is not None:
            resolved_ids = set(harness.get("resolved", []))
            error_ids = set(harness.get("errors", []))
            passed = task.task_id in resolved_ids
            if task.task_id in error_ids:
                err_msg = "Harness error during Docker evaluation"
            elif not passed:
                err_msg = "Task unresolved (Docker evaluation)"
            else:
                err_msg = None
            return TaskResult(
                task_id=task.task_id,
                passed=passed,
                generated_code=solution_content,
                error=err_msg,
            )

        return TaskResult(
            task_id=task.task_id,
            passed=False,  # Cannot determine pass/fail without Docker environment
            generated_code=solution_content,
            error=(
                "Solution found but full evaluation requires Docker environment. "
                f"Run: bash scripts/score_terminalbench_docker.sh --run-dir <run_dir>  "
                f"(docker image: {task.metadata.get('docker_image', 'IMAGE')})"
            ),
        )

    @staticmethod
    def _load_harness_results(workspace_path: Path) -> Optional[Dict[str, Any]]:
        """Walk up from a task workspace to locate harness_results.json.

        Search order (first hit wins):
          1. workspace_path / "harness_results.json"          (same dir)
          2. workspace_path.parent / "harness_results.json"   (terminalbench/)
          3. Map benchmark_workspaces/<run>/terminalbench/<id>/
                -> benchmark_results/<run>/harness_results.json
        """
        try:
            candidates = [
                workspace_path / "harness_results.json",
                workspace_path.parent / "harness_results.json",
            ]
            parts = workspace_path.resolve().parts
            if "benchmark_workspaces" in parts:
                idx = parts.index("benchmark_workspaces")
                if idx + 1 < len(parts):
                    run_name = parts[idx + 1]
                    repo_root = Path(*parts[: idx])
                    candidates.append(
                        repo_root / "benchmark_results" / run_name / "harness_results.json"
                    )
            for cand in candidates:
                if cand.is_file():
                    return json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Could not load harness_results.json: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # Shell scripts written by task_to_workspace that must not be mistaken for
    # generated agent solutions.
    _SCAFFOLD_FILES: frozenset[str] = frozenset({"eval.sh", "run-tests.sh"})

    def _find_generated_output(
        self, workspace_path: Path
    ) -> tuple[Optional[str], Optional[str]]:
        """Search workspace_path for a generated solution file.

        Search order:
            1. solution.sh
            2. commands.sh
            3. Any *.sh file that is NOT a scaffold file (eval.sh, run-tests.sh)

        Returns:
            (solution_content, relative_filename) or (None, None) if not found.
        """
        if not workspace_path.exists():
            return None, None

        priority_names = ["solution.sh", "commands.sh"]
        for name in priority_names:
            candidate = workspace_path / name
            if candidate.exists() and candidate.stat().st_size > 0:
                return candidate.read_text(encoding="utf-8", errors="replace"), name

        matches = sorted(workspace_path.glob("*.sh"))
        for match in matches:
            if match.name in self._SCAFFOLD_FILES:
                continue
            if match.stat().st_size > 0:
                return (
                    match.read_text(encoding="utf-8", errors="replace"),
                    match.name,
                )

        return None, None
