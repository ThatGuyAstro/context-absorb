# Architecture

How Context Absorb is put together, and why it ended up this shape.

## What we built and why

Context Absorb moves working context between Claude Code and Codex CLI sessions without a server, an account, or a sync layer. Everything runs locally against the JSONL transcripts both CLIs already write to disk. That decision drives the rest of the design: discovery is filesystem-driven, the catalog is a SQLite file in your home directory, and when a live cross-CLI handoff isn't possible we fall back to a Markdown brief that any agent can read. The user surface is a pair of slash commands (`/absorb` in Claude Code, `/session-absorb` in Codex) backed by a single Python runtime; the CLI underneath stays usable on its own for power users and shell aliases.

## Core Objects

Two dataclasses do most of the work in `skills/shared/session_absorb_core.py`. See the source for the full field list.

**`SessionRecord`** - one discovered session, normalized across both platforms. Carries the source (`claude` / `codex`), session id, title, cwd, transcript path, capability flags (`live_ask_supported`, `native_fork_supported`), the short alias code if one's been assigned, and a computed activity state.

**`Excerpt`** - one cleaned fragment from a transcript: index, timestamp, role, and text. Digests, question packs, and bridge briefs all render from a list of these.

## Discovery Pipeline

### Codex

Primary index: `~/.codex/session_index.jsonl`. Transcripts: `~/.codex/sessions/**`. We resolve the latest transcript for a given session id, then read `session_meta` to recover the cwd the session was started from.

### Claude

Sessions live in `~/.claude/sessions/*.json`; transcripts live under `~/.claude/projects/**` in cwd-derived directories. We compute the expected project slug from the cwd first and only fall back to a recursive search when that misses.

## Alias System

`init` assigns a short code to a session so you can target it without typing a UUID.

- Codes are stored in `~/.local/share/session-absorb/aliases.json`.
- Custom codes are 1-8 alphanumeric characters and get uppercased.
- Auto-generated codes are a SHA1 hash with a platform prefix: `CLD` for Claude, `CDX` for Codex (e.g. `CLD4A2F`).
- `init` also rewrites the native session title to `[CODE] Original Title` so the code shows up in the host CLI's own session picker.
- After init, every command that takes `--session` accepts the alias code.

Resolution order: exact session id, exact alias, session id prefix, title prefix. Ambiguous matches print a disambiguation list.

## Session Catalog

Every `list` or resolve call syncs discovered sessions into SQLite at `~/.local/share/session-absorb/sessions.db`. The catalog tracks source + session id (composite primary key), alias, title, cwd, `updated_at`, `last_seen_at`, `last_state`, `first_seen_at`, `seen_count`, transcript path and existence, plus the two capability flags.

Activity state uses a configurable active window (default 240 minutes). Sessions absent from the latest sync are flagged `missing` instead of being deleted, so you can see what dropped off. The `db` subcommand reads the catalog directly.

## Interactive Menu

When `list` runs in a real TTY (both stdin and stdout), it opens a curses arrow-key picker instead of printing a flat table:

- arrow keys plus j/k for navigation, page up/down for long lists
- Enter selects, q cancels
- footer shows the full session id and cwd
- 256-color highlighting on the source column (orange for Claude, cyan for Codex)
- `*self*` annotation on the user's currently-running session

After Enter, a second curses screen offers actions: digest, ask, brief, launch-native, launch-claude, launch-codex, print, cancel. Dispatch happens in-process: we build an `argparse.Namespace` and call the matching `command_*` function. For ask/brief/launch-bridge actions the picker exits curses cleanly first, then prompts for the question text via plain `input()`.

`--select-only` keeps the older print-and-exit behavior for callers that just want a session resolved.

From non-interactive contexts (slash commands, pipes), `--open-terminal` relaunches in a macOS Terminal window via AppleScript. For pure markdown rendering inside Claude Code's chat (where curses cannot run), `--chat-menu` emits a numbered table with a snapshot id that `pick <n>` resolves later.

## Visual Differentiation

Source identity has to survive three rendering surfaces: a chat surface that doesn't render ANSI, a real terminal that does, and Claude Code's `AskUserQuestion` picker which renders neither curses nor ANSI but does render emoji. So we encode source three ways:

| Surface | Encoding |
|---|---|
| Plain markdown (chat menu) | Filled vs hollow Unicode diamonds: `◆C` for Claude, `◇X` for Codex, plus an explicit legend line |
| TTY (curses + `--plain`) | 256-color ANSI (`38;5;214` orange Claude, `38;5;51` cyan Codex), wrapped in `source_label()` which honors `NO_COLOR` and `FORCE_COLOR` |
| `AskUserQuestion` picker | Colored emoji glyphs: `🟠` Claude, `🟢` Codex, `📋` manual escape |

The skill prompts pick the right encoding for the surface they're rendering into. `SKILL.md` for `/absorb` mandates the colored emoji set for AskUserQuestion options.

## Self-Session Detection

The runtime reads `CLAUDE_CODE_SESSION_ID` (and falls back to `CODEX_SESSION_ID`) from the subprocess environment. When the env var matches a discovered session:

- JSON output gets `is_current: true` for that record
- the plain table and curses picker append a `*self*` suffix
- `/absorb` filters the current session out of the AskUserQuestion picker entirely via `jq 'select(.is_current != true)'`, because the active session's transcript is mid-write and can't be digested or queried until it flushes

## Extraction Pipeline

Extraction is conservative. We walk the JSONL transcript line by line and pull user messages and assistant turns. Tool usage gets counted separately rather than promoted into excerpts. For Codex we also keep `function_call_output` entries because those sometimes contain the only operationally useful data (rate-limit telemetry, command output, error payloads). Known transcript noise gets stripped early through `sanitize_excerpt_text()`: slash-command boilerplate, task notifications, local command caveats, skill base-directory headers.

This keeps the downstream ranker simple while preserving the things that actually matter for handoff.

## Ranking Model

Lightweight on purpose:

- tokenize the question into words (3+ chars, stopwords excluded)
- count per-term hits per excerpt
- boost exact full-question matches by +4
- add a recency factor (position / total)
- combine: `score = term_hits * 3 + recency`
- sort by combined score, ties break by recency

This isn't semantic retrieval, it's local lexical ranking with a recency bias. The tradeoff buys zero dependencies and predictable behavior. If no terms match, we fall back to the most recent excerpts.

## Transfer Modes

### Native mode

Same-platform handoff goes through the host CLI's own resume:

- Codex: `codex fork <session-id>`
- Claude: `claude -r <session-id> --fork-session`

### Brief mode

Used when transfer is cross-platform, or when native live interrogation isn't available or isn't reliable. Brief mode writes a Markdown artifact into `.session-absorb/briefs/` and launches the target CLI with a prompt that tells it to read that artifact before doing anything else.

### Launch mechanics

Both modes open a new macOS Terminal window via AppleScript. `--dry-run` prints the exact shell command without executing it.

## Installation Architecture

`install` is home-scoped and copies (not symlinks) so the installed runtime survives if you delete the repo:

- runtime: `~/.local/share/session-absorb/session_absorb_core.py`
- web app: `~/.local/share/session-absorb/webapp/`
- session-start hooks: `~/.local/share/session-absorb/session-start-hook-{codex,claude}.sh`
- shell wrapper: `~/.local/bin/session-absorb`
- skill copies: `~/.codex/skills/session-absorb/` and `~/.claude/skills/session-absorb/`
- `~/.claude/skills/absorb/` when `skills/claude/absorb/` exists in the repo (the Claude-only `/absorb` alias)

`--force` overwrites existing targets.

## `/absorb` Skill (Claude Code alias)

`skills/claude/absorb/SKILL.md` is a Claude-only alias on top of the shared runtime, tuned for in-chat interaction. It has four execution paths:

1. **Bare `/absorb`** - fetches the session list as compact JSON (piped through `jq -c` so the auto-displayed tool-call preview stays one line), splits into `local` (cwd matches) and `recent` (top across all cwds), filters out the current session via `is_current`, and renders a clickable picker via `AskUserQuestion` with colored emoji badges. If exactly one local session exists, the session picker is skipped and the flow jumps straight to the action picker. The action picker has 4 primary options (Digest, Fork native, Handoff to other CLI, More) plus a secondary submenu (Ask, Brief only, Fork myself, Back).

2. **Shortcuts** - `/absorb here`, `/absorb last`, `/absorb pick`, `/absorb fork-myself` are direct pass-throughs to native CLI subcommands. Session matching, self-filtering, and action dispatch all happen in pure Python with no LLM thinking beyond loading the skill.

3. **Known subcommand pass-through** - when the first argument is one of `list|pick|init|digest|ask|brief|launch|here|last|fork-myself|db|web|install`, the skill invokes `session-absorb {{ARGUMENTS}}` directly with no LLM reasoning beyond skill load.

4. **Natural-language Haiku dispatch** - free-text intents trigger an `Agent` tool call with `subagent_type: general-purpose, model: haiku`. The Haiku subagent reads the JSON session list, matches the user's intent to a session and action verb, and runs the right `session-absorb` command via `Bash`. This moves resolution out of the parent session's high-effort thinking budget. Subagent output may be reformatted vs raw stdout - a known Haiku tool-following limitation.

For zero-LLM invocation, install a shell alias (`alias sa="$HOME/.local/bin/session-absorb"`) and use Claude Code's bang prefix: `!sa here` runs the shell command directly with no LLM round-trip and no thinking budget (~250ms wall time). The slash commands stay the headline path for everyone else.

## Native Shortcut Subcommands

`here`, `last`, and `fork-myself` are first-class CLI subcommands rather than skill-only shortcuts. Putting them in the runtime buys three things:

1. **Zero-LLM speed** - invokable via `!sa here` (Claude Code bang prefix), `sa here` (real shell), or any pipeline. No skill load, no Claude turn, no thinking budget.
2. **Composable** - each accepts an action argument (`digest`/`ask`/`brief`/`launch`/`show`) and optional `--question`, so the full action surface is reachable without going through the slash-command UI.
3. **Self-aware** - `here` and `last` filter the current session via `CLAUDE_CODE_SESSION_ID` / `CODEX_SESSION_ID`. `fork-myself` does the inverse: it requires the env var to be set and forks specifically the user's own session.

`here` and `last` share `_shortcut_dispatch()`, which builds a candidate list, optionally filters by `cwd == os.getcwd()`, sorts by recency, then constructs the right `argparse.Namespace` and calls the matching `command_*` function in-process.

`fork-myself` reads the env var, looks up the live `SessionRecord` (or synthesizes one from cwd if the catalog hasn't seen it yet), then calls `shell_command_for_native_fork()` and `open_in_terminal()` to spawn the new window. Source detection: `CLAUDE_CODE_SESSION_ID` set means `claude`; `CODEX_SESSION_ID` set means `codex`.

## Known Constraints

- Codex has no dependable non-interactive live interrogation path right now. Cross-CLI questions against a Codex session always go through transcript ranking.
- Claude live interrogation works, but resumed sessions sometimes fail with stale deferred-tool marker errors. When that happens we fall back to the transcript pack rather than retrying.
- Both tools' session stores need to be reachable from the same machine. There's no remote mode.
- Terminal launch goes through macOS AppleScript. Linux and Windows fallbacks exist but aren't exercised in day-to-day use yet.
- Ranking is lexical, not semantic. A question phrased very differently from how the topic appears in the transcript can miss relevant excerpts.
- Claude Code's chat surface isn't a terminal emulator: a curses TUI cannot render inside the chat box. The closest in-chat interactive primitive is `AskUserQuestion`, which is what `/absorb` uses. `--open-terminal` is the only way to get the curses picker visible from a slash-command context, and it spawns a separate macOS Terminal window.
- A skill cannot override the parent session's thinking effort. Running the skill inside an Opus-with-high-thinking session pays that latency on every LLM round-trip. Subagent dispatch with `model: haiku` routes around this for one-shot natural-language flows but doesn't help interactive multi-turn pickers, since subagent output isn't visible to the user.

These constraints are why transcript extraction and bridge briefs are first-class parts of the system rather than a fallback nobody planned for.
