---
audience: ["agents", "team"]
source: "context-copilot"
managed: true
last_verified: "2026-04-19T00:00:35Z"
source_snapshot_hash: "6a6fb8a10a0a9d2ec337a21e67734d9f989a7828be6ea4e3afa4df34123cf674"
---

# Codebase Testing Guide

Stable test surfaces, commands, and contracts.

<!-- context-copilot:begin section=testing -->
## Test Surface

- Python test files: `0`
- Frontend test files: `0`

## Standard Validation Commands

- `uv run pytest -q`
- `uv run ruff check .`
- `npm --prefix dashboard/frontend run test`
- `npm --prefix dashboard/frontend run build`

## Contracts to Preserve

- Hooks must complete quickly and offload heavy work to background workers.
- Durable docs auto-update only managed sections.
- Observer docs and durable docs status must stay visible in dashboard diagnostics/settings.
<!-- context-copilot:end section=testing -->
