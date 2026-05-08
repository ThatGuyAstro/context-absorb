# Context Absorb

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/ThatGuyAstro/context-absorb/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tested on macOS](https://img.shields.io/badge/tested%20on-macOS-lightgrey.svg)](https://github.com/ThatGuyAstro/context-absorb)

Context Absorb is a small cross-CLI session transfer tool for people who run multiple AI coding sessions in parallel and need to move context between them without manual copy-paste. It provides one shared command, `session-absorb`, plus two thin skill wrappers so the same workflows are available from both Claude Code and Codex.

The core problem it solves is practical rather than theoretical: when one session has already explored a codebase, fixed a bug, produced a design direction, or investigated a runtime issue, another session should be able to absorb the important context quickly. Instead of pasting long transcript fragments back and forth, Context Absorb finds the relevant session, extracts usable material, ranks the most relevant excerpts, writes a bridge brief when needed, and can launch a follow-up session in the appropriate CLI.

## Quick Start

Prerequisites:

- Python 3.10+ (uses PEP 604 `X | Y` union syntax)
- macOS (Linux/Windows fallbacks planned, see Platform support below)
- Claude Code CLI and/or Codex CLI installed locally

```bash
# 1. Install runtime, shell command, and both skill wrappers
./session-absorb install --repo-root "$(pwd)"

# 2. Add a shell alias for instant invocation from inside Claude Code
echo 'alias sa="$HOME/.local/bin/session-absorb"' >> ~/.zshrc
source ~/.zshrc

# 3. List your sessions (chat-safe table inside Claude Code, curses picker in a real terminal)
sa list --limit 10
```

## Demo

_Asciinema demo coming soon - see scripts/demo-asciinema.sh_

### Daily fast paths

Inside Claude Code, prefix any invocation with `!` to bypass Claude entirely (~250ms, no LLM thinking):

| You type | What happens |
|---|---|
| `!sa here` | Digest the most-recent non-self session in this cwd |
| `!sa here ask --question "what changed?"` | Ask a targeted question of the cwd-default session |
| `!sa here launch` | Open a native fork of the cwd-default session in a new Terminal |
| `!sa last` | Digest the most-recent non-self session across all cwds |
| `!sa fork-myself` | Fork THIS active session into a new Terminal (continues the current conversation in a separate window) |
| `!sa list --active-only` | Show only sessions updated in the last 240 minutes |
| `!sa digest --source claude --session TMS121` | Direct dispatch by alias code |

For a clickable in-chat picker that walks you through session + action selection, use `/absorb` (slow on Opus high-think but conversational).

## What The Project Does

At a high level, the project is a transcript-aware bridge between:

- `codex` sessions stored under `~/.codex`
- `claude` sessions stored under `~/.claude`

It supports four main jobs:

1. **Session discovery and management**
   - list recent sessions across both tools with an interactive arrow-key picker or flat table
   - filter by source, cwd, title/session query, or active-only
   - auto-assign short mnemonic alias codes on session start (e.g. `TMS01`, `COAB01`)
   - auto-prefix newly launched native session titles with that code when the startup hook can reach the local session metadata
   - manually assign or override short alias codes (e.g. `DASH1`, `OPS42`) for fast targeting
   - track session state (active, idle, missing) in a SQLite catalog

2. **Context extraction**
   - build compact digests for a session
   - answer targeted questions from a session
   - rank transcript excerpts against a question

3. **Context transfer**
   - launch a native same-platform fork when possible
   - generate a bridge brief for cross-platform handoff
   - open a new Terminal session that starts from the generated brief

4. **Session catalog**
   - all discovered sessions are synced into `~/.local/share/session-absorb/sessions.db`
   - state is computed from recency (active window: 240 minutes by default)
   - the `db` subcommand exposes counts and recent entries

5. **Live web monitoring**
   - a local dashboard can stream live session state, aliases, source split, and hot projects
   - the web app is served directly by the shared Python runtime, with no extra framework dependency

## Why It Exists

The design assumes a real working style: multiple sessions may be open at once, often in the same repository, but each has only partial context. One session may have:

- explored the repo and identified the right files
- completed a bug investigation
- refined UI direction
- validated commands and runtime behavior
- gathered the exact evidence needed for a follow-up implementation pass

Without a bridge, that context is trapped inside the original session unless the user manually restates it. Context Absorb turns session history into reusable operational artifacts.

## Repository Layout

The repository is intentionally small.

- `session-absorb`
  - repo-local shell wrapper
  - useful during development inside this checkout
- `skills/shared/session_absorb_core.py`
  - the main implementation
  - handles discovery, extraction, ranking, launching, and installation
- `skills/codex/session-absorb/`
  - Codex-facing skill wrapper
  - contains a Codex `SKILL.md` and `agents/openai.yaml`
- `skills/claude/session-absorb/`
  - Claude Code-facing skill wrapper
  - contains a Claude `SKILL.md`
- `docs/codebase/`
  - generated durable project docs
- `.session-absorb/briefs/`
  - generated handoff briefs written by the tool

## How It Works

The shared runtime reads both tools’ local session metadata and transcript stores.

### Codex session discovery

Codex sessions are discovered from:

- `~/.codex/session_index.jsonl`
- transcript files under `~/.codex/sessions/**`

The runtime loads session IDs and thread names from the index, then resolves the matching transcript file and infers the original cwd from the transcript’s `session_meta` record.

### Claude session discovery

Claude sessions are discovered from:

- `~/.claude/sessions/*.json`
- transcript files under `~/.claude/projects/**`

The runtime uses the Claude session header to get the session ID, cwd, and display name, then resolves the project transcript based on the cwd-derived project slug or a direct recursive lookup.

### Transcript extraction

After locating a session, the runtime parses the transcript and extracts:

- user messages
- assistant messages
- tool usage counts
- selected tool outputs for Codex when those outputs are useful context

It also strips obvious noise such as slash-command boilerplate, task notifications, and local command caveats so the resulting material is easier to reuse.

### Ranking and question answering

The `ask` flow tokenizes the user’s question, scores transcript excerpts by term hits plus recency, and returns the highest-signal snippets. This is the fallback path for any situation where a true live handoff is unavailable or unreliable.

### Brief-driven transfer

When direct reuse is not practical, the tool writes a Markdown brief into:

- `.session-absorb/briefs/`

Each brief captures:

- source platform
- session ID
- title and cwd
- dominant tools
- recent user prompts
- recent assistant responses
- highest-signal excerpts
- instructions for the receiving session

That brief becomes the compressed artifact another session can absorb.

## Native vs Fallback Transfer

The project deliberately uses a hybrid model.

### Same-platform transfer

When the source and target CLI are the same, Context Absorb prefers native handoff:

- `codex -> codex` uses `codex fork`
- `claude -> claude` uses `claude -r <session> --fork-session`

This is the cleanest path because the target session stays within the original platform’s native conversation model.

### Cross-platform transfer

For cross-platform moves, the tool generates a bridge brief and launches a fresh session in the target CLI with a prompt telling it to read the brief first.

### Why the fallback exists

The fallback is not an edge case. It is a core part of the design.

- Codex does not expose a reliable non-interactive resume/fork path for live session questioning.
- Claude supports live questioning with `claude -p -r ... --fork-session`, but some sessions can fail with stale deferred-tool marker errors.

Because of that, transcript-backed extraction and brief generation are the reliability path, not just the backup plan.

## Installation Model

The project now installs globally in a tool-agnostic way.

Running:

```bash
session-absorb install --repo-root "$(pwd)"
```

installs:

- runtime: `~/.local/share/session-absorb/session_absorb_core.py`
- web app: `~/.local/share/session-absorb/webapp/`
- shell command: `~/.local/bin/session-absorb`
- SessionStart hook launchers: `~/.local/share/session-absorb/session-start-hook-{codex,claude}.sh`
- Codex skill: `~/.codex/skills/session-absorb/`
- Claude skill: `~/.claude/skills/session-absorb/`
- SessionStart hook registrations in `~/.codex/hooks.json` and `~/.claude/settings.json`

This means the repo checkout is used as the installation source, but the installed runtime and skills do not depend on the repo continuing to exist at the same path.

### Platform support

Currently macOS-only: native session launches use AppleScript to open Terminal windows. Linux and Windows fallbacks are planned and being implemented as part of this release. Core transcript discovery, ranking, digesting, and brief generation already work cross-platform; only the `launch` subcommand and `--open-terminal` flag are macOS-gated today.

### Hook security note

> The `install` command registers `SessionStart` hooks in `~/.codex/hooks.json` and `~/.claude/settings.json`. Those hooks invoke two scripts written into `~/.local/share/session-absorb/session-start-hook-{codex,claude}.sh`. The hooks only:
>
> - assign a short mnemonic alias code (e.g. `TMS01`) to the new session
> - prefix the native session title with that code when the platform allows
>
> They do not exfiltrate data, do not make network calls, and read only your own local Claude/Codex session metadata. The script source is part of this repo and inspectable before install. To skip hook registration entirely, pass `--no-hooks` to `install` (planned flag - track its rollout in CHANGELOG).

## Command Surface

The shared CLI exposes twelve subcommands, grouped by use case. When invoked with no subcommand, it defaults to `list` with the right rendering for the context (interactive picker in a real terminal, chat menu in a non-TTY).

### Discovery

- `list` - list recent sessions from both tools
  - opens an interactive curses picker in real terminals; `--plain` for flat output; `--chat-menu` (or non-TTY) for a numbered markdown menu
  - on Enter in the curses picker, opens an action menu (digest / ask / brief / launch-native / launch-claude / launch-codex / print / cancel). `--select-only` preserves the old print-and-exit behavior
  - `--active-only` limits to sessions updated within the active window
  - JSON output includes `is_current: true` for the row matching `CLAUDE_CODE_SESSION_ID`
- `pick` - select an entry from the most recent chat-menu snapshot by number
- `init` - assign a short alias code to a session and prefix its native title
  - shortlist mode when called without `--session`; supports natural-language positional query: `session-absorb init trade mirror`

### Action

- `digest` - summarize one session
- `ask` - answer a question from the transcript or, for Claude, try a live query first
- `brief` - write a Markdown handoff brief
- `launch` - launch a native fork or brief-driven handoff in Terminal

### Shortcuts (zero-LLM fast paths)

- `here [action]` - run an action on the most recent non-self session in current cwd. Default action: `digest`. Available actions: `digest`, `ask`, `brief`, `launch`, `show`
- `last [action]` - same as `here` but searches all cwds, not just the current one
- `fork-myself` - fork the user's CURRENT active session into a new Terminal (reads `CLAUDE_CODE_SESSION_ID` / `CODEX_SESSION_ID`). Optional `--question` for a starting prompt; `--dry-run` to preview the shell command

### Infrastructure

- `db` - inspect the SQLite session catalog: state counts, recent entries, database path
- `install` - install the runtime and all skill wrappers globally
- `web` - serve the local live dashboard and JSON stream

### Visual cues

Output distinguishes Claude vs Codex sessions consistently:

- **Chat menu (markdown)**: `◆C` filled diamond for Claude, `◇X` hollow diamond for Codex, with a legend line above the table
- **TTY / curses picker**: 256-color ANSI - Claude in orange (`38;5;214`), Codex in cyan (`38;5;51`). Honors `NO_COLOR` and `FORCE_COLOR`
- **`/absorb` AskUserQuestion picker (Claude Code chat)**: colored emoji `🟠` for Claude, `🟢` for Codex, `📋` for the manual-pick escape option (Claude Code's chat does not render ANSI, so colored emoji are the only intrinsic-color path)
- **Self detection**: when `CLAUDE_CODE_SESSION_ID` (or `CODEX_SESSION_ID`) matches a row, it is annotated with `*self*` in plain output and emitted with `is_current: true` in JSON output. The `/absorb` skill filters these out so users cannot accidentally try to digest their own active session

Examples:

```bash
session-absorb list --limit 20
session-absorb init --session 1 --code DASH1
session-absorb init --session latest
session-absorb digest --source claude --session DASH1
session-absorb ask --source codex --session OPS42 --question "What changed?"
session-absorb brief --source claude --session <session-id> --question "Absorb and continue"
session-absorb launch --source claude --session DASH1 --target codex --question "Continue implementation from this work."
session-absorb db --json
session-absorb web --open-browser
```

## How The Skill Wrappers Fit In

This project does not use one single skill package for both tools. Instead it uses:

- one shared runtime
- one shared shell command
- three skill wrappers: `claude/session-absorb`, `claude/absorb` (alias), and `codex/session-absorb`

This split is necessary because Claude Code and Codex discover and interpret skills differently. The behavior is shared, but the packaging layer is platform-specific.

### `/absorb` skill (Claude Code alias)

`skills/claude/absorb/SKILL.md` is a Claude-only alias of `/session-absorb`, optimized for the common case: "digest the sibling Claude session in this directory." Routing tree:

| Invocation | Path | Behavior |
|---|---|---|
| `/absorb` | A: cwd auto-default | If exactly one non-self session lives in `$PWD`, jump straight to the action picker. If 2+ candidates, show a session picker first. After a session is selected, present 4 primary actions (Digest / Fork native / Handoff to other CLI / More). |
| `/absorb here` | B: shortcut | Pass-through to `session-absorb here`. Digest most-recent non-self session in `$PWD`, no confirmation. |
| `/absorb last` | B: shortcut | Pass-through to `session-absorb last`. Digest most-recent non-self session anywhere. |
| `/absorb pick` | B: shortcut | Force the multi-step click picker (browse all sessions). |
| `/absorb fork-myself` | B: shortcut | Pass-through to `session-absorb fork-myself`. Forks the current active session into a new Terminal. |
| `/absorb <subcommand> [args]` | C: pass-through | Direct call to `session-absorb` (e.g. `/absorb digest --source claude --session TMS121`). |
| `/absorb <free text>` | D: Haiku dispatch | Subagent resolves intent (`session + verb`) and runs the right command in one shot (e.g. `/absorb digest the UI session`). |

The Path A action menu has 4 primary options and a "More" submenu:

| Primary action | Resulting command |
|---|---|
| 🔍 Digest | `session-absorb digest --source <s> --session <c>` |
| 🚀 Fork (native) | `session-absorb launch --source <s> --session <c> --mode native` |
| 🤝 Handoff to other CLI | `session-absorb launch --source <s> --session <c> --target <other-cli>` |
| 🎯 More | secondary menu: 🔎 Ask question / 📝 Brief only / 🪞 Fork myself / ↩️ Back |

Default question text for `ask` and `brief` actions is hard-coded so the user is never prompted for question text - it skips a full LLM turn. Custom questions go through Path D (`/absorb ask why X failed in TMS121`) or explicit subcommand pass-through.

For zero-LLM-latency invocation, the install step adds the runtime to `~/.local/bin`. Pair with a shell alias:

```bash
# in ~/.zshrc
alias sa="$HOME/.local/bin/session-absorb"

# in Claude Code chat (bang prefix bypasses Claude entirely)
!sa list --active-only
!sa digest --source claude --session TMS121
!sa here                # digest cwd-default sibling session
!sa here ask --question "what changed?"
!sa fork-myself         # fork current session into a new Terminal
```

### Self-detection

The runtime reads `CLAUDE_CODE_SESSION_ID` and `CODEX_SESSION_ID` from the environment and emits an `is_current: true` JSON flag on the matching session. Plain-text outputs append a `*self*` marker. All slash-command pickers filter `is_current` so you cannot ask/digest your own active session (its transcript is mid-write and unreadable).

### Visual differentiation between Claude and Codex

| Surface | Claude | Codex |
|---|---|---|
| AskUserQuestion option labels | `🟠` orange circle | `🟢` green circle |
| Plain-text chat menu | `◆C` filled diamond | `◇X` hollow diamond |
| TTY (`--plain`, terminal) | ANSI 256-color 214 (orange) | ANSI 256-color 51 (cyan) |
| Curses interactive picker | bold orange source column | bold cyan source column |

ANSI color is emitted only when stdout is a TTY (or `FORCE_COLOR=1`). Honors `NO_COLOR`. Chat surfaces use emoji color because Claude Code's chat does not render escape codes.

## Current Limitations

- no formal unit test suite is committed yet
- no git history exists in this checkout, so commit conventions are documented rather than inferred
- live Claude questioning may fail on some resumed sessions with stale deferred-tool marker errors
- Codex live non-interactive interrogation is not available, so transcript ranking is the main path there
- the tool assumes local access to both CLIs’ session stores from the same machine
- Terminal launch uses macOS AppleScript and will not work on Linux
- the ranking model is lexical, not semantic

## Development And Validation

The most useful validation is targeted and operational:

```bash
python3 -m py_compile skills/shared/session_absorb_core.py
session-absorb --help
session-absorb list --limit 5
session-absorb digest --source claude --session <id>
session-absorb ask --source codex --session <id> --question "What changed?"
```

If you change launch behavior, validate both:

- same-platform native fork behavior
- cross-platform brief generation and launch

## Summary

Context Absorb is a pragmatic session-bridge utility for parallel AI coding workflows. It is not trying to unify Claude Code and Codex internally. Instead, it treats both as separate ecosystems, reads their local session stores, extracts the reusable parts of prior work, and turns them into something another session can immediately consume. That design choice is the reason the tool is simple, local-first, and durable even when native resume/fork behavior is inconsistent across platforms.
