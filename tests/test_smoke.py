"""Smoke tests for session-absorb runtime.

Tests are tolerant of empty session catalogs so they pass on CI runners
that lack ~/.claude or ~/.codex transcripts.
"""

import json


SUBCOMMANDS = [
    "list",
    "pick",
    "init",
    "digest",
    "ask",
    "brief",
    "launch",
    "here",
    "last",
    "fork-myself",
    "db",
    "web",
    "install",
]


def test_help_lists_all_subcommands(run_runtime):
    proc = run_runtime("--help")
    assert proc.returncode == 0, proc.stderr
    for name in SUBCOMMANDS:
        assert name in proc.stdout, f"missing subcommand in help: {name}"


def test_list_json_empty_limit(run_runtime):
    proc = run_runtime("list", "--json", "--limit", "0")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert isinstance(data, list)


def test_list_chat_menu_header(run_runtime):
    proc = run_runtime("list", "--chat-menu", "--limit", "5")
    assert proc.returncode == 0, proc.stderr
    assert "Session Chat Menu" in proc.stdout


def test_here_show_tolerant(run_runtime):
    proc = run_runtime("here", "show")
    assert proc.returncode in (0, 1)
    combined = proc.stdout + proc.stderr
    if proc.returncode == 1:
        assert "matching session" in combined.lower() or "no matching" in combined.lower()


def test_last_show_tolerant(run_runtime):
    proc = run_runtime("last", "show")
    assert proc.returncode in (0, 1)
    combined = proc.stdout + proc.stderr
    if proc.returncode == 1:
        assert "matching session" in combined.lower() or "no matching" in combined.lower()


def test_fork_myself_dry_run_with_env(run_runtime):
    proc = run_runtime(
        "fork-myself",
        "--dry-run",
        env={
            "CLAUDE_CODE_SESSION_ID": "test-fake-id-1234",
            "CODEX_SESSION_ID": "",
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert "claude -r test-fake-id-1234 --fork-session" in proc.stdout


def test_fork_myself_dry_run_no_env(run_runtime):
    proc = run_runtime(
        "fork-myself",
        "--dry-run",
        env={"CLAUDE_CODE_SESSION_ID": "", "CODEX_SESSION_ID": ""},
    )
    assert proc.returncode == 1
    combined = proc.stdout + proc.stderr
    assert "CLAUDE_CODE_SESSION_ID" in combined


def test_db_json_valid(run_runtime):
    proc = run_runtime("db", "--json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert isinstance(data, dict)
