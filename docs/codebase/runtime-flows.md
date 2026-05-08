---
audience: ["agents", "team"]
source: "context-copilot"
managed: true
last_verified: "2026-04-19T00:00:35Z"
source_snapshot_hash: "6a6fb8a10a0a9d2ec337a21e67734d9f989a7828be6ea4e3afa4df34123cf674"
---

# Codebase Runtime Flows

Execution flow map across hooks and dashboard.

<!-- context-copilot:begin section=runtime-flows -->
## Runtime Flows

- **Hook Validation** — PreToolUse validates write intents and blocks unsafe hallucinated edits.
  - owner: `groundtruth/validator.py`
- **Observation Capture** — PostToolUse captures facts, phantom-path findings, and schedules observer docs.
  - owner: `groundtruth/observer.py`
- **Intent + Scope Injection** — UserPromptSubmit classifies archetype, builds scope, and assembles injected context.
  - owner: `upscaler/planner.py`
- **Observer Docs Runtime** — Background worker coalesces events and renders operational observer docs bundle.
  - owner: `observer_docs/runtime.py`
- **Durable Docs Runtime** — Background worker transforms runtime evidence into tracked docs/codebase markdown.
  - owner: `codebase_docs/runtime.py`
- **Dashboard Broadcast** — Backend gathers DB + telemetry state every second and broadcasts over WebSocket.
  - owner: `dashboard/backend/server.py`
<!-- context-copilot:end section=runtime-flows -->
