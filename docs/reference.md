# Command Reference

## Default invocation (no subcommand)

`session-absorb` with no arguments runs `list` with context-aware rendering:

- in a real terminal: opens the interactive curses picker
- non-TTY (e.g. inside a Claude Code Bash tool call): opens a chat-safe markdown menu

Use this when you want one-keystroke access to the picker from anywhere.

## `session-absorb list`

Lists recent Claude and Codex sessions.

When run in a real terminal (stdin and stdout are TTYs), it opens an interactive arrow-key picker by default. After picking a session with Enter, a second action menu appears (digest / ask / brief / launch-native / launch-claude / launch-codex / print / cancel) and the chosen action runs inline. For ask/brief/launch-bridge actions, the picker prompts for the question text at the shell. Use `--select-only` to restore the old print-and-exit behavior.

Flags:

- `--source {all,codex,claude}` - filter by platform (default: `all`)
- `--query <text>` - substring match against title, cwd, session id, or alias code
- `--cwd <path-fragment>` - match sessions whose cwd contains this substring
- `--limit <n>` - max results (default: `20`)
- `--json` - emit JSON array instead of table. Each entry includes `is_current: true` when its `session_id` matches `CLAUDE_CODE_SESSION_ID` or `CODEX_SESSION_ID`
- `--plain` - force non-interactive flat table output (with ANSI colors when stdout is a TTY)
- `--interactive` - force interactive picker even if not auto-detected
- `--chat-menu` - emit the numbered markdown chat menu with a snapshot id for `pick`
- `--open-terminal` - relaunch the interactive list in a new macOS Terminal window (useful from slash-command contexts)
- `--dry-run` - print the Terminal launch command without executing it
- `--active-only` - show only sessions updated within the active window (default: 240 minutes)
- `--select-only` - in interactive mode, print the selection and exit instead of opening the action menu

Examples:

```bash
session-absorb list --limit 20
session-absorb list --source claude --query redesign
session-absorb list --cwd context-copilot
session-absorb list --json
session-absorb list --active-only
session-absorb list --plain
session-absorb list --chat-menu --limit 12
session-absorb list --open-terminal     # spawns a Terminal window with the curses picker
session-absorb list --select-only       # picker that just prints the selection
```

## `session-absorb pick`

Resolves a numbered choice from the most recent `--chat-menu` snapshot.

Flags:

- positional `<n>` - 1-based index in the snapshot (required)
- `--snapshot <id>` - target a specific snapshot id; defaults to the latest

Examples:

```bash
session-absorb pick 3
session-absorb pick 1 --snapshot 8f092214
```

## `session-absorb init`

Assigns a short alias code to a session and prefixes the native session title with that code for easy targeting.

When called without `--session`, displays a numbered shortlist so you can pick by position. Supports natural-language query terms as positional arguments to narrow the shortlist.

Flags:

- `--source {codex,claude}` - restrict to one platform
- `--session <selector>` - session id, alias code, positional index (1-based), `latest`, or title prefix
- `--code <code>` - set a custom alias code (1-8 alphanumeric chars, auto-uppercased). If omitted, one is generated from a SHA1 hash
- `--title <title>` - override the base title before prefixing with the code
- `--query <text>` - substring filter for the shortlist
- `--cwd <path-fragment>` - cwd filter for the shortlist
- `--limit <n>` - shortlist size (default: `10`)
- positional `query_terms` - natural-language words to filter the shortlist (e.g. `session-absorb init trade mirror`)

Examples:

```bash
session-absorb init
session-absorb init trade mirror
session-absorb init --session 1 --code DASH1
session-absorb init --session latest
session-absorb init --source claude --session 3
```

After init, all other commands accept the alias code anywhere `--session` is expected.

## `session-absorb digest`

Renders a compact human-readable summary for a session: metadata, tool usage, recent user turns, and recent assistant turns.

Flags:

- `--source {codex,claude}` - required
- `--session <selector>` - required (session id, alias code, or positional index)

Example:

```bash
session-absorb digest --source claude --session DASH1
```

## `session-absorb ask`

Answers a focused question from a session. For Claude sessions, `--live auto` tries a live forked query first via `claude -p -r <session> --fork-session`. If that fails, the tool returns a ranked transcript-backed question pack.

Flags:

- `--source {codex,claude}` - required
- `--session <selector>` - required
- `--question <text>` - required
- `--limit <n>` - max ranked excerpts (default: `6`)
- `--live {auto,always,never}` - live query strategy (default: `auto`). `always` fails hard if the live path errors. `never` skips it entirely

Examples:

```bash
session-absorb ask --source claude --session DASH1 --question "What changed?"
session-absorb ask --source codex --session OPS42 --question "What is still blocked?"
session-absorb ask --source claude --session <id> --question "What port was used?" --live never
```

## `session-absorb brief`

Writes a Markdown bridge brief to `.session-absorb/briefs/`. The brief includes metadata, dominant tools, recent turns, highest-signal ranked excerpts, and instructions for the receiving session.

Flags:

- `--source {codex,claude}` - required
- `--session <selector>` - required
- `--question <text>` - optional focus question for excerpt ranking
- `--limit <n>` - max ranked excerpts in the brief (default: `8`)
- `--workspace <path>` - directory to write the brief into (default: current working directory)

Example:

```bash
session-absorb brief --source codex --session OPS42 --question "Absorb and continue"
```

## `session-absorb launch`

Launches a new Terminal window and starts either a native same-platform fork or a brief-driven bridge session.

Flags:

- `--source {codex,claude}` - required
- `--session <selector>` - required
- `--question <text>` - optional prompt for the launched session
- `--target {codex,claude}` - which CLI to launch in (defaults to same as source)
- `--mode {auto,native,brief}` - transfer strategy (default: `auto`). `auto` uses native when source matches target and the platform supports it
- `--workspace <path>` - directory for brief output (default: cwd)
- `--limit <n>` - max ranked excerpts for brief mode (default: `8`)
- `--dry-run` - print the shell command without opening Terminal

Examples:

```bash
session-absorb launch --source claude --session DASH1 --mode native
session-absorb launch --source claude --session <id> --target codex --question "Continue implementation"
session-absorb launch --source codex --session OPS42 --target claude --dry-run
```

## `session-absorb here`

Run an action on the most recent non-self session whose `cwd` matches `$PWD`. The current session (matched by `CLAUDE_CODE_SESSION_ID` or `CODEX_SESSION_ID`) is filtered out automatically.

Positional `action`:

- `digest` (default) - print the session digest
- `ask` - run `ask` with default question text (override with `--question`)
- `brief` - write a bridge brief with default instruction text (override with `--question`)
- `launch` - launch a native fork of the matched session in a new Terminal
- `show` - print the session metadata only (no transcript work)

Flags:

- `--question <text>` - override default question text for `ask` / `brief` actions

Errors with `No matching session in cwd \`<path>\`` if no candidate exists.

Examples:

```bash
session-absorb here
session-absorb here ask --question "What's still broken?"
session-absorb here launch
session-absorb here show
```

## `session-absorb last`

Same as `here` but matches across all cwds, not just `$PWD`. Filters out the current session via env var.

Positional `action`: same set as `here`.

Flags: same as `here`.

Examples:

```bash
session-absorb last
session-absorb last brief --question "Absorb everything from this morning"
session-absorb last show
```

## `session-absorb fork-myself`

Fork the user's CURRENT active session into a new Terminal window. Reads `CLAUDE_CODE_SESSION_ID` (preferred) or `CODEX_SESSION_ID` to identify "myself", then builds and spawns the right native fork command.

Errors with a clear message if neither env var is set (i.e. you're not running inside an active session).

Flags:

- `--question <text>` - optional initial prompt for the forked session
- `--dry-run` - print the shell command without spawning a Terminal

Examples:

```bash
session-absorb fork-myself
session-absorb fork-myself --question "Now refactor the picker"
session-absorb fork-myself --dry-run
```

The forked session inherits all current context up to the moment of fork; the original session continues independently. Same-CLI native fork only - if you want a cross-CLI handoff from your own session, use `launch --source claude --session $CLAUDE_CODE_SESSION_ID --target codex`.

## `session-absorb db`

Inspects the SQLite session catalog at `~/.local/share/session-absorb/sessions.db`. Shows counts by state (active, idle, missing) and the most recently seen sessions.

The catalog is updated automatically every time sessions are listed or resolved.

Flags:

- `--limit <n>` - max rows to display (default: `20`)
- `--json` - emit JSON instead of table

Examples:

```bash
session-absorb db
session-absorb db --json
session-absorb db --limit 50
```

## `session-absorb install`

Installs the runtime and skill wrappers globally.

Flags:

- `--repo-root <path>` - required, path to this repository checkout
- `--force` - overwrite existing targets

Installed paths:

- `~/.local/share/session-absorb/session_absorb_core.py`
- `~/.local/share/session-absorb/webapp/`
- `~/.local/share/session-absorb/session-start-hook-{codex,claude}.sh`
- `~/.local/bin/session-absorb`
- `~/.codex/skills/session-absorb/`
- `~/.claude/skills/session-absorb/`
- `~/.claude/skills/absorb/` (alias - copied if `skills/claude/absorb/` exists in the repo)

Example:

```bash
session-absorb install --repo-root "$(pwd)"
```

## Visual cues across renderers

Source differentiation is consistent across every output surface:

| Surface | Claude marker | Codex marker | Notes |
|---|---|---|---|
| Chat menu (markdown) | `◆C` | `◇X` | Legend line emitted above the table |
| TTY plain table | orange `claude` (`38;5;214`) | cyan `codex` (`38;5;51`) | Honors `NO_COLOR` and `FORCE_COLOR` |
| Curses interactive picker | orange `claude` | cyan `codex` | Source column bolded with curses color pair |
| `/absorb` AskUserQuestion picker | `🟠` orange circle | `🟢` green circle | Plus `📋` for the manual-pick escape option |
| Self marker | `*self*` suffix in plain output, `is_current: true` in JSON | same | Matched against `CLAUDE_CODE_SESSION_ID` / `CODEX_SESSION_ID` env vars |

## Environment variables

- `CLAUDE_CODE_SESSION_ID` - exported by Claude Code into subprocess env. When present and matching a session's `session_id`, that record is flagged `is_current: true` in JSON output and annotated `*self*` in plain output.
- `CODEX_SESSION_ID` - same role for Codex (when set).
- `NO_COLOR` - disables ANSI output regardless of TTY status.
- `FORCE_COLOR` - forces ANSI output even when stdout is not a TTY.

## `/absorb` slash command (Claude Code)

Lives at `skills/claude/absorb/SKILL.md` (alias of `/session-absorb`). Routes by argument shape:

| Invocation | Path | Behavior |
|---|---|---|
| `/absorb` | A | cwd auto-default. If exactly one non-self session in `$PWD`, jump straight to action picker. If 2+, show session picker first. Action picker has 4 primary options + a More submenu. |
| `/absorb here [action]` | B | Pass-through to `session-absorb here`. Default action `digest`. |
| `/absorb last [action]` | B | Pass-through to `session-absorb last`. Default action `digest`. |
| `/absorb pick` | B | Force the multi-step click picker. |
| `/absorb fork-myself` | B | Pass-through to `session-absorb fork-myself`. Forks the user's current active session. |
| `/absorb <subcommand> [args]` | C | Direct pass-through to `session-absorb`. |
| `/absorb <free text>` | D | Haiku subagent resolves intent (session match + verb) and runs the command in one shot. |

### Path A action menu

Primary actions shown after a session is selected:

| Option | Resulting shell command |
|---|---|
| 🔍 Digest | `session-absorb digest --source <s> --session <c>` |
| 🚀 Fork (native) | `session-absorb launch --source <s> --session <c> --mode native` |
| 🤝 Handoff to other CLI | `session-absorb launch --source <s> --session <c> --target <other>` |
| 🎯 More | renders the secondary menu below |

Secondary action menu (under 🎯 More):

| Option | Resulting shell command |
|---|---|
| 🔎 Ask question | `session-absorb ask --source <s> --session <c> --question "<default>"` |
| 📝 Brief only | `session-absorb brief --source <s> --session <c> --question "<default>"` |
| 🪞 Fork myself | `session-absorb fork-myself` (ignores the picked session - forks the user's own active session) |
| ↩️ Back | re-renders primary menu |

### Default question text

Hard-coded so the slash command never prompts the user:

- `ask`: `"What changed, what failed, and what should the receiving session know?"`
- `brief`: `"Absorb the implementation context and continue from there."`

For custom question text, invoke Path D (`/absorb ask why X failed in TMS121`) or pass `--question` directly via Path C.

### Bang-prefix fast paths

For zero-LLM-latency invocation, use the Claude Code bang prefix with the shell alias `sa`:

```bash
!sa list --active-only
!sa digest --source claude --session TMS121
!sa here                          # digest cwd-default sibling session
!sa here ask --question "what changed?"
!sa here launch                   # fork the cwd-default sibling
!sa last                          # digest most recent anywhere
!sa fork-myself                   # fork the current session
!sa fork-myself --question "now do X"
```

Bang prefix bypasses Claude entirely (~250ms shell only, no thinking budget consumed).
