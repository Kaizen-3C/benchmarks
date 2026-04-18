"""
CD-AOR Benchmark Runner.

Usage:
    python -m benchmarks.runner --benchmark humaneval --data-dir ./data/benchmarks
    python -m benchmarks.runner --benchmark mbpp --data-dir ./data/benchmarks --limit 20

Evaluation-only mode (default):
    Runs the test harness against code already generated in workspace directories.
    Use this to validate the evaluation pipeline before wiring in the orchestrator.

Full CD-AOR mode (--run-cdaor flag):
    Submits each benchmark task through the full denoising loop, then evaluates.
    Requires agents.src on PYTHONPATH (set PYTHONPATH=<repo-root>).

Checkpoint / resume mode:
    --resume         Resume a previous run from CHECKPOINT.json in --output-dir.
    --retry-failed   When resuming, also retry tasks that previously failed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Load .env from repo root so ANTHROPIC_API_KEY etc. are available without
# requiring the caller to export them manually.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
except ImportError:
    pass  # python-dotenv not installed — rely on shell environment

from .base_adapter import BenchmarkAdapter, BenchmarkTask, TaskResult
from .humaneval import HumanEvalAdapter
from .mbpp import MBPPAdapter
from .swebench import SWEBenchAdapter
from .terminalbench import TerminalBenchAdapter

logger = logging.getLogger(__name__)

ADAPTERS: dict[str, type[BenchmarkAdapter]] = {
    "humaneval": HumanEvalAdapter,
    "mbpp": MBPPAdapter,
    "swebench": SWEBenchAdapter,
    "terminalbench": TerminalBenchAdapter,
}

# Checkpoint schema version — increment when the format changes in a
# backward-incompatible way so readers can gate on this.
CHECKPOINT_SCHEMA_VERSION = 1

# Progress log every N tasks
_PROGRESS_LOG_EVERY = 5


# Three dedicated Ollama servers — one per tier.
# Override with --speed-port / --balanced-port / --reasoning-port if needed.
_OLLAMA_TIER_PORTS: dict[str, int] = {
    "speed":     11436,   # ollama-speed   — fast lookups (Researcher)
    "balanced":  11435,   # ollama-balanced — quality+speed (RedTeam/Draft/Eval)
    "reasoning": 11434,   # ollama-reasoning — best coder (Write agent)
}

# Context window per tier. qwen3-coder:30b is a reasoning model that emits
# <think> blocks before code — it needs a large context to avoid truncation.
# Without this, Ollama defaults to 2048 tokens which silently truncates
# reasoning model output, producing empty or incomplete responses.
_OLLAMA_TIER_CTX: dict[str, int] = {
    "speed":     8192,    # llama3:latest — simple lookups, moderate context
    "balanced":  16384,   # qwen2.5-coder:14b — review/draft tasks
    "reasoning": 32768,   # qwen3-coder:30b — full reasoning chain + code output
}

# Default models per Ollama tier (can be overridden via CLI flags)
_OLLAMA_TIER_MODELS: dict[str, str] = {
    "speed":     "llama3:latest",
    "balanced":  "qwen2.5-coder:14b",
    "reasoning": "qwen3-coder:30b",
}


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _checkpoint_path(output_dir: Path) -> Path:
    return output_dir / "CHECKPOINT.json"


def _load_checkpoint(output_dir: Path) -> Optional[Dict[str, Any]]:
    """Load CHECKPOINT.json from output_dir. Returns None if not found."""
    path = _checkpoint_path(output_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        version = data.get("schema_version", 0)
        if version != CHECKPOINT_SCHEMA_VERSION:
            logger.warning(
                "Checkpoint schema_version=%d (expected %d). Proceeding cautiously.",
                version, CHECKPOINT_SCHEMA_VERSION,
            )
        return data
    except Exception as exc:
        logger.error("Failed to read checkpoint: %s", exc)
        return None


def _write_checkpoint_atomic(output_dir: Path, data: Dict[str, Any]) -> None:
    """Atomically write checkpoint data to CHECKPOINT.json.

    Strategy:
    1. Write to a temp file in the same directory (guarantees same filesystem).
    2. fsync the temp file so data hits disk.
    3. On Windows, os.replace() handles the case where the target already
       exists (unlike os.rename() which raises FileExistsError on Windows).
       os.replace() is documented as atomic on POSIX and as atomic-as-possible
       on Windows (it uses MoveFileEx with MOVEFILE_REPLACE_EXISTING).

    This means that at no point is CHECKPOINT.json left in a partially-written
    state — readers always see either the old complete file or the new one.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    target = _checkpoint_path(output_dir)

    # Write to a temp file in the same directory so the rename stays on-volume.
    fd, tmp_path = tempfile.mkstemp(
        dir=output_dir, prefix="CHECKPOINT.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        # os.replace is atomic on POSIX; on Windows it uses MoveFileEx which
        # replaces an existing target atomically (no FileExistsError).
        os.replace(tmp_path, target)
    except Exception:
        # Clean up temp file on failure — don't leave debris.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _build_checkpoint(
    run_id: str,
    benchmark: str,
    planned_task_ids: List[str],
    completed_task_ids: List[str],
    failed_task_ids: List[str],
    per_task_results: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "benchmark": benchmark,
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "planned_task_ids": planned_task_ids,
        "completed_task_ids": completed_task_ids,
        "failed_task_ids": failed_task_ids,
        "last_updated": _utcnow_iso(),
        "per_task_results": per_task_results,
    }


def _result_to_checkpoint_entry(result: TaskResult) -> Dict[str, Any]:
    return {
        "task_id": result.task_id,
        "passed": result.passed,
        "confidence": result.confidence,
        "steps": result.steps_taken,
        "duration_s": round(result.duration_seconds, 2),
        "cost_usd": round(result.cost_usd, 6),
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "error": result.error,
        "completed_at": _utcnow_iso(),
    }


# ---------------------------------------------------------------------------
# Orchestrator factory (unchanged from original)
# ---------------------------------------------------------------------------

def _make_endpoint(
    name: str,
    provider: str,
    model: str,
    ollama_host: str = "localhost",
    ollama_port: int = 0,
    num_ctx: Optional[int] = None,
) -> "ProviderEndpoint":
    """Build a ProviderEndpoint for one tier.

    For Ollama, each tier connects to a dedicated server port:
      speed     → 11436  (ollama-speed)
      balanced  → 11435  (ollama-balanced)
      reasoning → 11434  (ollama-reasoning)

    Pass ollama_port > 0 to override the default for the named tier.
    Pass num_ctx to override the context window (defaults from _OLLAMA_TIER_CTX).
    """
    from agents.src.bootstrap_orchestrator import ProviderEndpoint
    provider = provider.lower()
    if provider == "anthropic":
        return ProviderEndpoint(name=name, provider="anthropic", model=model,
                                api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    elif provider == "openai":
        return ProviderEndpoint(name=name, provider="openai", model=model,
                                api_key=os.environ.get("OPENAI_API_KEY", ""))
    elif provider == "ollama":
        port = ollama_port if ollama_port > 0 else _OLLAMA_TIER_PORTS.get(name, 11435)
        ctx = num_ctx if num_ctx is not None else _OLLAMA_TIER_CTX.get(name, 8192)
        return ProviderEndpoint(
            name=name, provider="ollama", model=model,
            host=ollama_host, port=port, num_ctx=ctx,
        )
    else:
        return ProviderEndpoint(name=name, provider="litellm", model=model)


def _create_orchestrator(args: argparse.Namespace, workspace_path: str):
    """Instantiate a BootstrapOrchestrator from parsed CLI args.

    Supports per-tier model overrides for anti-vibe-coding (ADR-0009):
      --speed-model   → Researcher agent (fast lookups)
      --balanced-model → RedTeam, Draft, Evaluator (balanced quality)
      --reasoning-model → Write agent (code generation — use best code model)

    For Ollama, each tier routes to a dedicated server port (11434/11435/11436).
    Per-tier port overrides available via --speed-port / --balanced-port /
    --reasoning-port.

    Uses lazy imports so the agents.src package is only required when
    --run-cdaor is passed.  Raises SystemExit with a clear message if the
    package cannot be found.
    """
    try:
        from agents.src.bootstrap_orchestrator import BootstrapOrchestrator
    except ImportError as exc:
        logger.error(
            "Cannot import agents.src: %s\n"
            "Add the repository root to PYTHONPATH, e.g.:\n"
            "  PYTHONPATH=<repo-root> python -m benchmarks.runner --run-cdaor ...",
            exc,
        )
        sys.exit(1)

    provider = args.provider.lower()
    ollama_host = getattr(args, "ollama_host", "localhost") or "localhost"

    # For Ollama, use per-tier model defaults when no explicit override given.
    def _resolve_model(tier: str, override: str | None) -> str:
        if override:
            return override
        if provider == "ollama":
            return _OLLAMA_TIER_MODELS.get(tier, args.model)
        return args.model

    speed_model     = _resolve_model("speed",     getattr(args, "speed_model",     None))
    balanced_model  = _resolve_model("balanced",  getattr(args, "balanced_model",  None))
    reasoning_model = _resolve_model("reasoning", getattr(args, "reasoning_model", None))

    speed_ep    = _make_endpoint("speed",    provider, speed_model,    ollama_host, getattr(args, "speed_port",     0))
    balanced_ep = _make_endpoint("balanced", provider, balanced_model, ollama_host, getattr(args, "balanced_port",  0))
    reasoning_ep= _make_endpoint("reasoning",provider, reasoning_model,ollama_host, getattr(args, "reasoning_port", 0))

    logger.info(
        "Provider config — "
        "speed: %s/%s@%s  balanced: %s/%s@%s  reasoning: %s/%s@%s",
        provider, speed_model,     speed_ep.port if provider == "ollama" else "N/A",
        provider, balanced_model,  balanced_ep.port if provider == "ollama" else "N/A",
        provider, reasoning_model, reasoning_ep.port if provider == "ollama" else "N/A",
    )

    return BootstrapOrchestrator(
        speed=speed_ep,
        balanced=balanced_ep,
        reasoning=reasoning_ep,
        workspace_path=workspace_path,
        theta=args.theta,
        epsilon=args.epsilon,
        max_steps=args.max_steps,
        skip_red_team=args.skip_red_team,
        phase4_enabled=getattr(args, "phase4", False),
    )


def _benchmark_task_to_spec(
    task: BenchmarkTask,
    workspace_path: "Path",
    benchmark_name: str = "generic",
):
    """Convert a BenchmarkTask into a TaskSpec for the BootstrapOrchestrator.

    Benchmark tasks have a fixed output contract: write ``solution.py`` in the
    workspace root containing the required function.  We pass this as
    ``pre_planned_files`` so the Draft Agent skips its LLM file-planning and
    the Write Agent targets exactly the right file instead of generating
    Kaizen framework infrastructure code.

    ``benchmark_name`` flows into ``TaskSpec.benchmark_type`` so the orchestrator
    can route SWE-bench tasks through the Phase 3 plan-driven pipeline.
    Accepted values: "swebench", "humaneval", "mbpp", "generic".

    Uses a lazy import so agents.src is only pulled in when needed.
    """
    try:
        from agents.src.adr_task_loader import TaskSpec
    except ImportError as exc:
        logger.error("Cannot import agents.src.adr_task_loader: %s", exc)
        sys.exit(1)

    entry = task.entry_point or task.task_id
    decision = (
        f"Write a Python function named `{entry}` in the file `solution.py` "
        f"in the workspace root. The function must pass all provided test cases. "
        f"Do NOT write any other files, test files, or framework code. "
        f"ONLY write solution.py containing the single function implementation."
    )

    # Normalize benchmark_type — TaskSpec only accepts the documented values.
    _allowed_types = {"swebench", "humaneval", "mbpp", "generic"}
    benchmark_type = benchmark_name if benchmark_name in _allowed_types else "generic"

    # For SWE-bench the output is a unified diff, not solution.py. We skip
    # pre_planned_files in that case so the Phase 3 plan-driven Write agent can
    # emit solution.patch based on the Researcher+Draft plan.
    if benchmark_type == "swebench":
        return TaskSpec(
            adr_id=task.task_id,
            title=f"SWE-bench: {task.task_id}",
            status="Accepted",
            context=task.prompt,
            decision=decision,
            consequences="solution.patch must apply cleanly and pass the hidden tests",
            full_text=task.prompt,
            layer_hints=["python"],
            pre_planned_files=[],
            benchmark_type="swebench",
        )

    # TerminalBench tasks require a shell script solution rather than a Python
    # function. Instruct the Write Agent to emit solution.sh so the adapter's
    # _find_generated_output can locate it (it looks for *.sh, excluding eval.sh).
    if benchmark_name == "terminalbench":
        tb_decision = (
            f"Write a bash shell script in the file `solution.sh` in the workspace root. "
            f"The script must complete the task described in task.md when executed inside "
            f"the Docker container specified in metadata.json. "
            f"Do NOT write solution.py or any Python files — the evaluator expects shell commands. "
            f"Read task.md for the full specification."
        )
        return TaskSpec(
            adr_id=task.task_id,
            title=f"TerminalBench: {task.task_id}",
            status="Accepted",
            context=task.prompt,
            decision=tb_decision,
            consequences=(
                "solution.sh must execute correctly inside the Docker container. "
                "Full pass/fail evaluation requires running eval.sh in the Docker environment."
            ),
            full_text=task.prompt,
            layer_hints=["bash", "shell"],
            pre_planned_files=[
                {
                    "file_path": "solution.sh",
                    "change_type": "create",
                    "description": (
                        "Bash script that completes the terminal task. "
                        "Read task.md for the full specification."
                    ),
                }
            ],
            benchmark_type="generic",
        )

    return TaskSpec(
        adr_id=task.task_id,
        title=f"Benchmark: {task.task_id}",
        status="Accepted",
        context=task.prompt,
        decision=decision,
        consequences="solution.py must define the function and pass all test cases",
        full_text=task.prompt,
        layer_hints=["python"],
        # Tell _get_target_files to skip the framework file mapping.
        pre_planned_files=[
            {
                "file_path": "solution.py",
                "change_type": "create",
                "description": (
                    f"Python function `{entry}` that solves the benchmark problem. "
                    f"Read prompt.txt for the full specification."
                ),
            }
        ],
        benchmark_type=benchmark_type,
    )


# ---------------------------------------------------------------------------
# Interrupt-aware task runner
# ---------------------------------------------------------------------------

class _InterruptHandler:
    """Cooperative SIGINT handler that lets the current task finish.

    On the first Ctrl-C, sets .interrupted = True (signals the loop to stop
    after the current task).  On the second Ctrl-C within the same run, raises
    KeyboardInterrupt immediately.
    """

    def __init__(self) -> None:
        self.interrupted = False
        self._count = 0
        self._original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handle)

    def _handle(self, signum: int, frame: Any) -> None:  # noqa: ARG002
        self._count += 1
        if self._count == 1:
            print(
                "\n[runner] Interrupt received — finishing current task, then stopping. "
                "Press Ctrl-C again to force-quit immediately.",
                flush=True,
            )
            self.interrupted = True
        else:
            print("\n[runner] Force-quit requested.", flush=True)
            raise KeyboardInterrupt

    def restore(self) -> None:
        signal.signal(signal.SIGINT, self._original_handler)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="CD-AOR Benchmark Runner")
    parser.add_argument(
        "--benchmark",
        required=True,
        choices=list(ADAPTERS.keys()),
        help="Benchmark to run",
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        type=Path,
        help="Directory containing benchmark data files (e.g. HumanEval.jsonl)",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=Path("./benchmark_workspaces"),
        help="Root directory for per-task workspaces",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./benchmark_results"),
        help="Directory for result JSON files",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of tasks to run (for quick validation)",
    )
    parser.add_argument(
        "--task-ids",
        default=None,
        help=(
            "Comma-separated list of task IDs to run (e.g. HumanEval/72,HumanEval/74). "
            "When set, only these tasks are evaluated — useful for targeted retests."
        ),
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=5,
        help="Max denoising steps per task (when orchestrator is wired)",
    )
    parser.add_argument(
        "--provider",
        default="anthropic",
        help="LLM provider for CD-AOR orchestrator",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help=(
            "Default model for all tiers (overridden by --speed/balanced/reasoning-model). "
            "For --provider ollama the tier defaults are: "
            "speed=llama3:latest, balanced=qwen2.5-coder:14b, reasoning=qwen3-coder:30b."
        ),
    )
    parser.add_argument(
        "--speed-model",
        default=None,
        help="Model for speed tier (Researcher). Overrides --model.",
    )
    parser.add_argument(
        "--balanced-model",
        default=None,
        help="Model for balanced tier (RedTeam, Draft, Evaluator). Overrides --model.",
    )
    parser.add_argument(
        "--reasoning-model",
        default=None,
        help="Model for reasoning tier (Write agent — code generation). Overrides --model.",
    )
    # Ollama per-tier port overrides (default: speed=11436, balanced=11435, reasoning=11434)
    parser.add_argument(
        "--ollama-host", default="localhost",
        help="Hostname for all Ollama servers (default: localhost)",
    )
    parser.add_argument(
        "--speed-port", type=int, default=0,
        help="Ollama port for speed tier (default: 11436)",
    )
    parser.add_argument(
        "--balanced-port", type=int, default=0,
        help="Ollama port for balanced tier (default: 11435)",
    )
    parser.add_argument(
        "--reasoning-port", type=int, default=0,
        help="Ollama port for reasoning tier (default: 11434)",
    )
    parser.add_argument(
        "--run-cdaor",
        action="store_true",
        default=False,
        help=(
            "Run the full CD-AOR denoising loop on each task "
            "(requires agents.src on PYTHONPATH)"
        ),
    )
    parser.add_argument(
        "--skip-red-team",
        action="store_true",
        default=False,
        help="Ablation: skip the Red Team agent in the denoising loop",
    )
    parser.add_argument(
        "--phase4",
        action="store_true",
        default=False,
        help="Enable Phase 4 pipeline (Intake + Triage + ADR Quality Gate) for SWE-bench tasks",
    )
    parser.add_argument(
        "--theta",
        type=float,
        default=0.70,
        help="Convergence confidence threshold for BootstrapOrchestrator (default: 0.70)",
    )
    parser.add_argument(
        "--epsilon",
        type=float,
        default=0.05,
        help="Convergence delta threshold for BootstrapOrchestrator (default: 0.05)",
    )
    # ---- Checkpoint / resume flags ----------------------------------------
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help=(
            "Resume a previous run. Reads CHECKPOINT.json from --output-dir "
            "and skips already-completed tasks."
        ),
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        default=False,
        help=(
            "When resuming, also retry tasks that previously completed with an error. "
            "Has no effect unless --resume is also set."
        ),
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "Explicit run ID embedded in CHECKPOINT.json. "
            "Auto-generated from benchmark name + timestamp when not set."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # -----------------------------------------------------------------------
    # Derive a stable run_id for this session
    # -----------------------------------------------------------------------
    run_id = args.run_id or (
        f"{args.benchmark}_"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )

    # -----------------------------------------------------------------------
    # Load tasks
    # -----------------------------------------------------------------------
    adapter_cls = ADAPTERS[args.benchmark]
    adapter = adapter_cls(data_dir=args.data_dir, workspace_root=args.workspace_root)

    logger.info("Loading %s tasks from %s", args.benchmark, args.data_dir)
    tasks = adapter.load_tasks()
    if args.task_ids:
        filter_set = {tid.strip() for tid in args.task_ids.split(",")}
        tasks = [t for t in tasks if t.task_id in filter_set]
        logger.info("Filtered to %d tasks by --task-ids", len(tasks))
    if args.limit:
        tasks = tasks[: args.limit]

    planned_task_ids: List[str] = [t.task_id for t in tasks]
    logger.info("Planned %d tasks", len(planned_task_ids))

    # -----------------------------------------------------------------------
    # Resume: load checkpoint and skip already-done tasks
    # -----------------------------------------------------------------------
    args.output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint: Dict[str, Any] = {}
    completed_set: set[str] = set()
    failed_set: set[str] = set()
    per_task_results: Dict[str, Any] = {}

    if args.resume:
        checkpoint = _load_checkpoint(args.output_dir) or {}
        if checkpoint:
            run_id = checkpoint.get("run_id", run_id)
            completed_set = set(checkpoint.get("completed_task_ids", []))
            failed_set = set(checkpoint.get("failed_task_ids", []))
            per_task_results = checkpoint.get("per_task_results", {})
            logger.info(
                "Resuming run %s — completed=%d, failed=%d",
                run_id, len(completed_set), len(failed_set),
            )
        else:
            logger.warning(
                "--resume set but no CHECKPOINT.json found in %s; starting fresh.",
                args.output_dir,
            )

    # Decide which tasks to skip.
    # completed_set contains all attempted tasks (including ones that failed).
    # When --retry-failed is set, remove failed tasks from the skip set so they
    # are re-evaluated even though they appear in completed_set.
    skip_ids: set[str] = set(completed_set)
    if args.resume and args.retry_failed:
        # Allow failed tasks to run again.
        skip_ids -= failed_set

    tasks_to_run = [t for t in tasks if t.task_id not in skip_ids]
    skipped_count = len(tasks) - len(tasks_to_run)
    if skipped_count:
        logger.info(
            "Skipping %d already-completed task(s); running %d remaining.",
            skipped_count, len(tasks_to_run),
        )

    # Pre-populate results list from checkpoint for aggregate metrics at the end.
    # We reconstruct TaskResult stubs so compute_metrics() gets the full picture.
    from .base_adapter import TaskResult as _TaskResult
    results: List[TaskResult] = []
    for tid, entry in per_task_results.items():
        if tid in skip_ids:
            stub = _TaskResult(
                task_id=tid,
                passed=entry.get("passed", False),
                generated_code="",
                error=entry.get("error"),
                confidence=entry.get("confidence", 0.0),
                steps_taken=entry.get("steps", 0),
                duration_seconds=entry.get("duration_s", 0.0),
                cost_usd=entry.get("cost_usd", 0.0),
                input_tokens=entry.get("input_tokens", 0),
                output_tokens=entry.get("output_tokens", 0),
            )
            results.append(stub)

    # -----------------------------------------------------------------------
    # Set up interrupt handler
    # -----------------------------------------------------------------------
    interrupt_handler = _InterruptHandler()
    interrupted = False

    # -----------------------------------------------------------------------
    # Task loop
    # -----------------------------------------------------------------------
    try:
        for i, task in enumerate(tasks_to_run):
            if interrupt_handler.interrupted:
                logger.info("[runner] Stopping after task %d (interrupt requested).", i)
                interrupted = True
                break

            task_workspace = (
                args.workspace_root / args.benchmark / task.task_id.replace("/", "_")
            )
            adapter.task_to_workspace(task, task_workspace)

            task_error: Optional[str] = None
            try:
                if args.run_cdaor:
                    # ------------------------------------------------------
                    # Full CD-AOR mode
                    # ------------------------------------------------------
                    orchestrator = _create_orchestrator(args, str(task_workspace))
                    task_spec = _benchmark_task_to_spec(task, task_workspace, args.benchmark)

                    logger.info(
                        "[%d/%d] Running CD-AOR denoising loop for %s",
                        i + 1, len(tasks_to_run), task.task_id,
                    )

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        bootstrap_result = loop.run_until_complete(orchestrator.run(task_spec))
                    finally:
                        try:
                            pending = asyncio.all_tasks(loop)
                            if pending:
                                loop.run_until_complete(
                                    asyncio.gather(*pending, return_exceptions=True)
                                )
                        except Exception:
                            pass
                        loop.close()

                    logger.info(
                        "[%d/%d] CD-AOR finished: converged=%s confidence=%.3f steps=%d",
                        i + 1, len(tasks_to_run),
                        bootstrap_result.converged,
                        bootstrap_result.final_confidence,
                        bootstrap_result.steps_taken,
                    )

                    start = time.time()
                    result = adapter.evaluate_output(task, task_workspace)
                    result.duration_seconds = bootstrap_result.total_duration_secs + (
                        time.time() - start
                    )
                    result.confidence = bootstrap_result.final_confidence
                    result.steps_taken = bootstrap_result.steps_taken
                    result.cost_usd = bootstrap_result.total_cost_usd
                    result.input_tokens = bootstrap_result.total_input_tokens
                    result.output_tokens = bootstrap_result.total_output_tokens
                    # Per-signal breakdown for benchmark JSON (diagnoses the
                    # "ceiling pinned at 0.28125" class of bugs where 5/6
                    # signals silently return 0.0).
                    result.signal_scores = dict(
                        getattr(bootstrap_result, "final_signals", {}) or {}
                    )

                else:
                    # ------------------------------------------------------
                    # Evaluation-only mode (default)
                    # ------------------------------------------------------
                    start = time.time()
                    result = adapter.evaluate_output(task, task_workspace)
                    result.duration_seconds = time.time() - start

            except KeyboardInterrupt:
                # Second Ctrl-C — stop immediately without recording the task.
                logger.warning("[runner] Force-quit mid-task %s.", task.task_id)
                interrupted = True
                break
            except Exception as exc:
                logger.error("[%d/%d] EXCEPTION on %s: %s", i + 1, len(tasks_to_run), task.task_id, exc)
                result = _TaskResult(
                    task_id=task.task_id,
                    passed=False,
                    generated_code="",
                    error=str(exc),
                )
                task_error = str(exc)

            results.append(result)

            status = "PASS" if result.passed else "FAIL"
            logger.info("[%d/%d] %s %s", i + 1, len(tasks_to_run), status, task.task_id)

            # Update checkpoint tracking sets
            if task_error or not result.passed:
                failed_set.add(task.task_id)
            else:
                failed_set.discard(task.task_id)
            completed_set.add(task.task_id)
            per_task_results[task.task_id] = _result_to_checkpoint_entry(result)

            # Atomic checkpoint write after each task
            ckpt_data = _build_checkpoint(
                run_id=run_id,
                benchmark=args.benchmark,
                planned_task_ids=planned_task_ids,
                completed_task_ids=list(completed_set),
                failed_task_ids=list(failed_set),
                per_task_results=per_task_results,
            )
            _write_checkpoint_atomic(args.output_dir, ckpt_data)

            # Periodic progress log
            done_count = i + 1
            total_count = len(tasks_to_run)
            if done_count % _PROGRESS_LOG_EVERY == 0 or done_count == total_count:
                pct = 100.0 * done_count / total_count if total_count else 0
                logger.info(
                    "[progress] %d/%d tasks done (%.1f%%) — pass rate so far: %d/%d",
                    done_count, total_count, pct,
                    sum(1 for r in results if r.passed),
                    len(results),
                )

    except KeyboardInterrupt:
        interrupted = True
        logger.warning("[runner] Interrupted — writing final checkpoint.")
    finally:
        interrupt_handler.restore()

    # Write a final checkpoint even if interrupted, capturing everything done.
    if per_task_results or completed_set:
        ckpt_data = _build_checkpoint(
            run_id=run_id,
            benchmark=args.benchmark,
            planned_task_ids=planned_task_ids,
            completed_task_ids=list(completed_set),
            failed_task_ids=list(failed_set),
            per_task_results=per_task_results,
        )
        _write_checkpoint_atomic(args.output_dir, ckpt_data)
        logger.info("Checkpoint written to %s", _checkpoint_path(args.output_dir))

    if interrupted:
        remaining = [t.task_id for t in tasks_to_run if t.task_id not in completed_set]
        logger.warning(
            "[runner] Run interrupted. %d/%d tasks completed. "
            "Re-run with --resume to continue. Remaining: %s",
            len(completed_set), len(planned_task_ids),
            remaining[:5],
        )
        sys.exit(130)

    # -----------------------------------------------------------------------
    # Compute aggregate metrics and save results (only when not interrupted)
    # -----------------------------------------------------------------------
    report = adapter.compute_metrics(results)
    saved = adapter.save_results(report, args.output_dir)

    # Print summary table
    print()
    print("=" * 60)
    print(f"  {args.benchmark.upper()} Benchmark Results")
    print("=" * 60)
    d = report.to_dict()
    for k, v in d.items():
        print(f"  {k:20s}: {v}")
    print("=" * 60)
    print(f"  Results saved to: {saved}")
    print()


if __name__ == "__main__":
    main()
