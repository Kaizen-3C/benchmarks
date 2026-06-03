#!/usr/bin/env bash
# Phase-1 full-suite re-validation driver (RUN ON THE WSL HOST).
#
# Encodes RE-VALIDATION.md §4 as one gated, abort-on-error operation:
#   preflight -> SMOKE GATE -> confirm -> archive old data -> 4 sweeps ->
#   sync workspace results into the repo -> strict provenance guard -> regen analysis.
#
# This SPENDS ~$65 of Anthropic + OpenAI API budget and needs WSL2 + Docker +
# the commit0 CLI + the aider/smolagents SDKs. It cannot run on a Windows host.
#
# Usage (from the kaizen-commit0 workspace, .venv active, .env present):
#   bash baselines/run_revalidation.sh --dry-run             # print the plan, spend nothing
#   bash baselines/run_revalidation.sh --smoke-only          # preflight + 1-lib smoke (cents)
#   bash baselines/run_revalidation.sh --repo ~/src/benchmarks   # full re-run (prompts before spend)
#   bash baselines/run_revalidation.sh --repo ~/src/benchmarks --yes   # full re-run, no prompt
#
# Flags:
#   --repo PATH   path to the benchmarks git checkout whose commit0/results/ is authoritative
#                 (defaults to the git toplevel of this script; required if that can't be detected)
#   --smoke-only  stop after the smoke gate (still spends a few cents on 1 lib/arch)
#   --dry-run     print every step without executing (spends nothing)
#   --yes         skip the interactive confirm before the paid sweep
set -euo pipefail

# ---- locate workspace (where the runners live + write results) ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"     # .../baselines
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"                       # kaizen-commit0 root
WS_RESULTS="$WORKSPACE/baselines/results"

REPO=""; SMOKE_ONLY=0; DRY_RUN=0; ASSUME_YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2;;
    --smoke-only) SMOKE_ONLY=1; shift;;
    --dry-run) DRY_RUN=1; shift;;
    --yes) ASSUME_YES=1; shift;;
    *) echo "unknown flag: $1" >&2; exit 2;;
  esac
done

run() { echo "  + $*"; [ "$DRY_RUN" = 1 ] || "$@"; }
say() { echo; echo "== $* =="; }

# ---- preflight: fail fast, before any spend ----
say "PREFLIGHT"
fail=0
need() { command -v "$1" >/dev/null 2>&1 || { echo "  MISSING: $1"; fail=1; }; }
need python; need docker; need commit0; need git
if command -v docker >/dev/null 2>&1; then
  docker info >/dev/null 2>&1 || { echo "  Docker daemon not reachable"; fail=1; }
fi
[ -f "$WORKSPACE/.env" ] || echo "  WARN: no $WORKSPACE/.env (scripts source it for API keys)"
[ -n "${ANTHROPIC_API_KEY:-}" ] || echo "  note: ANTHROPIC_API_KEY not in env (may come from .env)"
[ -n "${OPENAI_API_KEY:-}" ]    || echo "  note: OPENAI_API_KEY not in env (may come from .env)"

# CRITICAL: refuse to run the OLD truncating runner. The fix adds _persist_and_score.
for r in baselines/aider/_aider_runner.py baselines/smolagents/_smolagents_runner.py; do
  if [ -f "$WORKSPACE/$r" ] && grep -q "_persist_and_score" "$WORKSPACE/$r"; then
    echo "  OK: $r carries the full-suite/persistence fix"
  else
    echo "  STALE/MISSING: $WORKSPACE/$r lacks the scoring fix — sync it from the repo first"; fail=1
  fi
done

# resolve repo (for the results sync + guard + analysis)
if [ -z "$REPO" ]; then REPO="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"; fi
if [ -n "$REPO" ] && [ -d "$REPO/commit0/results" ]; then
  echo "  repo results: $REPO/commit0/results"
else
  echo "  WARN: repo results dir not resolved (pass --repo PATH); sync + guard + regen will be skipped"
  REPO=""
fi
[ "$fail" = 0 ] || { echo; echo "PREFLIGHT FAILED — fix the above, spend nothing."; exit 1; }

# ---- smoke gate: prove the wiring on 1 lib before the full spend ----
say "SMOKE GATE (1 lib/arch)"
run python baselines/smoke_revalidation.py --arch aider      --provider anthropic --lib wcwidth
run python baselines/smoke_revalidation.py --arch smolagents --provider openai    --lib wcwidth
echo "  smoke gate passed (or dry-run)."
if [ "$SMOKE_ONLY" = 1 ]; then say "DONE (--smoke-only)"; exit 0; fi

# ---- confirm before the paid sweep ----
if [ "$ASSUME_YES" != 1 ] && [ "$DRY_RUN" != 1 ]; then
  if [ -t 0 ]; then
    read -r -p $'\nProceed with the ~$65 full re-run (4 sweeps)? [y/N] ' ans
    case "$ans" in y|Y|yes) ;; *) echo "aborted by user."; exit 0;; esac
  else
    echo "non-interactive: pass --yes to proceed with spend. Aborting."; exit 0
  fi
fi

# ---- archive existing competitor data (never overwrite blind) ----
say "ARCHIVE existing -x JSONs"
if [ -n "$REPO" ]; then
  STAMP="$(date +%Y%m%d_%H%M%S)"
  ARCH_DIR="$REPO/commit0/results/_pre_revalidation/$STAMP"
  run mkdir -p "$ARCH_DIR"
  # shellcheck disable=SC2086
  run bash -c "mv $REPO/commit0/results/*_aider_*.json $REPO/commit0/results/*_smolagents_*.json '$ARCH_DIR'/ 2>/dev/null || true"
  echo "  archived to $ARCH_DIR (if any matched)"
else
  echo "  (skipped — no --repo)"
fi

# ---- the four sweeps (the spend) ----
say "RE-RUN: 4 sweeps (full-suite scoring + code persistence)"
run python baselines/aider/run_lite_aider.py            --provider anthropic
run python baselines/aider/run_lite_aider.py            --provider openai
run python baselines/smolagents/run_lite_smolagents.py  --provider anthropic
run python baselines/smolagents/run_lite_smolagents.py  --provider openai

# ---- sync workspace results (+patches) into the repo ----
say "SYNC workspace results -> repo"
if [ -n "$REPO" ]; then
  run bash -c "cp $WS_RESULTS/*_aider_*.json $WS_RESULTS/*_smolagents_*.json '$REPO/commit0/results'/ 2>/dev/null || true"
  run bash -c "cp $WS_RESULTS/aggregate_lite_aider_*.json $WS_RESULTS/aggregate_lite_smolagents_*.json '$REPO/commit0/results'/ 2>/dev/null || true"
  run mkdir -p "$REPO/commit0/results/patches"
  run bash -c "cp $WS_RESULTS/patches/*.patch '$REPO/commit0/results/patches'/ 2>/dev/null || true"
else
  echo "  (skipped — no --repo; results remain in $WS_RESULTS)"
fi

# ---- assert clean, then regenerate analysis ----
if [ -n "$REPO" ]; then
  say "STRICT PROVENANCE GUARD"
  echo "  (expect 0 pending; if not, lower EXPECTED_PENDING per the warning)"
  run python "$REPO/commit0/baselines/check_scoring_provenance.py" --strict || \
    echo "  guard reports pending — see RE-VALIDATION.md before declaring done"
  say "REGENERATE FINGERPRINT"
  run python "$REPO/commit0/baselines/value_add_fingerprint.py"
fi

say "DONE"
cat <<'NEXT'
Next (manual, see RE-VALIDATION.md §4 "After the re-run"):
  1. Regenerate Figure 1: python paper/figures/figure1_fingerprint_heatmap.py
  2. Fill AAR_REVALIDATION_STUB.md (before/after deltas) and rename it.
  3. Update README headline + "What we proved" #3; remove the ⚠ caveats.
  4. Remove PROTOCOL §6 violation note + results/SCORING_NOTICE.md.
  5. Set EXPECTED_PENDING=0 in check_scoring_provenance.py; commit patches + new JSONs.
NEXT
