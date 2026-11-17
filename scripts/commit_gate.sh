#!/usr/bin/env bash
# Blocks a commit if the last commit is less than 60 minutes old. Run before every commit.
set -euo pipefail
name=$(git config user.name || true); email=$(git config user.email || true)
if [ -z "$name" ] || [ -z "$email" ] || echo "$name $email" | grep -qiE 'claude|anthropic'; then
  echo "COMMIT BLOCKED: set the repo's git author to your own name and email first (git config user.name / user.email)." >&2
  exit 1
fi
MIN_GAP=3600
last=$(git log -1 --format=%ct 2>/dev/null || true)
if [ -z "$last" ]; then echo "No previous commit: gate open."; exit 0; fi
now=$(date +%s)
elapsed=$((now - last))
if [ "$elapsed" -lt "$MIN_GAP" ]; then
  echo "COMMIT BLOCKED: $(( (MIN_GAP - elapsed + 59) / 60 )) minute(s) remaining until the 60-minute gap is met." >&2
  exit 1
fi
echo "Gate open: $((elapsed / 60)) minutes since the last commit."
