# Repository Guidelines

## Project Structure & Module Organization

This repository is a small agent tooling workspace centered on the `session-absorb` bridge.

- `session-absorb` - repo-local executable wrapper for the shared runtime.
- `skills/shared/session_absorb_core.py` - main Python implementation for listing, digesting, querying, and launching session transfers.
- `skills/codex/session-absorb/` - Codex skill package.
- `skills/claude/session-absorb/` - Claude Code skill package.
- `docs/codebase/` - durable, git-tracked project docs.
- `.context-copilot/` and `.session-absorb/` - generated runtime artifacts; treat them as operational output, not core source.

## Build, Test, and Development Commands

There is no formal build pipeline in this snapshot. Use targeted validation:

- `python3 -m py_compile skills/shared/session_absorb_core.py` - syntax check for the shared runtime.
- `session-absorb list --limit 5` - smoke test the installed wrapper and session discovery.
- `python3 skills/shared/session_absorb_core.py --help` - verify CLI subcommands and argument parsing.
- `session-absorb digest --source claude --session <id>` - validate transcript parsing on a real session.

Run commands from the repository root unless a task explicitly needs another cwd.

## Coding Style & Naming Conventions

- Use Python 3 with 4-space indentation and standard-library-first solutions.
- Keep shell wrappers POSIX-friendly and minimal.
- Use `snake_case` for Python functions and files, and `kebab-case` for skill directories.
- Keep Markdown instructions concise and command-oriented.
- Avoid broad rewrites of generated docs or runtime artifact folders unless the task is specifically about those outputs.

## Testing Guidelines

There is no committed unit test suite yet. For every change:

- run `py_compile` on touched Python files;
- run at least one real CLI smoke test through `session-absorb`;
- verify both same-platform and cross-platform paths when editing launch or brief logic.

Prefer targeted manual validation over invented test scaffolding.

## Commit & Pull Request Guidelines

This directory is currently not a git worktree, so there is no local commit history to infer conventions from. If the repo is later initialized or copied into a git project, use Conventional Commits such as `feat: add bridge brief fallback` or `fix: resolve symlink wrapper path`.

PRs should include:

- a short description of the behavioral change;
- exact validation commands run;
- sample session IDs or commands used for smoke testing;
- screenshots only if terminal or skill UX changed materially.

## Agent-Specific Notes

- Prefer editing `skills/shared/session_absorb_core.py` first; keep the Claude and Codex skill wrappers thin.
- Preserve the fallback behavior: when live resume/fork is unreliable, degrade to transcript-backed briefs instead of forcing a fake live bridge.
