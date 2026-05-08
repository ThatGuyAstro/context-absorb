# Context Absorb

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/ThatGuyAstro/context-absorb/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tested on macOS](https://img.shields.io/badge/tested%20on-macOS-lightgrey.svg)](https://github.com/ThatGuyAstro/context-absorb)

You're three Claude Code tabs deep, the one that found the auth bug isn't the one you're typing in, and you don't want to re-explain everything to a fresh session. Context Absorb pulls context out of any Claude Code or Codex session you've already run and pours it into the one you're in now. Local-only, stdlib Python, no SaaS, no API keys.

## When you'd reach for it

**You found the bug in one tab and you're typing in another.** Tab 1 chased an auth bug for an hour and figured out the fix. You're in tab 2 writing the tests now, and you can't quite remember what tab 1 actually changed.

```
/absorb here
```

Pulls a digest of the most recent sibling session in this directory. You see the files it touched, what it tried, and what landed.

**You started something here yesterday and don't remember what.** Same directory, different day. You want a quick recap of where you left off before you start typing again.

```
/absorb
```

Opens an in-chat picker showing recent sessions for this cwd. Click one, click Digest, read the recap.

**Codex did the heavy lifting. You want to keep going in Claude.** You ran a refactor in Codex CLI. Now you're in Claude Code and want it to continue from there. Pasting a transcript is not it.

```
/absorb
```

In the picker, choose the Codex session. Then "Handoff to other CLI". A brief gets written to `.session-absorb/briefs/`, and a new Claude session opens already primed to read it before doing anything else.

**You want to try something risky without losing your place.** You're in a session that took an hour to build context. You want to spin off a parallel session that inherits everything, try a refactor that might fail, and bail without affecting the original.

```
/absorb fork-myself
```

New Terminal window, new Claude session, same context. The session you're in now keeps going untouched.

## Install

```bash
curl -sSL https://raw.githubusercontent.com/ThatGuyAstro/context-absorb/v0.1.0/install.sh | bash
```

That installs the `session-absorb` command, the `/absorb` and `/session-absorb` skills for both Claude Code and Codex, and a SessionStart hook that auto-tags new sessions with short alias codes (e.g. `TMS01`). Requires Python 3.10+. macOS-tested; Linux/Windows fallbacks landed but unverified.

## Demo

_Asciinema demo coming soon - see scripts/demo-asciinema.sh_

## Other shapes worth knowing

Beyond the four scenarios above, the slash command takes a few more forms:

```
/absorb last                    # digest the most recent non-self session anywhere
/absorb digest the UI session   # free text gets routed by a Haiku subagent
```

Self-detection via `CLAUDE_CODE_SESSION_ID` filters out your own active session, so you can't accidentally digest a transcript that's still being written. `/session-absorb` is the same thing with a longer name; use whichever your fingers reach for.

### If you want it instant

Slash commands route through the LLM, which costs you a couple of seconds. If you live in this tool, drop a shell alias and use the bang prefix to bypass Claude entirely:

```bash
echo 'alias sa="$HOME/.local/bin/session-absorb"' >> ~/.zshrc
```

Then in chat:

```
!sa here
!sa fork-myself
!sa digest --source claude --session TMS121
```

About 250ms instead of a full conversational turn. Use it when you know exactly what you want.

## How it works in 90 seconds

Both Claude Code and Codex write JSONL transcripts under your home directory (`~/.claude/sessions/`, `~/.codex/sessions/`). Context Absorb reads those files directly. There is no daemon, no server, no remote sync.

When you ask for a session, the tool finds it three ways: by alias code (`TMS121`), by current working directory (the most recent non-self session in `$PWD`), or via an interactive picker. A SessionStart hook auto-assigns the alias codes when sessions begin, and prefixes the native session title with the code where the platform allows it.

Once a session is located, the runtime parses its transcript, strips slash-command preambles and other noise, and either summarizes it (digest), answers a targeted question against ranked excerpts (ask), or writes a Markdown handoff brief into `.session-absorb/briefs/`.

For handoff, same-platform transfers prefer native forks: `claude -r <session> --fork-session` and `codex fork`. Cross-platform handoff falls back to the brief, because Codex doesn't expose a reliable non-interactive fork and some Claude sessions choke on stale deferred-tool markers when resumed. The brief path isn't a backup; for cross-CLI work it's the main road.

## Commands

The shared CLI exposes twelve subcommands. The ones you'll touch directly:

**Find a session:** `list` (interactive picker or table), `init` (assign or override an alias code), `pick` (select by number from the last chat menu).

**Do something with it:** `digest`, `ask --question`, `brief`, `launch` (native fork or cross-platform handoff).

**Shortcuts:** `here [action]` for the cwd default, `last [action]` for anywhere, `fork-myself` for the current session.

**Plumbing:** `db` to inspect the SQLite catalog, `web` to serve a local live dashboard, `install` to (re)install the runtime and skills.

Visual cues distinguish the two CLIs everywhere: `🟠` for Claude and `🟢` for Codex in the in-chat picker, `◆C` and `◇X` in plain text, ANSI 214 (orange) and 51 (cyan) in real terminals. Honors `NO_COLOR` and `FORCE_COLOR`.

Full flag-by-flag reference lives in [docs/reference.md](docs/reference.md). Architecture and internals are in [docs/architecture.md](docs/architecture.md).

## Limits and reality check

- macOS-tested. Linux and Windows fallbacks are in the code but I haven't run them on real hardware. File issues if they break.
- Ranking is lexical (term hits plus recency), not semantic. Good enough for "what was the auth bug" but not for fuzzy concept search.
- Live Claude questioning sometimes fails on resumed sessions with stale deferred-tool marker errors. The tool falls back to transcript extraction automatically.
- Codex has no non-interactive fork, so cross-CLI handoff out of Codex always uses a brief.
- Both CLIs need to be on the same machine. There is no remote session pulling.
- No formal test suite. Validation is `python3 -m py_compile` plus real CLI smoke tests.

## License + contributing

MIT, see [LICENSE](LICENSE). Contributions welcome: read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR.
