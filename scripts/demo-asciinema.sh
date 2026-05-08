#!/usr/bin/env bash
# Demo script for asciinema recording.
# Run: asciinema rec --command "bash scripts/demo-asciinema.sh" demo.cast
# Then: asciinema upload demo.cast (or convert to GIF via agg).

set -euo pipefail

PAUSE="${DEMO_PAUSE:-1.5}"

step() {
  echo
  echo "# $*"
  sleep "$PAUSE"
}

run() {
  echo "$ $*"
  sleep 0.4
  bash -c "$*" || echo "(no output - empty catalog or expected error)"
  sleep "$PAUSE"
}

clear

step "context-absorb: cross-CLI session transfer for parallel AI coding"
step "Works with Claude Code and Codex - bridges them via transcripts and native forks."
sleep "$PAUSE"

step "1. List active sessions across both CLIs"
run "sa list --active-only"

step "2. Show the session attached to the current working directory"
run "sa here show"

step "3. Default action: digest the cwd-attached session (the 70% case)"
run "sa here"

step "4. Preview a self-fork: same session, fresh context window"
run "sa fork-myself --dry-run"

step "5. Inspect the catalog state as JSON"
run "sa db --json | head -20"

step "6. Cross-CLI brief: distill a Codex session into a markdown briefing"
run "sa brief --source codex --limit 1"

step "Done. Run 'sa --help' for the full command surface."
sleep "$PAUSE"
