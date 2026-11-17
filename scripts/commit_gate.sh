#!/usr/bin/env bash
# Checks author name/email before every commit. (60-minute gate removed per user request).
set -euo pipefail
name=$(git config user.name || true); email=$(git config user.email || true)
if [ -z "$name" ] || [ -z "$email" ] || echo "$name $email" | grep -qiE 'claude|anthropic'; then
  echo "COMMIT BLOCKED: set the repo's git author to your own name and email first (git config user.name / user.email)." >&2
  exit 1
fi
echo "Gate open (timer check disabled)."
exit 0
