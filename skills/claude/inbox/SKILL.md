---
name: inbox
description: Use when the user types /inbox. Pass-through alias for `session-absorb inbox` - lists pending handoffs targeted at the current session, cwd, or CLI. Defaults to the current context via CLAUDE_CODE_SESSION_ID and $PWD.
argument-hint: "[--source claude|codex|all] [--cwd PATH] [--show-all] [--json] [--limit N]"
---

# Inbox

Thin alias for `session-absorb inbox`. Shows pending handoffs targeted at you.

## Routing

Pass arguments straight through:

```bash
$HOME/.local/bin/session-absorb inbox {{ARGUMENTS}}
```

Task: {{ARGUMENTS}}

## Quick examples

```bash
# Pending handoffs for this session / cwd / CLI
/inbox

# Include already-acknowledged ones
/inbox --show-all

# Machine-readable
/inbox --json

# Filter by another cwd
/inbox --cwd ~/proj/api
```

Match rules: a handoff appears in your inbox if its `target_cli`, `target_cwd` (prefix match against your `$PWD`), and `target_session_id` are either null or match your current context.

To acknowledge one, use `/ack <handoff-id>`.
