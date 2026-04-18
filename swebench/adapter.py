"""SWE-bench Lite adapter for CD-AOR benchmarking.

SWE-bench Lite is a curated subset of 300 real GitHub issues paired with
verified resolving patches. Unlike HumanEval/MBPP (function-completion),
each task requires understanding an issue description and producing a valid
unified diff patch that makes failing repository tests pass.

Published baselines (pass@1, resolved %):
  - SWE-agent (original):  12.5%
  - AutoCodeRover:         22.7%
  - CodeR:                 28.3%
  - Latest SOTA:           ~33%

Dataset:
    huggingface-cli download princeton-nlp/SWE-bench_Lite --repo-type dataset

Full evaluation requires the SWE-bench harness:
    pip install swebench
    python -m swebench.harness.run_evaluation \\
        --predictions_path predictions.json \\
        --swe_bench_tasks swe-bench-lite.jsonl \\
        --log_dir ./logs
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..base_adapter import BenchmarkAdapter, BenchmarkTask, TaskResult

logger = logging.getLogger(__name__)

try:
    import swebench  # noqa: F401
    HAS_SWEBENCH = True
except ImportError:
    HAS_SWEBENCH = False


class SWEBenchAdapter(BenchmarkAdapter):
    """Adapter for SWE-bench Lite — real GitHub issue resolution tasks."""

    def name(self) -> str:
        return "swebench"

    # ------------------------------------------------------------------
    # Task loading
    # ------------------------------------------------------------------

    def load_tasks(self) -> List[BenchmarkTask]:
        """Load tasks from swe-bench-lite.jsonl.

        Each line is a JSON object with the SWE-bench schema:
            instance_id, repo, base_commit, problem_statement,
            hints_text, test_patch, patch, version, ...

        Raises:
            FileNotFoundError: When the data file is absent, with
                instructions to fetch it from HuggingFace.
        """
        data_file = self.data_dir / "swe-bench-lite.jsonl"
        if not data_file.exists():
            raise FileNotFoundError(
                f"SWE-bench Lite data file not found: {data_file}\n"
                "Download with:\n"
                "  huggingface-cli download princeton-nlp/SWE-bench_Lite "
                "--repo-type dataset\n"
                "Then copy swe-bench-lite.jsonl to: " + str(self.data_dir)
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

        logger.info("Loaded %d SWE-bench Lite tasks from %s", len(tasks), data_file)
        return tasks

    def _record_to_task(self, record: Dict[str, Any]) -> BenchmarkTask:
        """Convert a raw JSONL record to a BenchmarkTask."""
        instance_id: str = record.get("instance_id", "")
        repo: str = record.get("repo", "")
        base_commit: str = record.get("base_commit", "")
        problem_statement: str = record.get("problem_statement", "")
        hints_text: str = record.get("hints_text", "")
        test_patch: str = record.get("test_patch", "")
        patch: str = record.get("patch", "")
        version: str = record.get("version", "")

        return BenchmarkTask(
            task_id=instance_id,
            prompt=problem_statement,
            test_code=test_patch,
            entry_point=repo,
            canonical_solution=patch,
            metadata={
                "repo": repo,
                "base_commit": base_commit,
                "hints": hints_text,
                "version": version,
            },
        )

    # ------------------------------------------------------------------
    # Workspace setup
    # ------------------------------------------------------------------

    def task_to_workspace(self, task: BenchmarkTask, workspace_path: Path) -> None:
        """Populate a workspace directory with the task artefacts.

        Creates:
            issue.md          — the GitHub issue / problem statement
            test_patch.diff   — the test patch that validates the fix
            metadata.json     — repo, base_commit, hints
        """
        workspace_path.mkdir(parents=True, exist_ok=True)

        (workspace_path / "issue.md").write_text(task.prompt, encoding="utf-8")
        (workspace_path / "test_patch.diff").write_text(task.test_code, encoding="utf-8")

        meta = {
            "instance_id": task.task_id,
            "repo": task.metadata.get("repo", ""),
            "base_commit": task.metadata.get("base_commit", ""),
            "hints": task.metadata.get("hints", ""),
            "version": task.metadata.get("version", ""),
            # Signals to the Write agent that this task expects a unified diff
            # saved as solution.patch, not a Python file (solution.py). Detected
            # by write_agent._detect_swebench_workspace(). See Fix 1 in
            # STRATEGIC_ROADMAP Sprint 3 SWE-bench pilot notes.
            "output_format": "unified_diff",
            "target_patch_filename": "solution.patch",
            # Path (workspace-relative) where the source repo is checked out.
            # Gap A+B write_agent reads files from here to avoid hallucinating
            # line numbers. Example: workspace/repo/src/flask/blueprints.py
            "repo_dir_relative": "repo",
        }
        (workspace_path / "metadata.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

        # Clone the target repo at base_commit so agents can read real source.
        # Disk note: repos vary from ~10 MB (Flask) to ~500 MB (Django). A
        # 10-task pilot run uses a few GB total. benchmark_workspaces/ is
        # already covered by .gitignore so checked-out repos are never staged.
        repo_dir = workspace_path / "repo"
        if not repo_dir.exists():
            self._checkout_repo_at_commit(
                repo_slug=task.metadata.get("repo", ""),
                base_commit=task.metadata.get("base_commit", ""),
                target_dir=repo_dir,
            )
        else:
            logger.debug("Repo dir already exists, skipping clone: %s", repo_dir)

        logger.debug("Workspace ready: %s", workspace_path)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate_output(self, task: BenchmarkTask, workspace_path: Path) -> TaskResult:
        """Evaluate generated output for a SWE-bench task.

        When the ``swebench`` package is installed, this method runs the full
        SWE-bench harness via subprocess and returns a TaskResult whose
        ``passed`` flag reflects whether the patch resolved the issue.

        When ``swebench`` is *not* installed, this method falls back to a
        best-effort local check: it locates any generated patch and returns
        ``passed=False`` with instructions to run the full harness.

        The generated patch (if found) is always stored in ``generated_code``
        so downstream tooling can inspect or re-submit it.

        Full evaluation (manual):
            pip install swebench
            python -m swebench.harness.run_evaluation \\
                --predictions_path predictions.json \\
                --swe_bench_tasks swe-bench-lite.jsonl \\
                --log_dir ./logs
        """
        patch_content, patch_source = self._find_generated_patch(workspace_path)

        if patch_content is None:
            return TaskResult(
                task_id=task.task_id,
                passed=False,
                generated_code="",
                error=(
                    "No patch file found in workspace. "
                    "Expected solution.patch, solution.diff, or any *.patch / *.diff file. "
                    "Full evaluation requires: "
                    "pip install swebench && "
                    "python -m swebench.harness.run_evaluation"
                ),
            )

        logger.info(
            "Found patch for %s at %s (%d bytes)",
            task.task_id,
            patch_source,
            len(patch_content),
        )

        if not HAS_SWEBENCH:
            return TaskResult(
                task_id=task.task_id,
                passed=False,  # Cannot determine pass/fail without harness
                generated_code=patch_content,
                error=(
                    "Patch found but full evaluation requires the SWE-bench harness. "
                    "Run: pip install swebench && "
                    "python -m swebench.harness.run_evaluation"
                ),
            )

        # swebench is available — run the real harness.
        passed, eval_error = self._run_swebench_eval(task, patch_content, workspace_path)
        return TaskResult(
            task_id=task.task_id,
            passed=passed,
            generated_code=patch_content,
            error=eval_error,
        )

    # ------------------------------------------------------------------
    # SWE-bench harness integration
    # ------------------------------------------------------------------

    def _run_swebench_eval(
        self,
        task: BenchmarkTask,
        patch_content: str,
        workspace_path: Path,
    ) -> Tuple[bool, Optional[str]]:
        """Run the SWE-bench evaluation harness for a single prediction.

        Writes a predictions JSONL file, invokes
        ``python -m swebench.harness.run_evaluation`` via subprocess, then
        parses the resulting log directory to determine pass/fail.

        Args:
            task: The benchmark task being evaluated.
            patch_content: The raw unified-diff patch string.
            workspace_path: The task workspace directory (used for logs and
                the testbed checkout).

        Returns:
            ``(passed, error_message)`` where *passed* is ``True`` when the
            harness confirms the patch resolves the issue, and *error_message*
            is ``None`` on success or a human-readable string on failure.
        """
        data_file = self.data_dir / "swe-bench-lite.jsonl"
        log_dir = workspace_path / "eval_logs"
        testbed_dir = workspace_path / "testbed"
        log_dir.mkdir(parents=True, exist_ok=True)
        testbed_dir.mkdir(parents=True, exist_ok=True)

        # --- Write the predictions JSONL file expected by the harness -------
        prediction = {
            "instance_id": task.task_id,
            "model_patch": patch_content,
            "model_name_or_path": "CD-AOR",
        }

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".jsonl",
                prefix=f"swebench_pred_{task.task_id}_",
                delete=False,
                encoding="utf-8",
            ) as pred_fh:
                pred_fh.write(json.dumps(prediction) + "\n")
                predictions_file = Path(pred_fh.name)
        except OSError as exc:
            return False, f"Failed to write predictions file: {exc}"

        # --- Invoke the SWE-bench harness ------------------------------------
        cmd = [
            "python",
            "-m",
            "swebench.harness.run_evaluation",
            "--predictions_path",
            str(predictions_file),
            "--swe_bench_tasks",
            str(data_file),
            "--log_dir",
            str(log_dir),
            "--testbed",
            str(testbed_dir),
            "--timeout",
            "300",
        ]

        logger.info("Running SWE-bench harness for %s: %s", task.task_id, " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=360,  # slightly above the harness --timeout
            )
        except subprocess.TimeoutExpired:
            return False, "SWE-bench harness timed out after 360 s"
        except FileNotFoundError:
            return False, "Could not launch 'python'; ensure it is on PATH"
        except OSError as exc:
            return False, f"Subprocess error: {exc}"
        finally:
            # Clean up the temporary predictions file
            try:
                predictions_file.unlink(missing_ok=True)
            except OSError:
                pass

        if result.returncode != 0:
            stderr_tail = result.stderr[-1000:] if result.stderr else "(no stderr)"
            return False, (
                f"SWE-bench harness exited with code {result.returncode}. "
                f"stderr tail: {stderr_tail}"
            )

        # --- Parse the evaluation results ------------------------------------
        passed, parse_error = self._parse_eval_logs(task.task_id, log_dir)
        if parse_error:
            logger.warning(
                "Could not parse harness output for %s: %s", task.task_id, parse_error
            )
            return False, parse_error

        return passed, None

    def _parse_eval_logs(
        self, instance_id: str, log_dir: Path
    ) -> Tuple[bool, Optional[str]]:
        """Determine pass/fail by inspecting the harness log directory.

        The SWE-bench harness writes per-instance JSON result files whose
        names contain the instance_id (e.g.
        ``CD-AOR.<instance_id>.eval.log`` or a ``results.json`` summary).
        This method tries several common patterns in order:

        1. A ``results.json`` / ``results.jsonl`` summary at the top of
           *log_dir* whose ``resolved`` list contains *instance_id*.
        2. Any per-instance ``*.json`` file containing a ``"resolved"``
           boolean field.
        3. Any per-instance ``*.eval.log`` text file that contains the
           string ``"RESOLVED"`` (harness stdout convention).

        Returns:
            ``(passed, error_message)``
        """
        if not log_dir.exists():
            return False, f"Log directory does not exist: {log_dir}"

        # Pattern 1 — summary results file
        for summary_name in ("results.json", "results.jsonl"):
            summary_path = log_dir / summary_name
            if summary_path.exists():
                try:
                    text = summary_path.read_text(encoding="utf-8")
                    # results.jsonl: one JSON object per line
                    for line in text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        resolved = data.get("resolved", [])
                        if isinstance(resolved, list) and instance_id in resolved:
                            return True, None
                        # Some harness versions use a mapping
                        if isinstance(resolved, dict) and resolved.get(instance_id):
                            return True, None
                    # Found the file but instance not in resolved list
                    return False, None
                except OSError as exc:
                    logger.debug("Could not read %s: %s", summary_path, exc)

        # Pattern 2 — per-instance JSON file
        for json_path in log_dir.glob(f"*{instance_id}*.json"):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                resolved_val = data.get("resolved")
                if isinstance(resolved_val, bool):
                    return resolved_val, None
                if isinstance(resolved_val, list) and instance_id in resolved_val:
                    return True, None
            except (OSError, json.JSONDecodeError) as exc:
                logger.debug("Could not parse %s: %s", json_path, exc)

        # Pattern 3 — plain-text eval log
        for log_path in log_dir.glob(f"*{instance_id}*.eval.log"):
            try:
                content = log_path.read_text(encoding="utf-8", errors="replace")
                if "RESOLVED" in content:
                    return True, None
                if "FAILED" in content or "NOT_RESOLVED" in content:
                    return False, None
            except OSError as exc:
                logger.debug("Could not read %s: %s", log_path, exc)

        return False, (
            f"Could not find evaluation result for '{instance_id}' in {log_dir}. "
            "The harness may have produced output in an unexpected format."
        )

    # ------------------------------------------------------------------
    # Repo checkout helpers (Gap C)
    # ------------------------------------------------------------------

    def _checkout_repo_at_commit(
        self,
        repo_slug: str,  # e.g. "pallets/flask"
        base_commit: str,
        target_dir: Path,
    ) -> None:
        """Populate target_dir with the repo contents at the given commit.

        Uses shallow fetch to minimise download size and time.  Falls back to
        a full clone + checkout if the shallow fetch is rejected by the server.

        Disk usage note: repos range from ~10 MB (Flask) to ~500 MB (Django).
        A 10-task pilot run may consume a few GB.  Re-running with --resume
        skips the clone when repo/ already exists (idempotent).

        Args:
            repo_slug:   GitHub slug, e.g. ``"pallets/flask"``.
            base_commit: Full 40-char (or abbreviated) SHA to check out.
            target_dir:  Directory to populate.  Created if absent.
        """
        if not repo_slug or not base_commit:
            logger.warning(
                "Cannot checkout repo: repo=%r commit=%r — skipping",
                repo_slug,
                base_commit,
            )
            return

        target_dir.mkdir(parents=True, exist_ok=True)
        repo_url = f"https://github.com/{repo_slug}.git"
        sha8 = base_commit[:8]

        # --- Attempt 1: shallow fetch of the specific SHA --------------------
        # GitHub public repos support uploadpack.allowReachableSHA1InWant, so
        # fetching a single commit SHA with --depth 1 is normally possible and
        # much faster than a full clone.
        logger.info(
            "Checking out %s@%s into %s (shallow fetch attempt)",
            repo_slug, sha8, target_dir,
        )
        try:
            self._run_git(["init", "--quiet"], cwd=target_dir)
            self._run_git(["remote", "add", "origin", repo_url], cwd=target_dir)
            self._run_git(
                ["fetch", "--depth", "1", "--quiet", "origin", base_commit],
                cwd=target_dir,
                timeout=180,
            )
            self._run_git(["checkout", "--quiet", "FETCH_HEAD"], cwd=target_dir)
            logger.info(
                "Shallow-fetched %s@%s into %s", repo_slug, sha8, target_dir
            )
            return
        except subprocess.CalledProcessError as exc:
            logger.info(
                "Shallow fetch of %s@%s failed (exit %s); falling back to full clone",
                repo_slug, sha8, exc.returncode,
            )
        except FileNotFoundError:
            logger.error(
                "git not found on PATH — cannot check out %s@%s. "
                "Install git and ensure it is on PATH.",
                repo_slug, sha8,
            )
            return

        # Clean up partial git state before retrying
        shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.mkdir(parents=True, exist_ok=True)

        # --- Attempt 2: full clone then checkout -----------------------------
        logger.info("Full-cloning %s for commit %s", repo_slug, sha8)
        try:
            self._run_git(
                ["clone", "--quiet", repo_url, str(target_dir)],
                cwd=target_dir.parent,
                timeout=600,
            )
            self._run_git(["checkout", "--quiet", base_commit], cwd=target_dir)
            logger.info(
                "Full-cloned %s and checked out %s", repo_slug, sha8
            )
        except FileNotFoundError:
            logger.error(
                "git not found on PATH — cannot check out %s@%s. "
                "Install git and ensure it is on PATH.",
                repo_slug, sha8,
            )
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Failed to check out %s@%s (exit %s). "
                "Agents will proceed without source code and may hallucinate line numbers.",
                repo_slug, sha8, exc.returncode,
            )
            # Don't raise — proceed without repo; downstream agents will emit
            # an empty or best-effort patch.

    def _run_git(
        self,
        args: List[str],
        cwd: Path,
        timeout: int = 120,
    ) -> subprocess.CompletedProcess:
        """Run a git sub-command and raise ``CalledProcessError`` on failure.

        Args:
            args:    git arguments (without the leading ``"git"``).
            cwd:     Working directory for the subprocess.
            timeout: Seconds before the subprocess is killed.

        Returns:
            The completed process object (stdout/stderr captured as text).

        Raises:
            subprocess.CalledProcessError: On non-zero exit.
            FileNotFoundError: When ``git`` is not found on PATH.
            subprocess.TimeoutExpired: When the command exceeds *timeout*.
        """
        return subprocess.run(
            ["git"] + list(args),
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_generated_patch(
        self, workspace_path: Path
    ) -> tuple[Optional[str], Optional[str]]:
        """Search workspace_path for a generated patch file.

        Search order:
            1. solution.patch
            2. solution.diff
            3. Any *.patch file
            4. Any *.diff file

        Returns:
            (patch_content, relative_filename) or (None, None) if not found.
        """
        if not workspace_path.exists():
            return None, None

        priority_names = ["solution.patch", "solution.diff"]
        for name in priority_names:
            candidate = workspace_path / name
            if candidate.exists() and candidate.stat().st_size > 0:
                return candidate.read_text(encoding="utf-8", errors="replace"), name

        for glob_pattern in ("*.patch", "*.diff"):
            matches = sorted(workspace_path.glob(glob_pattern))
            for match in matches:
                if match.stat().st_size > 0:
                    return (
                        match.read_text(encoding="utf-8", errors="replace"),
                        match.name,
                    )

        return None, None
