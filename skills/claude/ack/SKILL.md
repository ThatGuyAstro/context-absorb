---
name: ack
description: Use when the user types /ack with a handoff id. Pass-through alias for `session-absorb ack` - marks a pending handoff as absorbed and records the acknowledgment timestamp and session id.
argument-hint: "<handoff-id> [--note TEXT]"
---

# Ack

Thin alias for `session-absorb ack`. Marks a handoff as absorbed.

## Routing

Pass arguments straight through:

```bash
$HOME/.local/bin/session-absorb ack {{ARGUMENTS}}
```

Task: {{ARGUMENTS}}

## Quick examples

```bash
# Acknowledge handoff #3
/ack 3

# Acknowledge with a note back to the source
/ack 3 --note "picked it up, continuing now"
```

To see what's pending in your inbox first, use `/inbox`.
