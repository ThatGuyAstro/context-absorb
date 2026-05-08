---
name: absorb
description: Use when the user types /absorb. Defaults to digesting the most-recent non-self session in the current cwd. Falls back to click picker, natural-language Haiku dispatch, or direct subcommand pass-through.
argument-hint: "[pick | here | last | <subcommand> [args] | <natural language>]"
---

# Absorb

Cross-session context bridge. Optimized for the common case: "digest the sibling Claude session in this directory."

## Routing

Classify `{{ARGUMENTS}}` and pick a path:

1. No args → **Path A: cwd auto-default** (most common, 1-click)
2. First arg is `pick` / `here` / `last` → **Path B: shortcut**
3. First arg is `list|pick|init|digest|ask|brief|launch|here|last|fork-myself|handoff|inbox|ack|db|web|install` → **Path C: pass-through**
4. Free text → **Path D: Haiku natural-language dispatch**

## Path A: bare `/absorb` (cwd auto-default)

The 70%-case. Skip multi-step picker entirely.

### Step 1: detect candidates

```bash
$HOME/.local/bin/session-absorb list --json --limit 20 | jq -c '
  map(select(.is_current != true)) |
  {
    local: [.[] | select(.cwd == env.PWD) | {c:.alias_code,s:.source,t:.title,u:.updated_at,r:.readiness}][0:3],
    recent: [.[] | {c:.alias_code,s:.source,t:.title,u:.updated_at,r:.readiness,cwd:.cwd}][0:6]
  }
'
```

### Step 2: pick a session (only if needed)

If `.local` has exactly 1 entry: skip this step, go straight to Step 3 with that session pre-selected.

If `.local` has 2+ entries OR is empty: AskUserQuestion to pick:

> Question: ``Which session?``
> Options (max 4):
> - For each candidate (up to 3): label = `🟠 <c>` for claude or `🟢 <c>` for codex; description = `<truncated title> · <relative time>`
> - 4th option: `📋 Show all` (only if `.local` is empty - presents `recent` list)

If user picks `📋 Show all`: second AskUserQuestion with up to 3 of `recent` + `📋 Type code manually` escape.

### Step 3: pick an action

For the chosen session, AskUserQuestion with all four primary actions:

> Question: ``Action for `<code>` — `<truncated title>`?``
> Options (max 4):
> 1. `🔍 Digest` — description: `Summarize what changed in this session.`
> 2. `🚀 Fork (native)` — description: `Open a new <source> session that continues from here.`
> 3. `🤝 Handoff to other CLI` — description: `Generate a brief and open in the other CLI.`
> 4. `🎯 More` — description: `Ask a custom question, or write a brief without launching.`

### Step 4: dispatch

| Action | Command |
|---|---|
| 🔍 Digest | `$HOME/.local/bin/session-absorb digest --source <s> --session <c>` |
| 🚀 Fork (native) | `$HOME/.local/bin/session-absorb launch --source <s> --session <c> --mode native` |
| 🤝 Handoff to other CLI | `$HOME/.local/bin/session-absorb launch --source <s> --session <c> --target <claude-if-source-is-codex-else-codex>` |
| 🎯 More | second AskUserQuestion below |

For 🎯 More, render a follow-up AskUserQuestion:

> Question: ``Pick a secondary action for `<code>`.``
> Options (max 4):
> 1. `🔎 Ask question` — description: `Ask a targeted question (uses default text).`
> 2. `📝 Brief only` — description: `Write a bridge brief to .session-absorb/briefs/ without launching.`
> 3. `📦 Handoff` - description: `Hand this session off with a structured note for the next picker-up.`
> 4. `↩️ Back`

| Secondary | Command |
|---|---|
| 🔎 Ask question | `$HOME/.local/bin/session-absorb ask --source <s> --session <c> --question "<default ask text>"` |
| 📝 Brief only | `$HOME/.local/bin/session-absorb brief --source <s> --session <c> --question "<default brief text>"` |
| 📦 Handoff | `$HOME/.local/bin/session-absorb handoff --source <s> --session <c>` (plus any `--done`/`--pending`/`--blocked` text the user provides; runs against the picked session as source) |
| ↩️ Back | re-render Step 3 |

### Default questions (do NOT prompt)

- `ask`: `"What changed, what failed, and what should the receiving session know?"`
- `brief`: `"Absorb the implementation context and continue from there."`

For custom questions, the user invokes Path D directly (`/absorb ask why X failed in TMS121`).

## Path B: shortcuts

`here` and `last` are native `session-absorb` subcommands - dispatch them as pass-through (Path C). They run in pure shell with no LLM thinking, no JSON parsing, no jq.

| Command | Action | Equivalent shell |
|---|---|---|
| `/absorb here` | Digest most-recent non-self session in current cwd | `session-absorb here` |
| `/absorb here ask --question "..."` | Ask in cwd-default session | `session-absorb here ask --question "..."` |
| `/absorb here brief` | Bridge brief from cwd-default session | `session-absorb here brief` |
| `/absorb here launch` | Launch native fork of cwd-default session | `session-absorb here launch` |
| `/absorb last` | Digest most-recent non-self session anywhere | `session-absorb last` |
| `/absorb pick` | Force the multi-step click picker (Path A) | (handled in Path A logic) |
| `/absorb fork-myself` | Fork the user's CURRENT active session (not a picked one) | `session-absorb fork-myself` |

Available actions for `here` / `last`: `digest` (default), `ask`, `brief`, `launch`, `show` (just print metadata).

For TRUE zero-latency (no thinking budget at all), recommend the user runs the bang-prefix form: `!sa here`, `!sa last`, `!sa here ask --question "..."`. That bypasses Claude entirely - shell only, ~250ms end-to-end.

## Path C: known subcommand pass-through

```bash
$HOME/.local/bin/session-absorb {{ARGUMENTS}}
```

## Path D: natural-language Haiku dispatch

For free-text intents, use the `Agent` tool with `subagent_type: general-purpose`, `model: haiku`. Prompt template (replace `<INTENT>` verbatim):

```
You are a session-absorb dispatcher. The user's intent is: "<INTENT>"

Step 1 - REQUIRED: call Bash to fetch sessions:
  $HOME/.local/bin/session-absorb list --json --limit 20

Step 2: parse the JSON. Filter out is_current == true. Match the intent to one session by alias_code, title fragment, or cwd. If multiple match, prefer cwd == $PWD; otherwise pick most recently updated.

Step 3: pick the action verb:
  - digest = summarize, recap, what-changed, what-happened
  - ask = a question phrased as a query
  - brief = absorb, transfer, continue, hand off
  - launch = fork, bridge, open in new

Step 4 - REQUIRED: call Bash to execute the dispatch command:
  - digest -> $HOME/.local/bin/session-absorb digest --source <source> --session <alias_code>
  - ask -> $HOME/.local/bin/session-absorb ask --source <source> --session <alias_code> --question "<extracted question>"
  - brief -> $HOME/.local/bin/session-absorb brief --source <source> --session <alias_code> --question "<extracted instruction>"
  - launch -> $HOME/.local/bin/session-absorb launch --source <source> --session <alias_code> --mode native

Step 5: return ONLY the stdout of the dispatch command. No preamble, no commentary, no markdown wrapping.

If you cannot disambiguate, return: "Could not disambiguate - try /absorb pick for the click picker, or /absorb here for the most recent session in this folder."
```

## Visual conventions

AskUserQuestion option labels (chat-rendered, color via emoji):
- `🟠` = Claude session
- `🟢` = Codex session
- `🎯` = Action selector / different action
- `📋` = Browse / list / manual entry
- `✅` `❌` `↩️` `🔍` `📝` `🚀` for control affordances

Plain-text contexts (chat menu, terminal, curses): `◆C` (Claude) / `◇X` (Codex) — runtime emits these automatically.

## Inbox check on session start

When `/absorb` is invoked with no args (Path A), before rendering the action picker, run:

```bash
$HOME/.local/bin/session-absorb inbox --json --limit 5
```

If the result is non-empty (pending handoffs targeted at this cwd, CLI, or session id), surface a 1-line summary at the top of the response - "📦 N pending handoff(s) for this session" - and offer to absorb the most recent one before continuing with the normal Path A flow. The user can then run `/absorb ack <id>` after they've digested it.

## Important constraints

- Never invoke yourself: runtime filters `is_current` sessions. Don't override.
- Claude Code chat does NOT render ANSI colors; emoji is the only intrinsic-color path.
- For zero-LLM speed: user runs `!sa <args>` directly via the bang prefix. Do not suggest curses TUI inside chat.
- Path A's picker should fire AT MOST one AskUserQuestion before dispatch. Two if user picks "Different action".

Task: {{ARGUMENTS}}
