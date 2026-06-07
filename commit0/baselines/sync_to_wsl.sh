#!/usr/bin/env bash
# Verified sync of the baselines harness from the repo to the WSL workspace.
#
# Why this exists: a bulk `cp -rf "$SRC"/. "$DST"/ 2>/dev/null` SILENTLY skipped files
# (it left a stale 808-line kaizen_delta.py in WSL while main was 578 lines), so a Part-B
# run used the OLD runner (no per-provider branches). This copies every .py/.sh via
# redirection (which always overwrites — it cannot silently skip), strips CRLF, then
# VERIFIES each WSL file is byte-identical to the CRLF-normalized repo file, and checks a
# known marker. Fails loud on ANY mismatch. $0.
#
# Usage (in WSL):  bash sync_to_wsl.sh [REPO_ROOT]
set -uo pipefail
REPO="${1:-/mnt/c/RepoEx/Kaizen-3C/benchmarks}"
SRC="$REPO/commit0/baselines"
DST="$HOME/kaizen-commit0/baselines"
[ -d "$SRC" ] || { echo "FAIL: src not found: $SRC"; exit 2; }
[ -d "$DST" ] || { echo "FAIL: dst not found: $DST"; exit 2; }

n=0; mism=0
while IFS= read -r f; do
  rel="${f#"$SRC"/}"
  mkdir -p "$DST/$(dirname "$rel")"
  rm -f "$DST/$rel"                       # clear any read-only/stale file first
  sed 's/\r$//' "$f" > "$DST/$rel"        # redirection always writes (cannot silently skip)
  n=$((n+1))
  if ! diff -q <(sed 's/\r$//' "$f") "$DST/$rel" >/dev/null 2>&1; then
    echo "  MISMATCH: $rel"; mism=$((mism+1))
  fi
done < <(find "$SRC" -type f \( -name '*.py' -o -name '*.sh' \))

echo "synced $n files | $mism content mismatch"
# end-to-end marker checks (catch a stale/partial copy that diff alone might miss)
check() { grep -q "$2" "$DST/$1" && echo "  OK: $1 :: $3" || { echo "  FAIL: $1 missing :: $3"; mism=$((mism+1)); }; }
check kaizen_delta.py            'kaizen_delta_{provider}'  "A1 per-provider branch"
check aider/_aider_runner.py     'pin_jinja_for_litellm'    "jinja pin"
check aider/_aider_runner.py     '_score_branch'            "score_branch routing"
check single_shot_sonnet.py      'def pin_jinja_for_litellm' "jinja helper"

[ "$mism" = 0 ] && echo "SYNC VERIFIED — WSL matches repo" || { echo "SYNC FAILED ($mism issues)"; exit 1; }
