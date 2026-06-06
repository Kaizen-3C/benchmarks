#!/usr/bin/env bash
# A5 pre-campaign hygiene — run in the WSL workspace before any (re)generation sweep. $0.
# Prevents the failure modes the 2026-06 verification surfaced (orphaned containers ->
# false 0/0/0; stale verify branches; wrong env). See ../RERUN_CHECKLIST.md.
set -uo pipefail

echo "=== 1. remove orphaned commit0 eval containers (a leftover 409s -> false 0/0/0) ==="
ids=$(docker ps -aq --filter name=commit0.eval 2>/dev/null || true)
if [ -n "$ids" ]; then docker rm -f $ids >/dev/null && echo "  removed $(echo "$ids" | wc -l)"; else echo "  none"; fi

echo "=== 2. docker daemon up? ==="
docker info >/dev/null 2>&1 && echo "  docker OK" || echo "  DOCKER DOWN — start Docker Desktop"

echo "=== 3. pinned commit0 version (expected 0.1.8 per CAMPAIGN_README.md) ==="
python - <<'PY' 2>/dev/null || pip show commit0 2>/dev/null | grep -E '^Version' | sed 's/^/  commit0 /'
import importlib.metadata as m
print("  commit0", m.version("commit0"))
PY

echo "=== 4. stale temp verify branches left in repos (clean before scoring) ==="
shopt -s nullglob
found=0
for r in "$HOME"/kaizen-commit0/repos/*/; do
  b=$(git -C "$r" for-each-ref --format='%(refname:short)' refs/heads 2>/dev/null \
        | grep -E '^_verify|^_vtest|^_nt' | tr '\n' ' ')
  if [ -n "$b" ]; then echo "  $(basename "$r"): $b"; found=1; fi
done
[ "$found" = 0 ] && echo "  none"

echo "PREFLIGHT DONE — safe to start the sweep (use repeat_runner.py for pacing + valid-rep gating)"
