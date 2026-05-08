# Use Cases

This is a tour of specific moments where Context Absorb earns its keep. I built it for myself, so the scenarios below are real evenings I've actually had. Each one has the situation, the exact command, and what you get back. If any of them feel familiar, you probably want this tool.

**1. The auth bug fix is in the tab next door**

You opened three Claude Code tabs this morning to chase an auth bug across the API and the frontend. Tab 1 chased the actual fix. You're now in tab 2 writing tests and you don't remember what tab 1 changed.

```
/absorb here
```

A digest of the most recent sibling session in this directory. You get the cwd, dominant tools used, the last few user prompts, and the last few assistant turns. Reads in 30 seconds. Self-detection filters out the tab you're typing in via `CLAUDE_CODE_SESSION_ID`, so you can't accidentally digest yourself or trip on a transcript that's still being written.

**2. Yesterday's session, this morning's amnesia**

You shipped something at 11pm and went to bed. Now it's 9am, coffee in hand, and you can't remember where you left off. Same repo, but everything else is fog.

```
/absorb
```

Pick the session from yesterday in the picker, choose `🔍 Digest`. If you live in this tool and your fingers move faster than menus, the bang-prefix one-liner does the same thing in about 250ms:

```
!sa here
```

**3. Codex did the heavy lift, Claude takes it from here**

You used Codex CLI to scaffold a new module because its planner felt right for the job. The scaffolding is done. Now you want Claude Code's editing flow on top of it without reading the Codex transcript line by line.

```
/absorb
```

Pick the Codex session (it's the green circle in the picker), choose `🤝 Handoff to other CLI`. A bridge brief gets written to `.session-absorb/briefs/`. A fresh Claude Code window opens in a new Terminal, primed with the brief as its first user message. The receiving session knows what tools were used, what files were touched, and what the previous CLI was trying to accomplish. Codex has no non-interactive fork API, so brief-driven handoff is the right road for cross-CLI work, not a fallback.

**4. Hand work to your future self in 8 hours**

End of the day, you've got one PR half-done. You won't remember the state by morning. You write a structured handoff to whichever Claude session opens in this cwd next.

```
/handoff --no-launch --target-cwd "$(pwd)" \
   --done "API routes wired" \
   --pending "frontend integration" \
   --blocked "waiting on Stripe API key"
```

Two artifacts get written:

- A markdown brief at `.session-absorb/briefs/<timestamp>-claude-<id>.md`. Your `## Handoff Notes` section (What's done / What's pending / What's blocked) leads, then session metadata, dominant tools, recent turns, and ranked transcript excerpts.
- A row in `~/.local/share/session-absorb/sessions.db` `handoffs` table marking it pending and tying it to your cwd.

Tomorrow you start a Claude session in the same directory and run `/inbox`. The pending handoff shows up:

```
# Inbox: 1 pending handoff(s)
  ID  AGE       FROM                              BRIEF                       REQ_ACK  STATUS
  --  --------  --------------------------------  --------------------------  -------  -------
  3   16h ago   claude:f7f36dcf (~/proj/api)      .session-absorb/briefs/...  no       pending
```

You read the brief, pick up where you stopped, and run `/ack 3` so the row flips to `acked` with your session id and timestamp recorded.

**5. Cross-CLI handoff with explicit ack**

You ran a heavy refactor in Codex. You want Claude to take over. You also want to know whether Claude actually started.

```
/handoff --target-cli claude --require-ack \
   --done "refactor complete, all tests passing" \
   --pending "performance benchmarks"
```

Because `--target-cli` differs from the source CLI, `--launch` defaults true: a new Claude Terminal opens immediately, primed to read the brief before doing anything. After Claude absorbs, it runs `/ack <id> --note "got it"`. Back in Codex, you check `session-absorb inbox --show-all` and see the row flipped to `acked` with the receiver's session id and your note attached.

**6. One question, not a whole digest**

You remember a session figured out a specific thing. Whether you wired up Stripe webhooks, what port the mock server ran on, why the migration kept failing. You don't want a 600-line digest, you want one answer.

```
/absorb
```

Pick the session, choose `🎯 More`, then `🔎 Ask question`. Or skip the menus entirely and let the Haiku subagent route a free-text dispatch:

```
/absorb ask did we already wire up Stripe webhooks?
```

For Claude sessions, `--live auto` tries a real forked query first. If that fails (sometimes resumed sessions choke on stale tool markers), you fall back to a ranked transcript-backed answer pack. Either way you get something usable.

**7. Try something risky without losing your place**

You're 40 messages deep in a session that's working. You want to try a refactor that might blow it up. You don't want to stash, branch, and lose your seat in the chat.

```
/absorb fork-myself
```

A new Terminal window opens with a parallel Claude Code session that inherits everything up to right now. The original keeps running in your current window, untouched. Use the fork to experiment with the refactor. If it works, merge the diffs back manually. If it doesn't, close the window and pretend it never happened. Same-CLI native fork only, no brief involved. Reads `CLAUDE_CODE_SESSION_ID` from your env to know who "myself" is.

**8. Hand the work to a teammate**

Sometimes a teammate needs to pick up where you left off and they don't have your terminal. You need a written artifact, not a fork.

```
/absorb
```

Pick the session, choose `🎯 More`, then `📝 Brief only`. The brief lands at `.session-absorb/briefs/<timestamp>-<source>-<sessionid>.md` (e.g. `20260508T143022Z-claude-abc123.md`). Plain Markdown: metadata, dominant tools, recent turns, ranked excerpts, instructions for the receiving session. Slack it, paste it into a PR description, attach it to a Linear ticket. It's just a file.

**9. You're juggling six sessions and need to see them all**

It's late, you've been hopping between four repos, and you've lost track of which sessions are still warm and which ones you can let go.

```
!sa list --active-only
```

A flat table of every session updated in the last 240 minutes. Claude rows render in orange (ANSI 214), Codex rows in cyan (ANSI 51). Your current session gets a `*self*` annotation in plain output so you don't waste a beat trying to digest yourself. `--active-only` clamps the list to live work, not yesterday's archaeological record. Honors `NO_COLOR` and `FORCE_COLOR` if you pipe it.

**10. You want to give one a name so you stop typing UUIDs**

There's a session you keep coming back to. The big dashboard refactor, the one with all the open threads. Typing `4f3a8b21-...` every time is friction.

```
!sa init --session latest --code DASH1
```

That stamps the alias `DASH1` onto your most recent session and rewrites the native session title to `[DASH1] ...`, so the host CLI's session picker shows it too. From here on, anywhere a `--session` selector is accepted, `DASH1` works:

```
!sa digest --source claude --session DASH1
```

---

For the full flag-by-flag reference, see [reference.md](reference.md). For how it's put together internally, see [architecture.md](architecture.md).
