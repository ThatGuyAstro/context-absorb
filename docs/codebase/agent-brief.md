---
audience: ["agents", "team"]
source: "context-copilot"
managed: true
last_verified: "2026-04-19T00:00:35Z"
source_snapshot_hash: "6a6fb8a10a0a9d2ec337a21e67734d9f989a7828be6ea4e3afa4df34123cf674"
---

# Codebase Agent Brief

Compact shared-source brief for coding agents.

<!-- context-copilot:begin section=agent-brief -->
## Agent Brief

- Product label: `context-absorb`
- Current trigger: `observer-rebuild`
- Current trigger label: `Session stop`
- Active archetype: `bug-fix`
- Active phase: `reproduce`
- Next likely step: Advance from `reproduce` to `root-cause`.
- Facts observed: `73` / patterns observed: `8`

### Primary Hotspots

- `webapp/app.js` (heat `4`, facts `25`)
- `skills/shared/session_absorb_core.py` (heat `3`, facts `48`)

### Guardrails

- Keep hook handlers schedule-only for heavy work.
- Preserve stable-prefix ordering in injected context assembly.
- Keep generated observer docs separate from stable CDD canon artifacts.
<!-- context-copilot:end section=agent-brief -->
