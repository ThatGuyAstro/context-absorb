# Command Reference

## Orientation: slash commands first

If you're inside Claude Code, you almost never type these CLI commands directly. Reach for one of these instead:

- `/absorb` opens the click picker. Pick a session, pick an action, done.
- `/absorb here` runs against the most recent sibling session in your current directory.
- `/absorb <free text>` lets a Haiku subagent figure out which session and which verb you meant.
- `/session-absorb <subcommand>` is a direct pass-through to the CLI if you know exactly what you want.

The CLI reference below is what those slash flows ultimately run. It's also what you type when you've aliased the binary to `sa` and want bang-prefix speed: `!sa here`, `!sa list --active-only`, etc. The bang prefix skips Claude entirely (~250ms shell roundtrip, no thinking budget burned).

The full slash-command routing table lives at the bottom of this file under [`/absorb` slash command](#absorb-slash-command-claude-code).

## Default invocation (no subcommand)

_Reach for this when: you have one keystroke to spare and you just want to see what's around._

`session-absorb` with no arguments runs `list` and picks the right renderer for where you are:

- in a real terminal: opens the interactive curses picker
- non-TTY (e.g. inside a Claude Code Bash tool call): prints a chat-safe markdown menu

Use this when you want one-keystroke access to the picker from anywhere.

## `session-absorb list`

_Reach for this when: you can't remember which session was the right one and want to scan recent activity._

Shows your recent Claude and Codex sessions. In a real terminal, you get an arrow-key picker. In a piped or non-TTY context (like inside a Claude Code Bash tool call), you get a markdown table you can read inline.

After picking a session with Enter, a second action menu appears (digest / ask / brief / launch-native / launch-claude / launch-codex / print / cancel) and the chosen action runs inline. For ask/brief/launch-bridge actions, you'll be prompted for the question text at the shell. Pass `--select-only` if you just want the picker to print a selection and exit.

From inside Claude Code: `/absorb` is the friendlier route. It uses the AskUserQuestion picker instead of curses.

Flags:

- `--source {all,codex,claude}` - filter by platform (default: `all`)
- `--query <text>` - substring match against title, cwd, session id, or alias code
- `--cwd <path-fragment>` - match sessions whose cwd contains this substring
- `--limit <n>` - max results (default: `20`)
- `--json` - print a JSON array instead of a table. Each entry includes `is_current: true` when its `session_id` matches `CLAUDE_CODE_SESSION_ID` or `CODEX_SESSION_ID`
- `--plain` - force non-interactive flat table output (with ANSI colors when stdout is a TTY)
- `--interactive` - force the interactive picker even if not auto-detected
- `--chat-menu` - print the numbered markdown chat menu with a snapshot id for `pick`
- `--open-terminal` - relaunch the interactive list in a new macOS Terminal window (handy from slash-command contexts)
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

_Reach for this when: you ran `--chat-menu` and you're following up by number from the printed snapshot._

Resolves a numbered choice from the most recent `--chat-menu` snapshot. You'll mostly hit this indirectly: a chat-menu list emits a snapshot, then a follow-up message says "pick 3" and `pick` is what runs.

Flags:

- positional `<n>` - 1-based index in the snapshot (required)
- `--snapshot <id>` - target a specific snapshot id; defaults to the latest

Examples:

```bash
session-absorb pick 3
session-absorb pick 1 --snapshot 8f092214
```

## `session-absorb init`

_Reach for this when: you'll come back to this session in 20 minutes and want a 6-character handle, not a UUID._

Stamps a short alias code onto a session and prefixes the native session title with that code, so you can refer to it later as `TMS121` instead of a UUID.

Without `--session`, you get a numbered shortlist to pick by position. Positional arguments are treated as natural-language query terms to narrow the shortlist.

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

After init, every other command accepts the alias code anywhere `--session` is expected.

## `session-absorb digest`

_Reach for this when: you ran something earlier today and want a recap before typing in a new tab._

Prints a summary of one session: what cwd it ran in, what tools it used, the last few user prompts, and the last few assistant turns. Good for skimming a session you ran an hour ago without re-loading its full transcript.

From inside Claude Code: `/absorb here` runs this against the cwd-default session, or `/absorb` opens a picker that lets you choose a session and select Digest.

Flags:

- `--source {codex,claude}` - required
- `--session <selector>` - required (session id, alias code, or positional index)

Example:

```bash
session-absorb digest --source claude --session DASH1
```

## `session-absorb ask`

_Reach for this when: a past session figured out a specific thing and you want a one-question lookup, not a full digest._

Asks one of your past sessions a question and prints whatever the transcript or live fork can answer. For Claude sessions, `--live auto` tries a live forked query first via `claude -p -r <session> --fork-session`. If that path fails, you get a ranked transcript-backed question pack instead.

From inside Claude Code: `/absorb` -> pick session -> More -> Ask question. Or skip the menus with `/absorb ask why X failed in TMS121`.

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

_Reach for this when: you're handing this work to a new session and want a written brief on disk first._

Writes a Markdown bridge brief to `.session-absorb/briefs/`. The brief contains metadata, dominant tools, recent turns, the highest-signal ranked excerpts, and instructions for the receiving session. Use this when you're handing off across CLIs (Claude -> Codex or vice versa) and a native fork isn't available.

From inside Claude Code: `/absorb` -> pick session -> More -> Brief only. Or use the handoff option to run brief plus a native launch in one shot.

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

_Reach for this when: you want to keep going in a fresh session, either same-CLI fork or cross-CLI bridge._

Opens a new Terminal window and starts either a native same-platform fork or a brief-driven bridge session. This is what `/absorb`'s Fork and Handoff buttons run under the hood.

Flags:

- `--source {codex,claude}` - required
- `--session <selector>` - required
- `--question <text>` - optional prompt for the launched session
- `--target {codex,claude}` - which CLI to launch in (defaults to same as source)
- `--mode {auto,native,brief}` - transfer strategy (default: `auto`). `auto` picks native when source matches target and the platform supports it
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

_Reach for this when: what you want is the most recent session you ran in this directory. Skip the picker._

Runs an action on the most recent non-self session whose `cwd` matches `$PWD`. The current session (matched via `CLAUDE_CODE_SESSION_ID` or `CODEX_SESSION_ID`) is filtered out, so `here` always points at a sibling, never at yourself.

Positional `action`:

- `digest` (default) - print the session digest
- `ask` - run `ask` with default question text (override with `--question`)
- `brief` - write a bridge brief with default instruction text (override with `--question`)
- `launch` - launch a native fork of the matched session in a new Terminal
- `show` - print the session metadata only (no transcript work)

Flags:

- `--question <text>` - override default question text for `ask` / `brief` actions

If nothing matches in this directory, you get `No matching session in cwd <path>` and exit code 1.

Examples:

```bash
session-absorb here
session-absorb here ask --question "What's still broken?"
session-absorb here launch
session-absorb here show
```

## `session-absorb last`

_Reach for this when: what you want is the most recent session you ran anywhere. Skip the picker._

Same shape as `here`, but searches every cwd, not just `$PWD`. Still filters out the current session via env var. Use this when you know you ran something earlier today but you're in a different repo now.

Positional `action`: same set as `here`.

Flags: same as `here`.

Examples:

```bash
session-absorb last
session-absorb last brief --question "Absorb everything from this morning"
session-absorb last show
```

## `session-absorb fork-myself`

_Reach for this when: you're about to try something risky and want a parallel session that inherits everything._

Forks the session you're sitting in right now into a new Terminal window. Reads `CLAUDE_CODE_SESSION_ID` (preferred) or `CODEX_SESSION_ID` to identify "myself", then builds and spawns the right native fork command.

If neither env var is set (you're not actually inside an active session), it errors with a clear message instead of guessing.

Flags:

- `--question <text>` - optional initial prompt for the forked session
- `--dry-run` - print the shell command without spawning a Terminal

Examples:

```bash
session-absorb fork-myself
session-absorb fork-myself --question "Now refactor the picker"
session-absorb fork-myself --dry-run
```

The forked session inherits all current context up to the moment of fork; the original keeps going independently. Same-CLI native fork only. If you want a cross-CLI handoff out of your own session, use `launch --source claude --session $CLAUDE_CODE_SESSION_ID --target codex` instead.

## `session-absorb db`

_Reach for this when: you want to inspect the SQLite catalog directly instead of going through the picker._

Inspects the SQLite session catalog at `~/.local/share/session-absorb/sessions.db`. Shows counts by state (active, idle, missing) and the most recently seen sessions. The catalog refreshes itself every time sessions are listed or resolved, so this is just a read.

Flags:

- `--limit <n>` - max rows to display (default: `20`)
- `--json` - print JSON instead of a table

Examples:

```bash
session-absorb db
session-absorb db --json
session-absorb db --limit 50
```

## `session-absorb install`

_Reach for this when: you just cloned the repo and need the runtime, shell command, and skill wrappers wired up._

Installs the runtime and skill wrappers globally. Run this once after cloning, then again with `--force` whenever you pull updates.

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

Source differentiation stays consistent across every output surface:

| Surface | Claude marker | Codex marker | Notes |
|---|---|---|---|
| Chat menu (markdown) | `◆C` | `◇X` | Legend line printed above the table |
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
| `/absorb` | A | cwd auto-default. If exactly one non-self session in `$PWD`, jumps straight to the action picker. If 2+, shows session picker first. Action picker has 4 primary options + a More submenu. |
| `/absorb here [action]` | B | Pass-through to `session-absorb here`. Default action `digest`. |
| `/absorb last [action]` | B | Pass-through to `session-absorb last`. Default action `digest`. |
| `/absorb pick` | B | Forces the multi-step click picker. |
| `/absorb fork-myself` | B | Pass-through to `session-absorb fork-myself`. Forks your current active session. |
| `/absorb <subcommand> [args]` | C | Direct pass-through to `session-absorb`. |
| `/absorb <free text>` | D | Haiku subagent resolves intent (session match + verb) and runs the command in one shot. |

### Path A action menu

Primary actions shown after a session is selected:

| Option | Resulting shell command |
|---|---|
| 🔍 Digest | `session-absorb digest --source <s> --session <c>` |
| 🚀 Fork (native) | `session-absorb launch --source <s> --session <c> --mode native` |
| 🤝 Handoff to other CLI | `session-absorb launch --source <s> --session <c> --target <other>` |
| 🎯 More | shows the secondary menu below |

Secondary action menu (under 🎯 More):

| Option | Resulting shell command |
|---|---|
| 🔎 Ask question | `session-absorb ask --source <s> --session <c> --question "<default>"` |
| 📝 Brief only | `session-absorb brief --source <s> --session <c> --question "<default>"` |
| 🪞 Fork myself | `session-absorb fork-myself` (ignores the picked session - forks your own active session) |
| ↩️ Back | re-renders the primary menu |

### Default question text

Hard-coded so the slash command never has to prompt you:

- `ask`: `"What changed, what failed, and what should the receiving session know?"`
- `brief`: `"Absorb the implementation context and continue from there."`

For custom question text, take Path D (`/absorb ask why X failed in TMS121`) or pass `--question` directly via Path C.

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

Bang prefix skips Claude entirely (~250ms shell only, no thinking budget consumed).
