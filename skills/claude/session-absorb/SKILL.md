---
name: session-absorb
description: Use when you need to absorb, merge, or consult context from another Claude Code or Codex session without copy-pasting, including native Claude fork launch, Codex fork launch, transcript-backed bridge briefs, and focused session Q and A.
argument-hint: "<list|pick|init|digest|ask|brief|launch|db|web|install> [args]"
---

# Session Absorb

Use the shared runtime at `scripts/session_absorb.py` to move context between parallel Claude Code and Codex sessions.

Canonical slash command: `/session-absorb`

## Commands

| Command | Purpose | Example |
|---|---|---|
| `list` | show recent sessions; defaults to a compact chat menu in non-TTY contexts and an arrow-key picker in a real terminal | `/session-absorb list --limit 20` |
| `pick` | select one entry from the latest chat-menu snapshot | `/session-absorb pick 1` |
| `init` | shortlist recent sessions, or assign a short code and prefix the native session title | `/session-absorb init` |
| `digest` | summarize one session | `/session-absorb digest --source claude --session <id>` |
| `ask` | query a session or build ranked excerpts | `/session-absorb ask --source codex --session <id> --question "What changed?"` |
| `brief` | write a bridge brief | `/session-absorb brief --source claude --session <id> --question "Absorb and continue"` |
| `launch` | open a native fork or bridge session in Terminal | `/session-absorb launch --source codex --session <id> --target claude` |
| `db` | inspect the SQLite session catalog and active-state counts | `/session-absorb db` |
| `web` | serve the live local dashboard for sessions and states | `/session-absorb web --open-browser` |
| `install` | install the runtime and skill wrappers into both home registries | `/session-absorb install --repo-root <repo-root>` |

## Main workflows

1. Find the source session:

```bash
session-absorb list --limit 20
```

In a real shell, `session-absorb list` opens an arrow-key picker by default. In slash-command or other non-TTY contexts, the same command now returns the compact chat-safe menu automatically.

If you want the native picker from a slash-command context, use:

```bash
session-absorb list --open-terminal
```

To show only currently active sessions:

```bash
session-absorb list --active-only
```

If you explicitly want the old verbose table, use:

```bash
session-absorb list --plain --limit 20
```

2. Open the shortlist and pick a session:

```bash
session-absorb init
```

You can narrow it immediately with natural language:

```bash
session-absorb init trade mirror
```

3. Initialize it with a short code you can reuse later:

```bash
session-absorb init --session 1 --code DASH1
```

If you omit `--code`, one is generated automatically:

```bash
session-absorb init --session latest
```

New sessions also receive an automatic mnemonic code from the `SessionStart` hook after install, and the hook will usually prefix the native title with that code too, so `list` will often already show a short identifier without running `init`.

4. Ask what the other session knows:

```bash
session-absorb ask --source claude --session DASH1 --question "What changed, what failed, and what should the receiving session know?"
```

5. Launch a native same-CLI fork:

```bash
session-absorb launch --source claude --session DASH1 --mode native
```

6. Launch a cross-CLI bridge session from a generated brief:

```bash
session-absorb launch --source codex --session OPS42 --target claude --question "Absorb the implementation context and continue from there."

7. Open the live dashboard:

```bash
session-absorb web --open-browser
```
```

## Important constraints

- Claude sessions support live non-interactive questioning through `claude -p -r <session> --fork-session`.
- Codex sessions do not expose a non-interactive resume/fork path, so the runtime uses transcript ranking and bridge briefs instead of pretending there is a live RPC channel.
- Session metadata is also mirrored into `~/.local/share/session-absorb/sessions.db` for active-state tracking and later lookup.
- `install` also registers a `SessionStart` hook in Claude and Codex so new sessions get a short mnemonic code automatically and, when possible, a `[CODE] ...` native title prefix.
- Same-platform transfer should stay native when possible. Cross-platform transfer should use a generated brief.
- Some resumed Claude sessions fail with a stale deferred-tool marker. When that happens, use the transcript pack fallback instead of retrying the same live query.
- After `init`, all standard commands can target the short code instead of the full UUID.

## Installer

Install the runtime into `~/.local/share/session-absorb`, the shell command into `~/.local/bin`, and both skill wrappers into the home registries with:

```bash
session-absorb install --repo-root <repo-root>
```

## Routing

Preferred execution path:

```bash
$HOME/.local/bin/session-absorb {{ARGUMENTS}}
```

Task: {{ARGUMENTS}}
