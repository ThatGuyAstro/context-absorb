---
name: handoff
description: Use when the user types /handoff. Pass-through alias for `session-absorb handoff` - writes a structured handoff brief (with optional --done / --pending / --blocked notes), logs it to the inbox, and optionally launches the receiving session.
argument-hint: "[--target-cli claude|codex] [--done TEXT] [--pending TEXT] [--blocked TEXT] [--require-ack] [--no-launch] [...]"
---

# Handoff

Thin alias for `session-absorb handoff`. Same behavior, shorter to type.

## Routing

Pass arguments straight through:

```bash
$HOME/.local/bin/session-absorb handoff {{ARGUMENTS}}
```

Task: {{ARGUMENTS}}

## Quick examples

```bash
# End-of-day async handoff to whoever opens this cwd next
/handoff --no-launch --target-cwd "$(pwd)" --done "API routes done" --pending "frontend wiring" --blocked "Stripe key"

# Cross-CLI handoff with explicit ack required
/handoff --target-cli claude --require-ack --done "refactor complete"

# Same-CLI structured handoff that opens a fork
/handoff --done "schema migrated" --pending "backfill job"
```

For the full flag list, run `session-absorb handoff --help` or see `~/.claude/skills/session-absorb/SKILL.md` and the project docs.

For a click-driven flow that picks the source session for you, use `/absorb` and choose 🎯 More then 📦 Handoff.
