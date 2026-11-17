#!/usr/bin/env bash
# Run this on YOUR machine, from the project folder. It makes one commit per milestone (real timestamps, no
# backdating, no history rewriting) under YOUR name and email, then pushes. The token never leaves your machine.
#
#   1. put GITHUB_TOKEN=... in .env   (fine-grained token, Contents: read and write, this repo only)
#   2. GIT_NAME="Your Name" GIT_EMAIL="you@example.com" bash scripts/push_all.sh
#
# Optional: REMOTE_URL (default https://github.com/s2kumar2007/Selling-ai-.git), WAIT_MINUTES (gap between
# commits, default 0; set 60 to respect the one-hour rule), BRANCH (default main).
set -euo pipefail
cd "$(dirname "$0")/.."

REMOTE_URL="${REMOTE_URL:-https://github.com/s2kumar2007/Selling-ai-.git}"
BRANCH="${BRANCH:-main}"
WAIT_MINUTES="${WAIT_MINUTES:-0}"
NAME="${GIT_NAME:-}"; EMAIL="${GIT_EMAIL:-}"
[ -n "$NAME" ] && [ -n "$EMAIL" ] || { echo "Set GIT_NAME and GIT_EMAIL (your own)." >&2; exit 1; }
if echo "$NAME $EMAIL" | grep -qiE 'claude|anthropic'; then echo "Author must be you, not Claude/Anthropic." >&2; exit 1; fi

TOKEN="${GITHUB_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f .env ]; then TOKEN=$(grep -E '^GITHUB_TOKEN=' .env | head -1 | cut -d= -f2- | tr -d "\"' "); fi
[ -n "$TOKEN" ] || [ "$REMOTE_URL" != "${REMOTE_URL#file://}" ] || [ -d "$REMOTE_URL" ] || { echo "GITHUB_TOKEN not found in .env" >&2; exit 1; }

[ -d .git ] || git init -q -b "$BRANCH"
git checkout -q -B "$BRANCH" 2>/dev/null || true
git config user.name "$NAME"; git config user.email "$EMAIL"
git remote get-url origin >/dev/null 2>&1 && git remote set-url origin "$REMOTE_URL" || git remote add origin "$REMOTE_URL"
git ls-files --error-unmatch .env >/dev/null 2>&1 && { echo ".env is tracked; refusing." >&2; exit 1; }

push() {
  if [ -n "$TOKEN" ]; then
    AUTH=$(printf 'x-access-token:%s' "$TOKEN" | base64 | tr -d '\n')
    git -c "http.extraheader=AUTHORIZATION: basic $AUTH" push -u origin "$BRANCH"
  else git push -u origin "$BRANCH"; fi
}

n=0
milestone() {  # milestone "message" path...
  local msg="$1"; shift
  local paths=()
  for p in "$@"; do [ -e "$p" ] && paths+=("$p"); done
  [ ${#paths[@]} -gt 0 ] || return 0
  git add -- "${paths[@]}"
  if git diff --cached --quiet; then echo "skip (nothing new): $msg"; return 0; fi
  if [ "$n" -gt 0 ] && [ "$WAIT_MINUTES" -gt 0 ]; then echo "waiting $WAIT_MINUTES min..."; sleep $((WAIT_MINUTES * 60)); fi
  git commit -q -m "$msg"
  push
  n=$((n + 1)); echo "committed + pushed: $msg"
}

milestone "chore: repo skeleton, gitignore, env example, commit gate, starter kit and summary" \
  .gitignore .env.example scripts/commit_gate.sh docs/starter_kit_summary.md starter_kit \
  seller_agent/__init__.py tools/__init__.py eval/__init__.py logs/.gitkeep
milestone "feat(store): loader and floor calculator with unit tests" \
  seller_agent/store.py seller_agent/floor.py tests/test_floor.py
milestone "feat(kernel): concession curve, accept rules, bundle option and 10-round plan with tests" \
  seller_agent/config.py seller_agent/kernel.py tests/test_kernel.py
milestone "feat(adapter): template narration and tuning sweep for the harness seller" \
  seller_agent/templates.py eval/sweep.py
milestone "feat(parser): untrusted-input parser with injection tests" \
  seller_agent/parser.py tests/test_parser.py
milestone "feat(llm): Groq client with backoff, limiter, cache and counters" \
  seller_agent/llm_client.py tests/test_llm_client.py config.example.json
milestone "feat(tactician): one-call move chooser with strict JSON and placeholders" \
  seller_agent/tactician.py
milestone "feat(tools): logged tool layer and local truthfulness pre-check" \
  tools/toolbox.py seller_agent/gate.py
milestone "feat(gate): TraceWare final gate, seller agent and harness entry point with tests" \
  seller_agent/traceware.py seller_agent/agent.py seller.py tests/test_gate_and_agent.py tests/test_adapter.py
milestone "feat(kb): knowledge documents and agent card for Rezolve retrieval" \
  scripts/build_kb_docs.py docs/kb docs/agent_card.md docs/rezolve_capabilities.md
milestone "feat(buyers): LLM buyer personas with offline stand-in and tests" \
  llm_buyers tests/test_llm_buyers.py
milestone "feat(eval): evaluation script and twin-buyer fairness test" \
  eval/run_eval.py eval/fairness.py
milestone "feat(redteam): three-condition red-team experiment harness" \
  eval/redteam.py tests/test_redteam_plumbing.py
milestone "feat(tune): parameter tuning with a held-out buyer set" \
  eval/tune.py eval/baselines/tune_result.json
milestone "feat(demo): trace panel showing claims and verdicts" \
  demo scripts/demo_run.py
milestone "docs: abstract, architecture note, demo script and README" \
  docs/abstract.md docs/architecture_note.md docs/demo_script.md README.md scripts/push_all.sh
milestone "chore: freeze v1-D with saved baseline scores and default-run transcripts" \
  eval/baselines
git rev-parse v1-D >/dev/null 2>&1 || { git tag v1-D && git -c "http.extraheader=AUTHORIZATION: basic ${AUTH:-}" push origin v1-D 2>/dev/null || push_tag=1; }
echo "done: $n commits"
