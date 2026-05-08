# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `handoff` subcommand for structured cross-session work transfer with optional note fields (`--done`, `--pending`, `--blocked`) and acknowledgment tracking.
- `inbox` subcommand to show pending handoffs targeted at the current cwd, CLI, or session id.
- `ack` subcommand to mark a handoff as absorbed by the receiving session.
- New `handoffs` SQLite table at `~/.local/share/session-absorb/sessions.db` for handoff state tracking.
- Brief writer now prepends a `## Handoff Notes` section (What's done / What's pending / What's blocked) when handoff notes are supplied.
- Dedicated top-level slash commands `/handoff`, `/inbox`, and `/ack` as thin alias skills - no need to remember `/absorb handoff ...` pass-through syntax.

### Fixed

- Inbox cwd prefix matching is now case-insensitive on macOS and Windows where the filesystem itself is case-insensitive. A handoff stored with `/Users/sam/proj` will be found when the receiver's `os.getcwd()` returns `/Users/Sam/Proj`. Linux behavior unchanged (case-sensitive). Target cwd values are also normalized through `os.path.realpath` at insert time when the path exists. New regression test in `tests/test_handoff.py`.

## [0.1.0] - 2026-05-08

### Added

- `session-absorb` CLI with 12 subcommands across 4 categories: discovery (`list`, `pick`, `init`), action (`digest`, `ask`, `brief`, `launch`), shortcuts (`here`, `last`, `fork-myself`), infrastructure (`db`, `install`, `web`).
- Native Claude / Codex session discovery from `~/.claude/sessions` and `~/.codex/sessions`.
- Cross-CLI bridge briefs written to `.session-absorb/briefs/`.
- Native fork launch (Claude `claude -r ... --fork-session`; Codex `codex fork`).
- SQLite session catalog at `~/.local/share/session-absorb/sessions.db`.
- Live web dashboard via `session-absorb web --open-browser`.
- Claude Code skill wrappers: canonical `/session-absorb` and `/absorb` alias.
- `/absorb` skill with 4 routing paths: cwd auto-default click picker, native shortcut pass-through, subcommand pass-through, Haiku natural-language dispatch.
- Self-detection via `CLAUDE_CODE_SESSION_ID` and `CODEX_SESSION_ID` env vars; current session is filtered from pickers and tagged `*self*` in plain output / `is_current: true` in JSON.
- Visual differentiation across surfaces: `◆C` / `◇X` Unicode badges in chat menus, ANSI 256-color in TTY (orange Claude, cyan Codex), colored emoji `🟠` / `🟢` in `AskUserQuestion` pickers.
- Cross-platform Terminal launcher: macOS AppleScript, Linux (`x-terminal-emulator`, `gnome-terminal`, `konsole`, `xterm`, etc.), Windows (`wt.exe`, `cmd.exe`).
- One-line installer (`install.sh`) and pyproject.toml for pip-friendly distribution.
- Pytest smoke test suite and GitHub Actions CI matrix (macOS + Ubuntu, Python 3.10 / 3.11 / 3.12).
- MIT license.

[Unreleased]: https://github.com/ThatGuyAstro/context-absorb/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ThatGuyAstro/context-absorb/releases/tag/v0.1.0
