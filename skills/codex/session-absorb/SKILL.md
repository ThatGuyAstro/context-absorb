---
name: session-absorb
description: Use when you need to absorb, merge, or consult context from another Codex or Claude Code session without copy-pasting, including native fork launch for same-CLI sessions and transcript-backed bridge briefs across CLIs.
argument-hint: "<list|pick|init|digest|ask|brief|launch|db|web|install> [args]"
---

# Session Absorb

Use this skill to move context between parallel `codex` and `claude` sessions with the shared runtime at `scripts/session_absorb.py`.

Canonical command surface: `session-absorb <subcommand> ...`

## Commands

| Command | Purpose | Example |
|---|---|---|
| `list` | show recent sessions; defaults to a compact chat menu in non-TTY contexts and an arrow-key picker in a real terminal | `session-absorb list --limit 20` |
| `pick` | select one entry from the latest chat-menu snapshot | `session-absorb pick 1` |
| `init` | shortlist recent sessions, or assign a short code and prefix the native session title | `session-absorb init` |
| `digest` | summarize one session | `session-absorb digest --source claude --session <id>` |
| `ask` | extract an answer or ranked excerpts | `session-absorb ask --source codex --session <id> --question "What changed?"` |
| `brief` | write a bridge brief for another session | `session-absorb brief --source claude --session <id> --question "Absorb and continue"` |
| `launch` | open a native fork or brief-driven bridge in Terminal | `session-absorb launch --source claude --session <id> --target codex` |
| `db` | inspect the SQLite session catalog and active-state counts | `session-absorb db` |
| `web` | serve the live local dashboard for sessions and states | `session-absorb web --open-browser` |
| `install` | install the runtime and skill wrappers into your home directories | `session-absorb install --repo-root <repo-root>` |

## What it supports

1. Native same-CLI teleport:
   - `codex -> codex` via `codex fork`
   - `claude -> claude` via `claude -r ... --fork-session`
2. Cross-CLI absorb:
   - generate a bridge brief from either transcript
   - launch a fresh `codex` or `claude` session seeded with that brief
3. Targeted context lookup:
   - ask a focused question against a session
   - Claude sessions can be queried live with a forked, non-editing `claude -p` call
   - Codex sessions fall back to ranked transcript excerpts because Codex does not expose non-interactive resume/fork

## Quick start

List recent sessions:

```bash
session-absorb list --limit 20
```

In a real shell, `session-absorb list` opens an arrow-key picker by default. In non-interactive or slash-command contexts, the same command now returns the compact chat-safe menu automatically.

If you want the native picker from a non-interactive context, use:

```bash
session-absorb list --open-terminal
```

To limit the picker or list to active sessions only:

```bash
session-absorb list --active-only
```

If you explicitly want the old verbose table, use:

```bash
session-absorb list --plain --limit 20
```

Open the shortlist and pick one:

```bash
session-absorb init
```

You can narrow it immediately with natural language:

```bash
session-absorb init trade mirror
```

Initialize one with a reusable code:

```bash
session-absorb init --session 1 --code OPS42
```

If you omit `--code`, one is generated automatically:

```bash
session-absorb init --session latest
```

New sessions also receive an automatic mnemonic code from the `SessionStart` hook after install, and the hook will usually prefix the native title with that code too, so `list` will often already show a short identifier without running `init`.

Render a digest:

```bash
session-absorb digest --source codex --session OPS42
```

Ask a targeted question:

```bash
session-absorb ask --source claude --session DASH1 --question "What changed and what is still blocked?"
```

Launch a same-platform native fork in a new Terminal window:

```bash
session-absorb launch --source codex --session OPS42 --mode native
```

Launch a cross-CLI bridge session from a brief:

```bash
session-absorb launch --source claude --session <session-id> --target codex --question "Absorb the design work and continue implementation."

Open the live dashboard:

```bash
session-absorb web --open-browser
```
```

## Operating rules

- Prefer `launch --mode native` when the source and target CLI are the same.
- Prefer `ask --live auto` for Claude sessions when you want the old session to answer directly.
- Prefer `brief` or `launch --mode brief` for any Codex session you want another CLI to absorb.
- Do not dump an entire transcript into the current context unless the question truly needs it. Use `digest`, `ask`, or `brief` first.
- Session metadata is also mirrored into `~/.local/share/session-absorb/sessions.db` for active-state tracking and later lookup.
- `install` also registers a `SessionStart` hook in Claude and Codex so new sessions get a short mnemonic code automatically and, when possible, a `[CODE] ...` native title prefix.
- If Claude live resume returns a stale deferred-tool error, keep the fallback transcript pack. That is expected on some old sessions.
- After `init`, you can pass the short code anywhere `--session` is accepted.

## Installer

If this repo skill has not been copied into your home-level registries yet, install the runtime plus both platform skill wrappers with:

```bash
session-absorb install --repo-root <repo-root>
```

If the `session-absorb` wrapper is not on `PATH`, use the installed home-level executable directly:

```bash
$HOME/.local/bin/session-absorb {{ARGUMENTS}}
```
