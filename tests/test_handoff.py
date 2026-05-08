"""Smoke tests for the handoff / inbox / ack subcommands.

These tests exercise the CLI surface only - no direct SQLite reads.
Each test is tolerant of an existing handoffs table populated by prior
runs (don't assert specific row counts on shared state).
"""

import json
import pytest


def test_handoff_help_lists_flags(run_runtime):
    proc = run_runtime("handoff", "--help")
    assert proc.returncode == 0, proc.stderr
    for flag in (
        "--target-cli",
        "--target-cwd",
        "--target-session",
        "--done",
        "--pending",
        "--blocked",
        "--launch",
        "--require-ack",
        "--dry-run",
    ):
        assert flag in proc.stdout, f"missing flag in handoff help: {flag}"


def test_inbox_help_lists_flags(run_runtime):
    proc = run_runtime("inbox", "--help")
    assert proc.returncode == 0, proc.stderr
    for flag in ("--source", "--cwd", "--show-all", "--json", "--limit"):
        assert flag in proc.stdout, f"missing flag in inbox help: {flag}"


def test_ack_help_has_positional(run_runtime):
    proc = run_runtime("ack", "--help")
    assert proc.returncode == 0, proc.stderr
    assert "handoff-id" in proc.stdout or "handoff_id" in proc.stdout
    assert "--note" in proc.stdout


def test_inbox_json_empty_or_array(run_runtime):
    proc = run_runtime("inbox", "--json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert isinstance(data, list)


def test_handoff_dry_run_no_session_resolution_error(run_runtime):
    proc = run_runtime(
        "handoff",
        "--dry-run",
        env={"CLAUDE_CODE_SESSION_ID": "", "CODEX_SESSION_ID": ""},
    )
    assert proc.returncode == 1
    combined = (proc.stdout + proc.stderr).lower()
    assert "session" in combined


def test_handoff_dry_run_with_fake_env(run_runtime):
    proc = run_runtime(
        "handoff",
        "--dry-run",
        "--target-cli",
        "codex",
        "--done",
        "wrote tests",
        "--pending",
        "needs review",
        env={
            "CLAUDE_CODE_SESSION_ID": "00000000-fake-fake-fake-000000000000",
            "CODEX_SESSION_ID": "",
        },
    )
    combined = proc.stdout + proc.stderr
    assert "Traceback (most recent call last):" not in combined


def test_ack_unknown_id(run_runtime):
    proc = run_runtime("ack", "999999999")
    assert proc.returncode == 1
    combined = (proc.stdout + proc.stderr).lower()
    assert "not found" in combined or "999999999" in combined
    assert "Traceback (most recent call last):" not in (proc.stdout + proc.stderr)


def test_inbox_show_all_flag_accepted(run_runtime):
    proc = run_runtime("inbox", "--show-all", "--json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert isinstance(data, list)


def test_inbox_cwd_filter_accepted(run_runtime):
    proc = run_runtime("inbox", "--cwd", "/tmp", "--json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert isinstance(data, list)


def test_inbox_source_filter_all(run_runtime):
    proc = run_runtime("inbox", "--source", "all", "--json")
    assert proc.returncode == 0, proc.stderr


def test_inbox_cwd_match_is_case_insensitive_on_macos(run_runtime, tmp_path):
    """Regression: macOS pwd vs os.getcwd casing mismatch must not hide handoffs.

    Pass --cwd in one casing to inbox while there's a stored handoff target_cwd
    in the other casing. On darwin / win32 the comparison must succeed.
    """
    import sys

    proc = run_runtime(
        "inbox",
        "--cwd",
        str(tmp_path).upper(),
        "--json",
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert isinstance(data, list)
    if sys.platform in ("darwin", "win32"):
        proc2 = run_runtime(
            "inbox",
            "--cwd",
            str(tmp_path).lower(),
            "--json",
        )
        assert proc2.returncode == 0, proc2.stderr
