# Session Absorb Verification Ledger

Last updated: 2026-04-18

## Scope

This ledger tracks active verification findings for the non-dashboard `session-absorb` flows:

- same-platform native launch
- Claude live ask vs transcript fallback
- cross-CLI brief handoff
- alias and selector resolution across commands

## Status

- Verification pass completed for the main non-dashboard command surface
- Dashboard-specific issues intentionally out of scope for this ledger
- Fixed items are retained below so the remaining open items are easier to review

## Fixed In This Pass

### 2026-04-18 19:58 EDT

1. `fixed` Missing-transcript Claude sessions no longer produce empty successful briefs
   - `session-absorb brief --source claude --session COAB01 ...` now exits `1`
   - message is explicit: transcript is not available yet and native fork may still work

2. `fixed` Missing-transcript Claude sessions no longer return empty transcript packs on `ask --live never`
   - `session-absorb ask --source claude --session COAB01 --live never ...` now exits `1`
   - output is explicit instead of `No relevant excerpts were extracted.`

3. `fixed` Alias-only Codex sessions now fail with an explicit not-indexed message
   - `digest`, `ask`, and `brief` against `COAB03` now explain that the alias exists but Codex has not written the session to `~/.codex/session_index.jsonl` yet

4. `fixed` `session-absorb list --plain` no longer crashes
   - the old `NameError: MaterialStatus is not defined` regression is gone in the installed runtime

5. `fixed` Claude live failure formatting no longer crashes on byte outputs
   - `ask --live always` now returns a clean failure message instead of `TypeError: expected str instance, bytes found`

6. `fixed` Codex brief generation no longer surfaces raw subagent-notification and chunk-status blobs as the top bridge excerpts
   - regenerated installed-runtime brief output now leads with assistant narrative excerpts instead of tool-status JSON

## Findings

### 2026-04-18 18:54 EDT - Cross-CLI bridge verification

1. `P1` Empty successful brief when source transcript is missing
   - Flow: cross-CLI `brief` and brief-driven handoff
   - Repro:
     - `session-absorb brief --source claude --session COAB01 --question 'Absorb this context-absorb Claude session into Codex and continue.'`
   - Observed:
     - command exited `0`
     - brief file was written successfully
     - generated brief reported `Transcript: missing`
     - no dominant tools, recent prompts, recent assistant responses, or highest-signal excerpts
   - Expected:
     - either fail clearly, warn prominently, or mark the brief as low-confidence / insufficient-source-material instead of silently producing a weak handoff artifact
   - Evidence:
     - `.session-absorb/briefs/20260418T225200Z-claude-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee1.md`
   - Status: `open`

2. `P2` Codex brief ranking overweights raw tool output
   - Flow: `brief` from Codex session to Claude
   - Repro:
     - `session-absorb brief --source codex --session aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee2 --question 'Absorb this Codex implementation session into Claude and continue.'`
   - Observed:
     - highest-signal excerpts contained noisy raw tool output, including large directory listings and code excerpts, instead of a cleaner task-focused bridge summary
   - Expected:
     - ranking should prefer user intent, assistant reasoning, and compact high-signal outputs over bulky low-context tool dumps
   - Evidence:
     - `.session-absorb/briefs/20260418T225200Z-codex-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee2.md`
   - Status: `open`

3. `P1` Codex aliases can exist without being resolvable as sessions
   - Flow: alias and selector resolution for Codex sessions
   - Repro:
     - `session-absorb list --plain --limit 25`
     - inspect `~/.local/share/session-absorb/aliases.json`
     - inspect `~/.codex/session_index.jsonl`
   - Observed:
     - aliases `COAB03` through `COAB06` existed in the alias registry
     - those sessions did not appear in `list`
     - the live `.codex/session_index.jsonl` only contained `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee2`
   - Expected:
     - either aliases should only be created for sessions discoverable via the canonical Codex index, or the resolver should surface a clearer “alias exists but session is not indexed” state
   - Evidence:
     - `~/.local/share/session-absorb/aliases.json`
     - `~/.codex/session_index.jsonl`
   - Status: `open`

4. `P2` Fresh Claude aliases can exist before transcript-backed commands are usable
   - Flow: alias and selector resolution for Claude sessions
   - Repro:
     - inspect headers in `~/.claude/sessions`
     - inspect transcript presence under `~/.claude/projects`
   - Observed:
     - `COAB01` and `COAB02` had valid Claude headers and aliases
     - neither had a matching transcript file yet
     - `CLDA03B` did have a transcript and was materially more usable
   - Expected:
     - transcript-backed commands should clearly indicate “session exists but transcript is not available yet” so the user knows this is a timing/state issue rather than a bad selector
   - Evidence:
     - `~/.claude/sessions/*.json`
     - `~/.claude/projects/**/*.jsonl`
   - Status: `open`

5. `P1` Claude `ask --live auto` can silently degrade to an empty fallback
   - Flow: Claude live ask vs transcript fallback
   - Repro:
     - `/usr/bin/time -p session-absorb ask --source claude --session COAB01 --question 'What is the current working directory of this session?' --live auto`
   - Observed:
     - returned a transcript-backed question pack instead of a live answer
     - output said `No relevant excerpts were extracted.`
     - command took about `7.91s`
     - no visible explanation that live resume failed before fallback
   - Expected:
     - either a clear warning that live resume failed and fallback is empty, or a structured status that distinguishes “live failed” from “no transcript evidence”
   - Evidence:
     - command output from the verification track
   - Status: `open`

6. `P1` Claude live resume still fails on older sessions with the deferred-marker error
   - Flow: Claude `ask --live always`
   - Repro:
     - `/usr/bin/time -p session-absorb ask --source claude --session CLDA03B --question 'What changed and what is still blocked?' --live always`
   - Observed:
     - stderr returned:
       - `Error: No deferred tool marker found in the resumed session...`
     - no stdout answer
     - command took about `7.12s`
   - Expected:
     - either a successful live answer or a more graceful downgrade path when `--live always` is explicitly requested
   - Evidence:
     - command stderr from the verification track
   - Status: `known-open`

7. `P1` `ask --live auto` can hang instead of falling back promptly
   - Flow: Claude live ask with automatic fallback
   - Repro:
     - `session-absorb ask --source claude --session CLDA03B --question 'What is this session doing? Answer in one short sentence.' --live auto --limit 3`
   - Observed:
     - hung for about `30.01s` in the verification harness
     - produced no stdout/stderr before timeout
     - same query with `--live never` returned in about `0.56s`
   - Expected:
     - `--live auto` should have a hard timeout and promptly degrade to transcript fallback when Claude live-resume is unhealthy
   - Evidence:
     - timing comparison from the dedicated Claude live-ask verification track
   - Status: `open`

8. `P1` Claude CLI resumability does not match session discoverability
   - Flow: direct Claude live resume behind `session-absorb ask`
   - Repro:
     - `claude -p -r aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee3 --fork-session --tools '' 'What is this session doing? Answer in one short sentence.'`
     - `claude -p -r aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee4 --fork-session --tools '' 'What is this session doing? Answer in one short sentence.'`
   - Observed:
     - both returned `RC 1`
     - stderr: `No conversation found with session ID: ...`
     - those sessions are still listable via `session-absorb`
   - Expected:
     - either resumability should be prevalidated before attempting live ask, or the user should get a clear “listable transcript session but not resumable by Claude CLI” status
   - Evidence:
     - direct `claude -p -r ... --fork-session` probes from the verification track
   - Status: `open`

9. `P2` Claude live-answer quality is not trustworthy even when `claude -p -r` exits `0`
   - Flow: direct Claude live resume / `ask --live` quality
   - Repro:
     - `claude -p -r aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee5 --fork-session --tools '' 'What is this session doing? Answer in one short sentence.'`
   - Observed:
     - command returned `RC 0`
     - output was unrelated to the session and mentioned lack of Bash tool access with a Python snippet
   - Expected:
     - success should be based on semantically relevant answer quality, not just `returncode == 0` and non-empty stdout
   - Evidence:
     - direct Claude CLI output from the verification track
   - Status: `open`

## Passes

- `P3` Cross-CLI `launch --mode auto` correctly resolved to brief mode in both Claude->Codex and Codex->Claude dry-run tests.
- `P3` Alias-based selection worked for bridge commands, including `CLDA03B`.
- `P3` Safe temp-HOME isolation for selector testing worked and produced a usable reduced catalog without mutating live state.
- `P3` Snapshot listing and `pick` worked with `list --chat-menu` and `pick 1 --snapshot ...`.
- `P3` Codex transcript fallback for `ask --live auto` was healthy and fast at about `0.58s`.
- `P3` Same-platform native launch dry-run command construction looked correct for both Claude and Codex.

## Still Open

1. `P2` Claude live ask on established sessions is explicit now, but still not consistently fast
   - `--live auto` and `--live always` can still spend the full `8s` timeout before degrading
   - some runs classify correctly as stale marker / non-resumable, but others still resolve only as timeout

2. `P2` Codex bridge briefs are cleaner, but still somewhat self-referential
   - the worst tool-status noise is gone
   - recent prompt and assistant sections still reflect the session’s own development history, which is accurate but not yet transformed into a tighter handoff summary

## Needs Retest

- live same-platform native launch end-to-end in Terminal:
  - `session-absorb launch --source claude --session COAB01 --mode native`
  - `session-absorb launch --source codex --session 019da216 --mode native`
- live cross-CLI launch end-to-end in Terminal:
  - `session-absorb launch --source claude --session CLDA03B --target codex --question 'Absorb this session and continue implementation.' --workspace /tmp/session-absorb-track3`
- full Claude live-ask matrix after the latest runtime install:
  - `--live auto`
  - `--live always`
  - `--live never`
  - on both resumable and non-resumable listed sessions

## Notes

- This file is the review surface for the current verification sweep.
- Findings should be kept concise and reproducible.
