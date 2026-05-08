---
audience: ["agents", "team"]
source: "context-copilot"
managed: true
last_verified: "2026-04-19T00:00:35Z"
source_snapshot_hash: "6a6fb8a10a0a9d2ec337a21e67734d9f989a7828be6ea4e3afa4df34123cf674"
---

# Codebase Documentation Policy

Governance for generated-vs-curated docs.

<!-- context-copilot:begin section=doc-policy -->
## Documentation Policy

- `conductor/` remains the stable product/process canon.
- `docs/codebase/` is the stable codebase-knowledge canon for team + agents.
- Observer docs remain generated operational evidence and are not stable canon.
- Promotion is fully automatic, but only within managed sections.
- Human-authored prose outside managed markers is preserved.

## Managed Sections

- Managed content is bounded by `<!-- context-copilot:begin section=... -->` and matching end markers.
- Frontmatter keys (`audience`, `source`, `managed`, `last_verified`, `source_snapshot_hash`) are machine-maintained.

## Freshness Expectations

- Last durable trigger: `observer-rebuild` / `Session stop`
- Observer snapshot source hash: `e4e14cd055d7`
- Run `context-copilot codebase-docs validate` when changing docs policy or major runtime behavior.
<!-- context-copilot:end section=doc-policy -->
