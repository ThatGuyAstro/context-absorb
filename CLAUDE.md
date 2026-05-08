# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A cross-session context bridge tool (`session-absorb`) that reads JSONL transcripts from `~/.claude/sessions` and `~/.codex/sessions`, extracts ranked excerpts, and transfers context between Claude Code and Codex CLI sessions via native forks or generated brief files.

## Validation Commands

```bash
# Syntax check
python3 -m py_compile skills/shared/session_absorb_core.py

# CLI smoke test
python3 skills/shared/session_absorb_core.py list --limit 5

# Verify argument parsing
python3 skills/shared/session_absorb_core.py --help

# Native shortcuts (zero-LLM fast paths)
python3 skills/shared/session_absorb_core.py here show
python3 skills/shared/session_absorb_core.py last show
python3 skills/shared/session_absorb_core.py fork-myself --dry-run

# Test transcript parsing on a real session
python3 skills/shared/session_absorb_core.py digest --source claude --session <id>
```

No formal test suite exists. Validate every change with `py_compile` plus at least one real CLI smoke test.

## Architecture

All logic lives in one file: `skills/shared/session_absorb_core.py`. The Claude and Codex skill wrappers (`skills/claude/` and `skills/codex/`) are thin `runpy` trampolines that import the shared core. The repo-root `session-absorb` script is a bash wrapper that delegates to `~/.local/share/session-absorb/session_absorb_core.py` (installed copy).

Data flow: JSONL transcript files -> `extract_*_excerpts()` -> `rank_excerpts()` (keyword + recency scoring) -> output as digest, question pack, or bridge brief.

Key subcommands (12 total, by category):
- Discovery: `list`, `pick`, `init`
- Action: `digest`, `ask`, `brief`, `launch`
- Shortcuts (zero-LLM fast paths): `here [action]`, `last [action]`, `fork-myself`
- Infrastructure: `db`, `install`, `web`

Bare `session-absorb` (no subcommand) defaults to `list` with the right rendering for the context.

Persistent state: alias registry at `~/.local/share/session-absorb/aliases.json`, session catalog at `~/.local/share/session-absorb/sessions.db`, menu snapshots at `~/.local/share/session-absorb/menu-snapshots/`, and installed dashboard assets at `~/.local/share/session-absorb/webapp/`.
Startup hooks: `install` also registers `SessionStart` hooks in Codex and Claude so new sessions get mnemonic alias codes automatically and, when possible, a `[CODE] ...` native title prefix on launch.

Skill wrappers: three live in `skills/` - `skills/claude/session-absorb` (canonical), `skills/claude/absorb` (alias with AskUserQuestion picker + Haiku subagent dispatch), `skills/codex/session-absorb`.

## Important Constraints

- Claude sessions support live querying via `claude -p -r <session> --fork-session`. Codex does not expose non-interactive fork, so it always falls back to transcript-ranked excerpts.
- Same-platform transfer should use native fork. Cross-platform transfer should use a generated brief.
- Some resumed Claude sessions fail with stale deferred-tool markers: use transcript pack fallback, do not retry.
- The `install` command copies the shared runtime to `~/.local/share/session-absorb/` and skill wrappers to `~/.claude/skills/` and `~/.codex/skills/`.
- Claude Code's chat surface cannot host curses TUIs. The `--open-terminal` flag spawns a real macOS Terminal window for the curses picker. Inside the chat itself, use the `AskUserQuestion`-driven `/absorb` flow or the chat menu.
- Visual differentiation: `◆C`/`◇X` Unicode badges in chat menus, ANSI 256-color (orange Claude / cyan Codex) in TTY contexts, colored emoji `🟠`/`🟢` in AskUserQuestion option labels. Self detection via `CLAUDE_CODE_SESSION_ID` / `CODEX_SESSION_ID` env emits `is_current: true` JSON flag and `*self*` plain-text marker.

## Editing Guidelines

- Edit `skills/shared/session_absorb_core.py` first; keep the Claude and Codex skill wrappers as thin trampolines.
- After editing the core, copy to `~/.local/share/session-absorb/session_absorb_core.py` so installed runtime picks up the change. Skill wrapper edits in `skills/claude/absorb/SKILL.md` should be mirrored to `~/.claude/skills/absorb/SKILL.md`.
- Standard library only: no third-party dependencies.
- When rendering source labels, route through `source_label()` (TTY) or `source_badge()` (chat menu) instead of hardcoding strings, so visual differentiation stays consistent.
- `docs/codebase/` and `.context-copilot/` are generated runtime artifacts managed by context-copilot: do not edit manually.
