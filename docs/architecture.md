# Architecture

This document explains the internal design of Context Absorb and the reasoning behind its implementation choices.

## Design Philosophy

The project is built around one core assumption: cross-session transfer should be local, inspectable, and operationally simple. That leads to four design choices:

1. **Local-first**
   - read the session stores already present on disk
   - avoid external services and synchronization layers

2. **Shared core, thin wrappers**
   - keep logic in one Python runtime
   - keep Claude and Codex skill packages as documentation and routing layers

3. **Reliability over elegance**
   - use native resume/fork only when it is actually dependable
   - degrade to transcript-based transfer when live handoff is not robust

4. **Artifact-oriented transfer**
   - emit digests and bridge briefs as plain Markdown
   - make intermediate outputs readable and reusable by humans and agents

## Core Objects

The runtime centers on two dataclasses:

### `SessionRecord`

Represents a discovered session across either platform:

- `source` - `"codex"` or `"claude"`
- `session_id` - the platform's native UUID
- `title` - display name
- `cwd` - working directory the session was started from
- `updated_at` - last modification timestamp
- `transcript_path` - resolved path to the JSONL transcript
- `live_ask_supported` - whether live forked questioning works
- `native_fork_supported` - whether native fork launch works
- `alias_code` - short code assigned via `init` (e.g. `DASH1`, `OPS42`)
- `state` - computed activity state: `"active"`, `"idle"`, or `"unknown"`

This gives the rest of the system a normalized view over two different session ecosystems.

### `Excerpt`

Represents one extracted transcript fragment:

- `index` - ordinal position in the transcript
- `timestamp` - ISO timestamp from the transcript row
- `role` - `"user"`, `"assistant"`, or `"tool"`
- `text` - cleaned and normalized content

Everything downstream, including digest rendering, question packs, and brief generation, works from these normalized excerpts.

## Discovery Pipeline

### Codex

Codex discovery uses `~/.codex/session_index.jsonl` as the primary index and `~/.codex/sessions/**` as the transcript source of truth. The runtime resolves the latest transcript for a given session ID and then inspects `session_meta` to recover the session cwd.

### Claude

Claude discovery starts from `~/.claude/sessions/*.json` and resolves transcripts from `~/.claude/projects/**`. Because Claude project transcript directories are cwd-derived, the runtime builds the expected project slug first and only falls back to a recursive search if needed.

## Alias System

The `init` subcommand assigns short codes (e.g. `DASH1`, `CLD4A2F`) to sessions for fast targeting.

- Codes are stored in `~/.local/share/session-absorb/aliases.json`
- A custom code is 1-8 alphanumeric characters, auto-uppercased
- Auto-generated codes use a SHA1 hash with a platform prefix (`CLD` for Claude, `CDX` for Codex)
- `init` also updates the native session title by prefixing it with the code in brackets: `[DASH1] Original Title`
- After init, all commands accept the alias code anywhere `--session` is expected

Session resolution checks in order: exact session ID match, exact alias code match, session ID prefix match, title prefix match. Ambiguous matches produce a disambiguation list.

## Session Catalog

Every time sessions are listed or resolved, the runtime syncs all discovered sessions into a SQLite database at `~/.local/share/session-absorb/sessions.db`.

The catalog tracks:

- source platform and session ID (composite primary key)
- alias code, title, cwd
- `updated_at` - last transcript modification
- `last_seen_at` - when the runtime last observed this session
- `last_state` - computed state: `active`, `idle`, or `missing`
- `first_seen_at` and `seen_count` - for observability
- transcript path and existence flag
- capability flags (live ask, native fork)

State computation uses a configurable active window (default: 240 minutes). Sessions not seen in the latest sync are marked `missing`.

The `db` subcommand exposes the catalog for inspection.

## Interactive Menu

When `list` is called from a real terminal (stdin and stdout are TTYs), it opens a curses-based arrow-key picker instead of printing a flat table. The picker supports:

- up/down arrows and j/k navigation
- page up/down for large lists
- Enter to select, q to cancel
- footer showing full session ID and cwd
- 256-color highlighting on the source column (orange Claude / cyan Codex)
- `*self*` annotation on the user's currently-running session

After a session is selected with Enter, a second curses screen opens with action choices: digest, ask, brief, launch-native, launch-claude, launch-codex, print, cancel. The selected action is dispatched in-process by building an `argparse.Namespace` and calling the matching `command_*` function. For ask/brief/launch-bridge actions, the picker exits curses cleanly and prompts for the question text via plain `input()`.

The `--select-only` flag preserves the older print-and-exit behavior for callers that just want a session resolved without dispatching an action.

From non-interactive contexts (slash commands, pipes), use `--open-terminal` to relaunch in a macOS Terminal window via AppleScript. For pure markdown rendering inside Claude Code's chat (where curses cannot run), the `--chat-menu` flag emits a numbered table with a snapshot id that `pick <n>` resolves later.

## Visual Differentiation

Source identity is preserved through every render path because Claude Code's chat surface does not render ANSI codes and curses cannot run inside it. Three tiers of visual encoding cover the three surfaces:

1. **Plain markdown (chat menu)**: filled vs hollow Unicode diamonds (`◆C` / `◇X`) plus an explicit legend line. Diamond shape difference is robust across every monospace renderer.
2. **TTY (curses + `--plain`)**: 256-color ANSI escape sequences (`38;5;214` orange for Claude, `38;5;51` cyan for Codex). Wrapped via a `source_label()` helper that honors `NO_COLOR` and `FORCE_COLOR`.
3. **Claude Code AskUserQuestion picker**: colored emoji glyphs (`🟠` Claude, `🟢` Codex, `📋` manual escape). This is the only chat-native primitive that carries intrinsic color in a non-terminal markdown context.

The choice tree is enforced by skill prompts so the right encoding is used for each surface (`SKILL.md` for the `/absorb` Claude alias mandates the colored emoji set for AskUserQuestion options).

## Self-Session Detection

The runtime reads `CLAUDE_CODE_SESSION_ID` (and falls back to `CODEX_SESSION_ID`) from subprocess environment. When the env var is present and matches a discovered session's id, the runtime:

- emits `is_current: true` in JSON output for that record
- appends a `*self*` suffix in plain table and curses picker output
- the `/absorb` skill uses `jq 'select(.is_current != true)'` to drop the current session from the AskUserQuestion picker entirely, since the active session's transcript is mid-write and cannot be digested or queried until it flushes

## Extraction Pipeline

Extraction is intentionally conservative.

- user and assistant messages are preferred
- tool usage is counted separately
- Codex `function_call_output` entries can be promoted into excerpts because they sometimes contain the most useful operational data
- known transcript noise is suppressed early through `sanitize_excerpt_text()`: slash-command boilerplate, task notifications, local command caveats, and skill base-directory headers

This design keeps the downstream ranking system simple while still preserving important context such as extracted rate-limit telemetry or command outputs.

## Ranking Model

The ranking model is lightweight by design:

- tokenize the question into words (3+ chars, stopwords excluded)
- count per-term hits in each excerpt
- boost exact full-question matches (+4)
- add a recency factor (position / total)
- combine: `score = term_hits * 3 + recency`
- sort by combined score, break ties by recency

This is not semantic retrieval. It is local lexical ranking plus recency bias. That tradeoff keeps the tool dependency-free and predictable. When no terms match, the system falls back to the most recent excerpts.

## Transfer Modes

### Native mode

Used when source and target are the same platform.

- Codex: `codex fork <session-id>`
- Claude: `claude -r <session-id> --fork-session`

### Brief mode

Used when:

- transfer is cross-platform
- native live interrogation is unavailable
- live interrogation is unreliable

Brief mode writes a Markdown artifact into `.session-absorb/briefs/` and launches the target CLI with a prompt that tells it to read that artifact before proceeding.

### Launch mechanics

Both modes open a new macOS Terminal window via AppleScript. The `--dry-run` flag prints the exact shell command without executing it.

## Installation Architecture

Installation is home-scoped and path-stable:

- runtime copied to `~/.local/share/session-absorb/session_absorb_core.py`
- web app copied to `~/.local/share/session-absorb/webapp/`
- session-start hook scripts written to `~/.local/share/session-absorb/session-start-hook-{codex,claude}.sh`
- shell wrapper written to `~/.local/bin/session-absorb`
- skill copies written into `~/.codex/skills/session-absorb/` and `~/.claude/skills/session-absorb/`
- `~/.claude/skills/absorb/` is also installed when `skills/claude/absorb/` exists in the repo (the Claude-only `/absorb` alias)

The `install` command copies files rather than symlinking, so the installed runtime does not depend on the repo checkout continuing to exist. The `--force` flag overwrites existing targets.

## `/absorb` Skill (Claude Code alias)

`skills/claude/absorb/SKILL.md` is a Claude-only alias that routes through the same shared runtime but defines a different default behavior optimized for in-chat interaction. It has four execution paths:

1. **Path A: bare `/absorb`** - fetches the session list as compact JSON (piped through `jq -c` so the auto-displayed tool-call preview stays a single line), splits into `local` (cwd matches) and `recent` (top across all cwds), filters out the current session via `is_current`, and renders a clickable picker via Claude Code's `AskUserQuestion` tool with colored emoji badges. If exactly one local session exists, the session picker is skipped and the flow jumps straight to the action picker. The action picker has 4 primary options (Digest, Fork native, Handoff to other CLI, More) plus a secondary submenu (Ask, Brief only, Fork myself, Back).

2. **Path B: shortcuts** - `/absorb here`, `/absorb last`, `/absorb pick`, and `/absorb fork-myself` are direct pass-throughs to native CLI subcommands. They invoke `session-absorb here`, `session-absorb last`, etc. with the same arguments. The session matching, self-filtering, and action dispatch all happen in pure Python with no LLM thinking beyond the skill load itself.

3. **Path C: known subcommand pass-through** - when the first argument is one of `list|pick|init|digest|ask|brief|launch|here|last|fork-myself|db|web|install`, the skill invokes `session-absorb {{ARGUMENTS}}` directly with no LLM reasoning beyond the skill load.

4. **Path D: natural-language Haiku dispatch** - free-text intents trigger an `Agent` tool call with `subagent_type: general-purpose, model: haiku`. The Haiku subagent reads the JSON session list, matches the user's intent to a session and action verb, and runs the right `session-absorb` command via `Bash`. This bypasses the parent session's high-effort thinking budget by moving the resolution into a Haiku subagent context. Subagent output may be reformatted vs raw stdout - a known Haiku tool-following limitation.

For zero-LLM invocation, the user can install a shell alias (`alias sa="$HOME/.local/bin/session-absorb"`) and use Claude Code's bang prefix: `!sa here` runs the shell command directly with no LLM round-trip and no thinking budget (~250ms wall time).

## Native Shortcut Subcommands

`here`, `last`, and `fork-myself` are first-class CLI subcommands rather than skill-only shortcuts. Putting them in the runtime gives three benefits:

1. **Zero-LLM speed**: invokable via `!sa here` (Claude Code bang prefix), `sa here` (real shell), or any pipeline. No skill needs to load, no Claude turn fires, no thinking budget is consumed.
2. **Composable**: each accepts an action argument (`digest`/`ask`/`brief`/`launch`/`show`) and optional `--question`, so the full action surface is reachable without going through the slash-command UI.
3. **Self-aware**: `here` and `last` automatically filter the current session via `CLAUDE_CODE_SESSION_ID` / `CODEX_SESSION_ID`. `fork-myself` does the inverse - it requires the env var to be set, then forks specifically the user's own session.

Implementation: `here` and `last` share `_shortcut_dispatch()` which builds a candidate list, optionally filters by `cwd == os.getcwd()`, sorts by recency, then constructs the right `argparse.Namespace` and calls the matching `command_*` function in-process.

`fork-myself` reads the env var, looks up the live `SessionRecord` (or synthesizes one from cwd if the catalog hasn't seen it yet), then calls `shell_command_for_native_fork()` and `open_in_terminal()` to spawn the new window. Source detection: `CLAUDE_CODE_SESSION_ID` set → `claude`; `CODEX_SESSION_ID` set → `codex`.

## Known Constraints

- Codex does not currently provide a dependable non-interactive live interrogation path.
- Claude live interrogation exists, but resumed sessions may fail with stale deferred-tool marker errors.
- The project assumes the user can access both tools' local session stores from the same machine.
- Terminal launch uses macOS AppleScript and will not work on Linux.
- The ranking model is lexical, not semantic: questions phrased differently from transcript content may miss relevant excerpts.
- Claude Code's chat surface is not a terminal emulator. A curses TUI cannot render inside the chat box - the closest in-chat interactive primitive is `AskUserQuestion`, which the `/absorb` skill uses. The `--open-terminal` flag is the only path to get the curses picker visible while running from a slash-command context, and it spawns a separate macOS Terminal window via AppleScript.
- Claude Code skills cannot override session-level thinking effort. A skill running inside an Opus-with-high-thinking session will pay that latency on every LLM round-trip. Subagent dispatch with `model: haiku` partially routes around this for one-shot natural-language flows but cannot help interactive multi-turn pickers (subagent output is not visible to the user).

These constraints are why transcript extraction and bridge briefs are first-class parts of the system rather than secondary fallbacks.
