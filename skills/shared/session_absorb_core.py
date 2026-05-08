#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mimetypes
import os
import secrets
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import webbrowser
from collections import Counter
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse


HOME = Path.home()
CODEX_HOME = HOME / ".codex"
CLAUDE_HOME = HOME / ".claude"
LOCAL_SHARE_HOME = HOME / ".local" / "share" / "session-absorb"
LOCAL_BIN_HOME = HOME / ".local" / "bin"
ALIAS_REGISTRY_PATH = LOCAL_SHARE_HOME / "aliases.json"
CATALOG_DB_PATH = LOCAL_SHARE_HOME / "sessions.db"
DEFAULT_ACTIVE_WINDOW_MINUTES = 240
DEFAULT_HOOK_TIMEOUT_SECONDS = 5
DEFAULT_CLAUDE_LIVE_ASK_TIMEOUT_SECONDS = 8
DEFAULT_WEB_PORT = 8420
DEFAULT_WEB_LIMIT = 60
DEFAULT_WEB_STREAM_INTERVAL_SECONDS = 2
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "me",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "them",
    "then",
    "this",
    "to",
    "us",
    "was",
    "we",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "would",
    "you",
    "your",
}
CODEX_TRANSCRIPT_NAME_RE = re.compile(
    r"(?P<session_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$",
    re.IGNORECASE,
)


@dataclass
class SessionRecord:
    source: str
    session_id: str
    title: str
    cwd: str
    updated_at: dt.datetime
    transcript_path: Path | None
    live_ask_supported: bool
    native_fork_supported: bool
    alias_code: str | None = None
    state: str = "unknown"


@dataclass
class Excerpt:
    index: int
    timestamp: str | None
    role: str
    text: str


@dataclass
class SessionMaterialStatus:
    status: str
    readiness: str
    message: str


@dataclass
class LiveAskOutcome:
    ok: bool
    stdout: str
    stderr: str
    returncode: int | None
    failure_reason: str | None = None
    failure_detail: str | None = None
    transport: str = "claude-live"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n")
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


SOURCE_BADGE: dict[str, str] = {
    "claude": "◆C",
    "codex":  "◇X",
}

SOURCE_ANSI: dict[str, str] = {
    "claude": "\x1b[38;5;214m",
    "codex":  "\x1b[38;5;51m",
}

ANSI_RESET = "\x1b[0m"


def current_session_id() -> str | None:
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CODEX_SESSION_ID")


def ansi_supported() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def source_label(source: str, *, width: int = 6, ansi: bool | None = None) -> str:
    if ansi is None:
        ansi = ansi_supported()
    text = source.ljust(width)
    if ansi and source in SOURCE_ANSI:
        return f"{SOURCE_ANSI[source]}{text}{ANSI_RESET}"
    return text


def source_badge(source: str) -> str:
    return SOURCE_BADGE.get(source, "  ")


def truncate(value: str, limit: int = 800) -> str:
    value = normalize_text(value)
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def ensure_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return ""


def sanitize_excerpt_text(role: str, text: str) -> str:
    text = normalize_text(text)
    if not text:
        return ""
    noisy_prefixes = (
        "<task-notification>",
        "<local-command-stdout>",
        "<local-command-caveat>",
        "<command-name>/",
        "<command-message>",
        "Base directory for this skill:",
    )
    if role == "user" and any(text.startswith(prefix) for prefix in noisy_prefixes):
        return ""
    return text


def parse_iso_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_epoch_millis(value: Any) -> dt.datetime | None:
    try:
        return dt.datetime.fromtimestamp(float(value) / 1000, tz=dt.timezone.utc)
    except Exception:
        return None


def format_dt(value: dt.datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def claude_project_slug(cwd: str) -> str:
    cleaned = cwd.strip("/")
    if not cleaned:
        return "-"
    return "-" + cleaned.replace("/", "-")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def extract_text_parts(content: Any) -> list[str]:
    parts: list[str] = []
    if isinstance(content, str):
        text = normalize_text(content)
        if text:
            parts.append(text)
        return parts
    if isinstance(content, list):
        for item in content:
            parts.extend(extract_text_parts(item))
        return parts
    if isinstance(content, dict):
        item_type = content.get("type")
        if item_type in {"text", "input_text", "output_text"}:
            text = content.get("text")
            if isinstance(text, str):
                text = normalize_text(text)
                if text:
                    parts.append(text)
        elif item_type == "tool_result":
            # Tool payloads are usually too noisy for context transfer unless explicitly requested.
            pass
        else:
            for key in ("text", "content"):
                if key in content:
                    parts.extend(extract_text_parts(content.get(key)))
        return parts
    return parts


def load_codex_sessions() -> list[SessionRecord]:
    index_path = CODEX_HOME / "session_index.jsonl"
    if not index_path.exists():
        return []
    transcript_index = build_codex_transcript_index()
    sessions: list[SessionRecord] = []
    for row in iter_jsonl(index_path):
        session_id = row.get("id")
        if not session_id:
            continue
        updated_at = parse_iso_datetime(row.get("updated_at")) or utc_now()
        transcript = transcript_index.get(str(session_id).lower())
        sessions.append(
            SessionRecord(
                source="codex",
                session_id=session_id,
                title=row.get("thread_name") or "Untitled Codex session",
                cwd=infer_codex_cwd(transcript) or "",
                updated_at=updated_at,
                transcript_path=transcript,
                live_ask_supported=False,
                native_fork_supported=True,
            )
        )
    return sessions


def infer_codex_cwd(path: Path | None) -> str | None:
    if not path or not path.exists():
        return None
    for row in iter_jsonl(path):
        if row.get("type") != "session_meta":
            continue
        payload = row.get("payload") or {}
        cwd = payload.get("cwd")
        if isinstance(cwd, str):
            return cwd
    return None


def build_codex_transcript_index() -> dict[str, Path]:
    root = CODEX_HOME / "sessions"
    if not root.exists():
        return {}
    index: dict[str, Path] = {}
    for path in root.rglob("*.jsonl"):
        match = CODEX_TRANSCRIPT_NAME_RE.search(path.name)
        if not match:
            continue
        session_id = match.group("session_id").lower()
        current = index.get(session_id)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            index[session_id] = path
    return index


def find_codex_transcript(session_id: str) -> Path | None:
    return build_codex_transcript_index().get(session_id.lower())


def load_claude_sessions() -> list[SessionRecord]:
    sessions_dir = CLAUDE_HOME / "sessions"
    if not sessions_dir.exists():
        return []
    sessions: list[SessionRecord] = []
    for header_path in sorted(sessions_dir.glob("*.json")):
        try:
            header = read_json(header_path)
        except Exception:
            continue
        session_id = header.get("sessionId")
        if not session_id:
            continue
        cwd = header.get("cwd") or ""
        transcript = find_claude_transcript(session_id, cwd)
        transcript_mtime = (
            dt.datetime.fromtimestamp(transcript.stat().st_mtime, tz=dt.timezone.utc)
            if transcript and transcript.exists()
            else None
        )
        updated_at = transcript_mtime or parse_epoch_millis(header.get("startedAt")) or utc_now()
        sessions.append(
            SessionRecord(
                source="claude",
                session_id=session_id,
                title=header.get("name") or "Untitled Claude session",
                cwd=cwd,
                updated_at=updated_at,
                transcript_path=transcript,
                live_ask_supported=True,
                native_fork_supported=True,
            )
        )
    return sessions


def compute_session_state(
    updated_at: dt.datetime,
    *,
    now: dt.datetime | None = None,
    active_window_minutes: int = DEFAULT_ACTIVE_WINDOW_MINUTES,
) -> str:
    observed_now = now or utc_now()
    if updated_at >= observed_now - dt.timedelta(minutes=max(active_window_minutes, 1)):
        return "active"
    return "idle"


def catalog_connection() -> sqlite3.Connection:
    LOCAL_SHARE_HOME.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CATALOG_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            source TEXT NOT NULL,
            session_id TEXT NOT NULL,
            alias_code TEXT,
            title TEXT NOT NULL,
            cwd TEXT,
            updated_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_state TEXT NOT NULL,
            transcript_path TEXT,
            transcript_exists INTEGER NOT NULL,
            live_ask_supported INTEGER NOT NULL,
            native_fork_supported INTEGER NOT NULL,
            first_seen_at TEXT NOT NULL,
            seen_count INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (source, session_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_state_seen ON sessions(last_state, last_seen_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS menu_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            query TEXT,
            cwd TEXT,
            active_only INTEGER NOT NULL,
            records_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_menu_snapshots_created ON menu_snapshots(created_at DESC)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS handoffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            source_cli TEXT NOT NULL,
            source_session_id TEXT NOT NULL,
            source_cwd TEXT NOT NULL,
            target_cli TEXT,
            target_cwd TEXT,
            target_session_id TEXT,
            brief_path TEXT,
            note_done TEXT,
            note_pending TEXT,
            note_blocked TEXT,
            require_ack INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            ack_at TEXT,
            ack_session_id TEXT,
            ack_note TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_handoffs_target_cwd ON handoffs(target_cwd)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_handoffs_target_session ON handoffs(target_session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_handoffs_status ON handoffs(status)"
    )
    return conn


def sync_session_catalog(
    sessions: list[SessionRecord],
    *,
    active_window_minutes: int = DEFAULT_ACTIVE_WINDOW_MINUTES,
) -> None:
    observed_now = utc_now()
    seen_at_text = observed_now.isoformat()
    with catalog_connection() as conn:
        for session in sessions:
            session.state = compute_session_state(
                session.updated_at,
                now=observed_now,
                active_window_minutes=active_window_minutes,
            )
            transcript_path = str(session.transcript_path) if session.transcript_path else None
            transcript_exists = int(bool(session.transcript_path and session.transcript_path.exists()))
            conn.execute(
                """
                INSERT INTO sessions (
                    source,
                    session_id,
                    alias_code,
                    title,
                    cwd,
                    updated_at,
                    last_seen_at,
                    last_state,
                    transcript_path,
                    transcript_exists,
                    live_ask_supported,
                    native_fork_supported,
                    first_seen_at,
                    seen_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(source, session_id) DO UPDATE SET
                    alias_code = excluded.alias_code,
                    title = excluded.title,
                    cwd = excluded.cwd,
                    updated_at = excluded.updated_at,
                    last_seen_at = excluded.last_seen_at,
                    last_state = excluded.last_state,
                    transcript_path = excluded.transcript_path,
                    transcript_exists = excluded.transcript_exists,
                    live_ask_supported = excluded.live_ask_supported,
                    native_fork_supported = excluded.native_fork_supported,
                    seen_count = sessions.seen_count + 1
                """,
                (
                    session.source,
                    session.session_id,
                    session.alias_code,
                    session.title,
                    session.cwd,
                    session.updated_at.isoformat(),
                    seen_at_text,
                    session.state,
                    transcript_path,
                    transcript_exists,
                    int(session.live_ask_supported),
                    int(session.native_fork_supported),
                    seen_at_text,
                ),
            )
        conn.execute(
            "UPDATE sessions SET last_state = 'missing' WHERE last_seen_at < ?",
            (seen_at_text,),
        )
        conn.commit()


def render_catalog_status(limit: int, as_json: bool) -> str:
    with catalog_connection() as conn:
        counts = {
            row["last_state"]: row["count"]
            for row in conn.execute(
                "SELECT last_state, COUNT(*) AS count FROM sessions GROUP BY last_state ORDER BY last_state"
            )
        }
        recent_rows = list(
            conn.execute(
                """
                SELECT source, session_id, alias_code, title, cwd, updated_at, last_seen_at, last_state
                FROM sessions
                ORDER BY last_seen_at DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        )
    unresolved_aliases = unresolved_alias_counts()
    if as_json:
        return json.dumps(
            {
                "database_path": str(CATALOG_DB_PATH),
                "counts": counts,
                "unresolved_aliases": unresolved_aliases,
                "recent": [dict(row) for row in recent_rows],
            },
            indent=2,
        )
    lines = [
        f"# Session Catalog",
        "",
        f"- Database: `{CATALOG_DB_PATH}`",
        f"- Active: `{counts.get('active', 0)}`",
        f"- Idle: `{counts.get('idle', 0)}`",
        f"- Missing: `{counts.get('missing', 0)}`",
        f"- Alias-only Codex: `{unresolved_aliases.get('codex', 0)}`",
        f"- Alias-only Claude: `{unresolved_aliases.get('claude', 0)}`",
        "",
        "STATE    SOURCE  SESSION                              TITLE",
        "-------  ------  -----------------------------------  -----",
    ]
    for row in recent_rows:
        lines.append(
            f"{row['last_state']:<7}  {row['source']:<6}  {row['session_id']:<35}  {truncate(str(row['title']), 72)}"
        )
    return "\n".join(lines)


def serialize_session_record(session: SessionRecord) -> dict[str, Any]:
    return {
        "source": session.source,
        "session_id": session.session_id,
        "title": session.title,
        "cwd": session.cwd,
        "updated_at": session.updated_at.isoformat(),
        "transcript_path": str(session.transcript_path) if session.transcript_path else None,
        "live_ask_supported": session.live_ask_supported,
        "native_fork_supported": session.native_fork_supported,
        "alias_code": session.alias_code,
        "state": session.state,
    }


def deserialize_session_record(payload: dict[str, Any]) -> SessionRecord:
    transcript_path = payload.get("transcript_path")
    return SessionRecord(
        source=str(payload.get("source") or ""),
        session_id=str(payload.get("session_id") or ""),
        title=str(payload.get("title") or "Untitled session"),
        cwd=str(payload.get("cwd") or ""),
        updated_at=parse_iso_datetime(payload.get("updated_at")) or utc_now(),
        transcript_path=Path(transcript_path) if transcript_path else None,
        live_ask_supported=bool(payload.get("live_ask_supported")),
        native_fork_supported=bool(payload.get("native_fork_supported")),
        alias_code=payload.get("alias_code") if isinstance(payload.get("alias_code"), str) else None,
        state=str(payload.get("state") or "unknown"),
    )


def write_menu_snapshot(
    records: list[SessionRecord],
    *,
    source: str,
    query: str | None,
    cwd_filter: str | None,
    active_only: bool,
) -> str:
    snapshot_id = secrets.token_hex(4)
    created_at = utc_now().isoformat()
    payload = json.dumps([serialize_session_record(item) for item in records], indent=2)
    with catalog_connection() as conn:
        conn.execute(
            """
            INSERT INTO menu_snapshots (snapshot_id, created_at, source, query, cwd, active_only, records_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                created_at,
                source,
                query,
                cwd_filter,
                int(active_only),
                payload,
            ),
        )
        conn.execute(
            """
            DELETE FROM menu_snapshots
            WHERE snapshot_id NOT IN (
                SELECT snapshot_id
                FROM menu_snapshots
                ORDER BY created_at DESC
                LIMIT 25
            )
            """
        )
        conn.commit()
    return snapshot_id


def load_menu_snapshot(snapshot_id: str | None = None) -> tuple[str, list[SessionRecord]]:
    with catalog_connection() as conn:
        if snapshot_id:
            row = conn.execute(
                "SELECT snapshot_id, records_json FROM menu_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT snapshot_id, records_json FROM menu_snapshots ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
    if not row:
        raise SystemExit(
            "No saved chat menu snapshot found. Run `session-absorb list --chat-menu` first."
        )
    records_payload = json.loads(str(row["records_json"]))
    records = [deserialize_session_record(item) for item in records_payload if isinstance(item, dict)]
    return str(row["snapshot_id"]), records


def find_claude_transcript(session_id: str, cwd: str) -> Path | None:
    projects_root = CLAUDE_HOME / "projects"
    if not projects_root.exists():
        return None
    if cwd:
        candidate = projects_root / claude_project_slug(cwd) / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate
    matches = sorted(projects_root.rglob(f"{session_id}.jsonl"))
    return matches[-1] if matches else None


def all_sessions() -> list[SessionRecord]:
    sessions = load_codex_sessions() + load_claude_sessions()
    aliases = load_alias_registry()
    alias_by_key = {
        (entry.get("source"), entry.get("session_id")): code
        for code, entry in aliases.items()
    }
    for session in sessions:
        session.alias_code = alias_by_key.get((session.source, session.session_id))
        session.state = compute_session_state(session.updated_at)
    sync_session_catalog(sessions)
    sessions.sort(key=lambda item: item.updated_at, reverse=True)
    return sessions


def unresolved_alias_entries(
    sessions: list[SessionRecord],
) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    discovered = {(session.source, session.session_id) for session in sessions}
    unresolved: dict[str, list[tuple[str, dict[str, Any]]]] = {"claude": [], "codex": []}
    for code, entry in load_alias_registry().items():
        source = entry.get("source")
        session_id = entry.get("session_id")
        if not isinstance(source, str) or not isinstance(session_id, str):
            continue
        if (source, session_id) not in discovered:
            unresolved.setdefault(source, []).append((code, entry))
    return unresolved


def session_material_status(
    session: SessionRecord,
    excerpts: list[Excerpt] | None = None,
) -> SessionMaterialStatus:
    if not session.transcript_path or not session.transcript_path.exists():
        return SessionMaterialStatus(
            status="missing_transcript",
            readiness="fork-only",
            message=(
                f"Session {session.alias_code or session.session_id} is registered, but its "
                f"{session.source.capitalize()} transcript is not available yet. Native fork is "
                "available; transcript-backed absorb commands are not yet ready."
            ),
        )
    material = excerpts if excerpts is not None else extract_session_material(session)[0]
    conversational = [entry for entry in material if entry.role in {"user", "assistant"}]
    if not material or not conversational:
        return SessionMaterialStatus(
            status="empty_transcript",
            readiness="fork-only",
            message=(
                f"Session {session.alias_code or session.session_id} has a transcript file, but no "
                "usable conversational material was extracted yet. Native fork is available; "
                "transcript-backed absorb commands are not ready."
            ),
        )
    return SessionMaterialStatus(
        status="ready",
        readiness="ready",
        message="Transcript-backed absorb commands are ready.",
    )


def unresolved_alias_counts() -> dict[str, int]:
    aliases = load_alias_registry()
    if not aliases:
        return {"codex": 0, "claude": 0}
    discovered = {(session.source, session.session_id) for session in load_codex_sessions() + load_claude_sessions()}
    counts: Counter[str] = Counter()
    for entry in aliases.values():
        source = str(entry.get("source") or "")
        session_id = str(entry.get("session_id") or "")
        if source and session_id and (source, session_id) not in discovered:
            counts[source] += 1
    return {"codex": counts.get("codex", 0), "claude": counts.get("claude", 0)}


def repo_root_path() -> Path | None:
    current = Path(__file__).resolve()
    candidate = current.parent.parent.parent
    if (candidate / "webapp").exists():
        return candidate
    return None


def webapp_asset_dir() -> Path:
    installed = LOCAL_SHARE_HOME / "webapp"
    if installed.exists():
        return installed
    repo_root = repo_root_path()
    if repo_root:
        repo_assets = repo_root / "webapp"
        if repo_assets.exists():
            return repo_assets
    raise SystemExit("Web app assets not found. Re-run `session-absorb install --repo-root ...`.")


def relative_time_label(updated_at: dt.datetime, *, now: dt.datetime) -> str:
    delta = max(now - updated_at, dt.timedelta(0))
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def build_live_snapshot(limit: int = DEFAULT_WEB_LIMIT) -> dict[str, Any]:
    sessions = all_sessions()
    observed_now = utc_now()
    limited_sessions = sessions[: max(limit, 1)]
    counts = Counter(session.state for session in sessions)
    by_source: dict[str, dict[str, int]] = {}
    project_map: dict[str, dict[str, Any]] = {}

    for source in ("claude", "codex"):
        source_sessions = [session for session in sessions if session.source == source]
        by_source[source] = {
            "total": len(source_sessions),
            "active": sum(1 for session in source_sessions if session.state == "active"),
            "idle": sum(1 for session in source_sessions if session.state == "idle"),
            "missing": sum(1 for session in source_sessions if session.state == "missing"),
        }

    for session in sessions:
        project_key = session.cwd or "(unknown)"
        entry = project_map.setdefault(
            project_key,
            {
                "cwd": project_key,
                "label": Path(project_key).name if project_key not in {"", "(unknown)"} else "unknown",
                "session_count": 0,
                "active_count": 0,
                "latest_updated_at": session.updated_at,
                "sources": set(),
            },
        )
        entry["session_count"] += 1
        if session.state == "active":
            entry["active_count"] += 1
        if session.updated_at > entry["latest_updated_at"]:
            entry["latest_updated_at"] = session.updated_at
        entry["sources"].add(session.source)

    projects = sorted(
        (
            {
                "cwd": entry["cwd"],
                "label": entry["label"],
                "session_count": entry["session_count"],
                "active_count": entry["active_count"],
                "latest_updated_at": entry["latest_updated_at"].isoformat(),
                "latest_updated_label": relative_time_label(entry["latest_updated_at"], now=observed_now),
                "sources": sorted(entry["sources"]),
            }
            for entry in project_map.values()
        ),
        key=lambda item: (item["active_count"], item["session_count"], item["latest_updated_at"]),
        reverse=True,
    )[:8]

    payload_sessions = []
    for session in limited_sessions:
        payload_sessions.append(
            {
                "source": session.source,
                "session_id": session.session_id,
                "short_id": session.session_id[:8],
                "title": session.title,
                "cwd": session.cwd,
                "cwd_label": Path(session.cwd).name if session.cwd else "unknown",
                "updated_at": session.updated_at.isoformat(),
                "updated_at_local": format_dt(session.updated_at),
                "updated_label": relative_time_label(session.updated_at, now=observed_now),
                "state": session.state,
                "alias_code": session.alias_code,
                "transcript_path": str(session.transcript_path) if session.transcript_path else None,
                "transcript_exists": bool(session.transcript_path and session.transcript_path.exists()),
                "live_ask_supported": session.live_ask_supported,
                "native_fork_supported": session.native_fork_supported,
                "digest_command": f"session-absorb digest --source {session.source} --session {session.alias_code or session.session_id}",
                "launch_command": f"session-absorb launch --source {session.source} --session {session.alias_code or session.session_id}",
            }
        )

    return {
        "generated_at": observed_now.isoformat(),
        "generated_at_local": format_dt(observed_now),
        "database_path": str(CATALOG_DB_PATH),
        "active_window_minutes": DEFAULT_ACTIVE_WINDOW_MINUTES,
        "counts": {
            "total": len(sessions),
            "active": counts.get("active", 0),
            "idle": counts.get("idle", 0),
            "missing": counts.get("missing", 0),
        },
        "by_source": by_source,
        "projects": projects,
        "sessions": payload_sessions,
    }


def render_web_status(host: str, port: int) -> str:
    return f"Session dashboard running at http://{host}:{port}"


def open_browser_if_requested(url: str, should_open: bool) -> None:
    if should_open:
        webbrowser.open(url)


def serve_web_dashboard(args: argparse.Namespace) -> int:
    asset_dir = webapp_asset_dir()
    host = args.host
    port = args.port
    limit = max(args.limit, 1)
    interval = max(args.interval, 1)
    quiet = args.quiet

    class SessionDashboardHandler(BaseHTTPRequestHandler):
        server_version = "SessionAbsorbWeb/1.0"

        def log_message(self, format: str, *message_args: Any) -> None:
            if quiet:
                return
            super().log_message(format, *message_args)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._serve_file(asset_dir / "index.html", "text/html; charset=utf-8")
                return
            if parsed.path in {"/styles.css", "/app.js"}:
                self._serve_file(asset_dir / parsed.path.lstrip("/"))
                return
            if parsed.path == "/api/live":
                query = parse_qs(parsed.query)
                response_limit = int(query.get("limit", [str(limit)])[0] or limit)
                self._serve_json(build_live_snapshot(response_limit))
                return
            if parsed.path == "/api/events":
                query = parse_qs(parsed.query)
                response_limit = int(query.get("limit", [str(limit)])[0] or limit)
                self._serve_event_stream(response_limit)
                return
            if parsed.path == "/healthz":
                self._serve_json({"ok": True, "generated_at": utc_now().isoformat()})
                return
            self.send_error(404, "Not found")

        def _serve_json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_file(self, path: Path, content_type: str | None = None) -> None:
            if not path.exists():
                self.send_error(404, "Asset not found")
                return
            body = path.read_bytes()
            mime, _ = mimetypes.guess_type(str(path))
            self.send_response(200)
            self.send_header("Content-Type", content_type or mime or "application/octet-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_event_stream(self, response_limit: int) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            last_digest = ""
            try:
                while True:
                    payload = build_live_snapshot(response_limit)
                    body = json.dumps(payload, separators=(",", ":"))
                    digest = hashlib.sha1(body.encode("utf-8")).hexdigest()
                    if digest != last_digest:
                        message = f"event: snapshot\ndata: {body}\n\n".encode("utf-8")
                        self.wfile.write(message)
                        self.wfile.flush()
                        last_digest = digest
                    time.sleep(interval)
            except (BrokenPipeError, ConnectionResetError):
                return

    server = ThreadingHTTPServer((host, port), SessionDashboardHandler)
    url = f"http://{host}:{port}"
    print(render_web_status(host, port))
    open_browser_if_requested(url, args.open_browser)
    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def _handle_shutdown_signal(signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt(f"signal {signum}")

    try:
        signal.signal(signal.SIGINT, _handle_shutdown_signal)
        signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    except ValueError:
        previous_sigint = None
        previous_sigterm = None
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSession dashboard stopped.")
    finally:
        if previous_sigint is not None:
            signal.signal(signal.SIGINT, previous_sigint)
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        server.server_close()
    return 0


def load_alias_registry() -> dict[str, dict[str, Any]]:
    if not ALIAS_REGISTRY_PATH.exists():
        return {}
    try:
        data = read_json(ALIAS_REGISTRY_PATH)
    except Exception:
        return {}
    if isinstance(data, dict):
        return {
            str(code): entry
            for code, entry in data.items()
            if isinstance(entry, dict)
        }
    return {}


def alias_entry_for_code(
    code: str,
    *,
    registry: dict[str, dict[str, Any]] | None = None,
    source: str | None = None,
) -> tuple[str, dict[str, Any]] | None:
    entries = registry or load_alias_registry()
    needle = normalize_code(code)
    entry = entries.get(needle)
    if not entry:
        return None
    if source and entry.get("source") != source:
        return None
    return needle, entry


def alias_only_message(code: str, entry: dict[str, Any]) -> str:
    source = str(entry.get("source") or "session")
    source_label = source.capitalize()
    if source == "codex":
        detail = (
            "The alias was created at session start, but Codex has not written the session "
            "to ~/.codex/session_index.jsonl yet."
        )
    else:
        detail = (
            "The alias was created at session start, but the source CLI has not exposed the "
            "underlying session for absorb commands yet."
        )
    return (
        f"Alias {code} exists, but the {source_label} session is not discoverable yet. "
        f"{detail} Try again after the session persists, or use the native CLI directly."
    )


def save_alias_registry(data: dict[str, dict[str, Any]]) -> None:
    write_json(ALIAS_REGISTRY_PATH, data)


def normalize_code(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    if not cleaned:
        raise SystemExit("Alias code must contain at least one alphanumeric character.")
    return cleaned[:8]


def split_alias_words(value: str) -> list[str]:
    return [part for part in re.split(r"[^A-Za-z0-9]+", value or "") if part]


def derive_alias_prefix(source: str, cwd: str, title: str) -> str:
    candidates = [Path(cwd).name if cwd else "", title]
    for candidate in candidates:
        words = split_alias_words(candidate)
        if not words:
            continue
        if len(words) >= 3:
            prefix = "".join(word[0] for word in words[:4]).upper()
        elif len(words) == 2:
            prefix = (words[0][:2] + words[1][:2]).upper()
        else:
            prefix = words[0][:4].upper()
        prefix = normalize_code(prefix)
        if prefix:
            return prefix[:4]
    return "CDX" if source == "codex" else "CLD"


def find_existing_alias_code(
    registry: dict[str, dict[str, Any]],
    source: str,
    session_id: str,
) -> str | None:
    for code, entry in registry.items():
        if entry.get("source") == source and entry.get("session_id") == session_id:
            return code
    return None


def generate_alias_code(
    source: str,
    session_id: str,
    title: str,
    registry: dict[str, dict[str, Any]],
    cwd: str = "",
) -> str:
    existing = find_existing_alias_code(registry, source, session_id)
    if existing:
        return existing
    prefix = derive_alias_prefix(source, cwd, title)
    for number in range(1, 1000):
        suffix = f"{number:02d}" if number < 100 else str(number)
        code = normalize_code(f"{prefix}{suffix}")
        if code not in registry or registry[code].get("session_id") == session_id:
            return code
    seed = f"{source}:{session_id}:{title}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest().upper()
    fallback = ("CDX" if source == "codex" else "CLD") + digest[:4]
    if fallback not in registry or registry[fallback].get("session_id") == session_id:
        return fallback
    raise SystemExit("Unable to generate a unique alias code.")


def format_native_title(code: str, title: str) -> str:
    base = re.sub(r"^\[[A-Z0-9]{3,8}\]\s*", "", title).strip()
    if not base:
        base = "Untitled session"
    return f"[{code}] {base}"


def find_codex_session_index_entry(session_id: str) -> tuple[Path, list[dict[str, Any]], int]:
    path = CODEX_HOME / "session_index.jsonl"
    rows = list(iter_jsonl(path))
    for idx, row in enumerate(rows):
        if row.get("id") == session_id:
            return path, rows, idx
    raise SystemExit(f"Codex session not found in session index: {session_id}")


def find_codex_session_index_entry_optional(session_id: str) -> tuple[Path, list[dict[str, Any]], int] | None:
    path = CODEX_HOME / "session_index.jsonl"
    if not path.exists():
        return None
    rows = list(iter_jsonl(path))
    for idx, row in enumerate(rows):
        if row.get("id") == session_id:
            return path, rows, idx
    return None


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")))
            handle.write("\n")


def update_codex_native_title(session_id: str, new_title: str) -> str:
    path, rows, idx = find_codex_session_index_entry(session_id)
    rows[idx]["thread_name"] = new_title
    rows[idx]["updated_at"] = utc_now().isoformat()
    write_jsonl(path, rows)
    return f"updated Codex title in {path}"


def find_claude_session_header(session_id: str) -> Path:
    sessions_dir = CLAUDE_HOME / "sessions"
    for path in sorted(sessions_dir.glob("*.json")):
        try:
            payload = read_json(path)
        except Exception:
            continue
        if payload.get("sessionId") == session_id:
            return path
    raise SystemExit(f"Claude session header not found: {session_id}")


def update_claude_native_title(session_id: str, new_title: str) -> str:
    header_path = find_claude_session_header(session_id)
    payload = read_json(header_path)
    payload["name"] = new_title
    write_json(header_path, payload)
    return f"updated Claude title in {header_path}"


def update_native_title(source: str, session_id: str, new_title: str) -> str:
    if source == "codex":
        return update_codex_native_title(session_id, new_title)
    if source == "claude":
        return update_claude_native_title(session_id, new_title)
    raise SystemExit(f"Unsupported source for native title update: {source}")


def filter_sessions(
    sessions: list[SessionRecord],
    source: str,
    query: str | None,
    cwd_filter: str | None,
    limit: int,
    active_only: bool = False,
) -> list[SessionRecord]:
    filtered: list[SessionRecord] = []
    query_lc = query.lower() if query else None
    cwd_lc = cwd_filter.lower() if cwd_filter else None
    for session in sessions:
        if source != "all" and session.source != source:
            continue
        if active_only and session.state != "active":
            continue
        haystack = f"{session.title}\n{session.cwd}\n{session.session_id}\n{session.alias_code or ''}".lower()
        if query_lc and query_lc not in haystack:
            continue
        if cwd_lc and cwd_lc not in session.cwd.lower():
            continue
        filtered.append(session)
    return filtered[:limit]


def resolve_recent_sessions(
    source: str | None,
    query: str | None,
    cwd_filter: str | None,
    limit: int,
    active_only: bool = False,
) -> list[SessionRecord]:
    return filter_sessions(all_sessions(), source or "all", query, cwd_filter, limit, active_only=active_only)


def find_session_or_die(
    source: str | None,
    session_id: str,
    *,
    query: str | None = None,
    cwd_filter: str | None = None,
    limit: int = 20,
) -> SessionRecord:
    needle = session_id.strip()
    if not needle:
        raise SystemExit("Session selector cannot be empty.")

    sessions = all_sessions()
    recent = filter_sessions(sessions, source or "all", query, cwd_filter, max(limit, 20))
    needle_lc = needle.lower()
    if needle_lc in {"latest", "recent"}:
        if recent:
            return recent[0]
        raise SystemExit("No sessions found for that selector.")

    if needle.isdigit():
        index = int(needle) - 1
        if 0 <= index < len(recent):
            return recent[index]
        raise SystemExit(
            f"Session index out of range: {needle}. Run `session-absorb init` or `session-absorb list --limit {max(limit, 10)}` first."
        )

    exact_matches: list[SessionRecord] = []
    prefix_matches: list[SessionRecord] = []
    for session in sessions:
        if source and session.source != source:
            continue
        if session.session_id == needle:
            exact_matches.append(session)
            continue
        if session.alias_code and session.alias_code.upper() == needle.upper():
            exact_matches.append(session)
            continue
        if session.session_id.startswith(needle):
            prefix_matches.append(session)
            continue
        if session.title.lower().startswith(needle_lc):
            prefix_matches.append(session)

    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        raise SystemExit(
            "Session identifier is ambiguous. Add `--source`, use the full session id, or use the indexed shortlist.\n"
            + "\n".join(
                f"- {item.source}:{item.session_id} {item.alias_code or '-'} {item.title}"
                for item in exact_matches[:10]
            )
        )
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        raise SystemExit(
            "Session identifier is ambiguous. Add `--source`, use the full session id, or use the indexed shortlist.\n"
            + "\n".join(
                f"- {item.source}:{item.session_id} {item.alias_code or '-'} {item.title}"
                for item in prefix_matches[:10]
            )
        )
    alias_match = alias_entry_for_code(needle, source=source)
    if alias_match:
        code, entry = alias_match
        raise SystemExit(alias_only_message(code, entry))
    source_label = source or "all"
    raise SystemExit(f"Session not found: {source_label}:{session_id}")


def extract_codex_excerpts(path: Path) -> tuple[list[Excerpt], Counter[str]]:
    excerpts: list[Excerpt] = []
    tools: Counter[str] = Counter()
    for row in iter_jsonl(path):
        row_type = row.get("type")
        if row_type != "response_item":
            continue
        payload = row.get("payload") or {}
        payload_type = payload.get("type")
        timestamp = row.get("timestamp")
        if payload_type == "message":
            role = payload.get("role") or "unknown"
            if role not in {"user", "assistant"}:
                continue
            text = "\n\n".join(extract_text_parts(payload.get("content")))
            text = sanitize_excerpt_text(role, text)
            if text:
                excerpts.append(
                    Excerpt(
                        index=len(excerpts),
                        timestamp=timestamp,
                        role=role,
                        text=text,
                    )
                )
        elif payload_type == "function_call":
            name = payload.get("name")
            if isinstance(name, str):
                tools[name] += 1
        elif payload_type == "function_call_output":
            text = payload.get("output")
            if isinstance(text, str):
                cleaned = normalize_text(text)
                if cleaned:
                    excerpts.append(
                        Excerpt(
                            index=len(excerpts),
                            timestamp=timestamp,
                            role="tool",
                            text=cleaned,
                        )
                    )
    return excerpts, tools


def extract_claude_excerpts(path: Path) -> tuple[list[Excerpt], Counter[str]]:
    excerpts: list[Excerpt] = []
    tools: Counter[str] = Counter()
    for row in iter_jsonl(path):
        row_type = row.get("type")
        timestamp = row.get("timestamp")
        if row_type == "user":
            message = row.get("message") or {}
            text = "\n\n".join(extract_text_parts(message.get("content")))
            text = sanitize_excerpt_text("user", text)
            if text:
                excerpts.append(
                    Excerpt(
                        index=len(excerpts),
                        timestamp=timestamp,
                        role="user",
                        text=text,
                    )
                )
        elif row_type == "assistant":
            message = row.get("message") or {}
            content = message.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_use":
                        name = item.get("name")
                        if isinstance(name, str):
                            tools[name] += 1
            text = "\n\n".join(extract_text_parts(content))
            text = sanitize_excerpt_text("assistant", text)
            if text:
                excerpts.append(
                    Excerpt(
                        index=len(excerpts),
                        timestamp=timestamp,
                        role="assistant",
                        text=text,
                    )
                )
    return excerpts, tools


def extract_session_material(session: SessionRecord) -> tuple[list[Excerpt], Counter[str]]:
    if not session.transcript_path or not session.transcript_path.exists():
        return [], Counter()
    if session.source == "codex":
        return extract_codex_excerpts(session.transcript_path)
    if session.source == "claude":
        return extract_claude_excerpts(session.transcript_path)
    return [], Counter()


def render_material_unavailable(
    session: SessionRecord,
    status: SessionMaterialStatus,
    *,
    action: str,
    fallback_reason: str | None = None,
) -> str:
    lines = [
        f"# Session {action.title()} Unavailable: {session.source}:{session.session_id}",
        "",
        f"- Readiness: `{status.readiness}`",
        f"- Reason: {status.message}",
    ]
    if fallback_reason:
        lines.append(f"- Live fallback: {fallback_reason}")
    lines.extend(
        [
            f"- Native fork: `{session.native_fork_supported}`",
            f"- Transcript: `{session.transcript_path or 'missing'}`",
            "",
        ]
    )
    if status.readiness == "fork-only":
        lines.append("Native fork is available; transcript-backed absorb commands are not ready yet.")
    else:
        lines.append("Wait for session discovery to catch up before using absorb commands on this alias.")
    lines.append("")
    return "\n".join(lines)


def classify_material_state(session: SessionRecord, excerpts: list[Excerpt]) -> tuple[str, str]:
    status = session_material_status(session, excerpts)
    return status.status, status.message


def recent_by_role(excerpts: list[Excerpt], role: str, limit: int) -> list[Excerpt]:
    matches = [item for item in excerpts if item.role == role]
    return matches[-limit:]


def tokenize(value: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_./:-]+", value.lower())
    return [word for word in words if len(word) >= 3 and word not in STOPWORDS]


def rank_excerpts(excerpts: list[Excerpt], question: str, limit: int) -> list[Excerpt]:
    terms = tokenize(question)
    if not excerpts:
        return []
    if not terms:
        return excerpts[-limit:]
    scored: list[tuple[float, Excerpt]] = []
    total = max(len(excerpts), 1)
    question_lc = question.lower()
    for excerpt in excerpts:
        haystack = excerpt.text.lower()
        term_hits = sum(haystack.count(term) for term in terms)
        if question_lc and question_lc in haystack:
            term_hits += 4
        recency = (excerpt.index + 1) / total
        score = float(term_hits * 3) + recency
        if score > 0:
            scored.append((score, excerpt))
    scored.sort(key=lambda item: (item[0], item[1].index), reverse=True)
    if scored:
        return [excerpt for _, excerpt in scored[:limit]]
    return excerpts[-limit:]


def excerpt_has_error_marker(text: str) -> bool:
    haystack = text.lower()
    markers = ("error", "exception", "traceback", "failed", "timeout", "warning", "blocked", "stderr")
    return any(marker in haystack for marker in markers)


def looks_like_raw_tool_dump(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 12:
        return False
    path_like = sum(1 for line in lines if "/" in line or line.endswith(".py") or line.endswith(".jsonl"))
    listing_like = sum(
        1
        for line in lines
        if line.startswith(("-", "drwx", "total"))
        or re.fullmatch(r"[A-Za-z0-9._/@:-]+", line) is not None
    )
    return path_like >= max(8, len(lines) // 3) or listing_like >= max(10, len(lines) // 2)


def looks_like_bridge_noise(excerpt: Excerpt) -> bool:
    haystack = excerpt.text.lower()
    if "<subagent_notification>" in haystack:
        return True
    if '"previous_status"' in haystack or '"submission_id"' in haystack:
        return True
    if excerpt.role == "tool" and haystack.lstrip().startswith('{"status":'):
        return True
    if excerpt.role == "tool" and haystack.lstrip().startswith('{"agent_id":'):
        return True
    if haystack.startswith("chunk id:") or "process exited with code" in haystack:
        return True
    if haystack.startswith("the user wants to run session-absorb"):
        return True
    if '"agent_path"' in haystack and '"status"' in haystack:
        return True
    if excerpt.role == "tool" and "original token count:" in haystack:
        return True
    return False


def select_brief_excerpts(excerpts: list[Excerpt], question: str, limit: int) -> list[Excerpt]:
    terms = tokenize(question)
    question_lc = question.lower()
    scored: list[tuple[float, Excerpt]] = []
    total = max(len(excerpts), 1)
    for excerpt in excerpts:
        if looks_like_bridge_noise(excerpt):
            continue
        haystack = excerpt.text.lower()
        term_hits = sum(haystack.count(term) for term in terms)
        if question_lc and question_lc in haystack:
            term_hits += 4
        score = float(term_hits * 3) + ((excerpt.index + 1) / total)
        if excerpt.role == "tool":
            has_signal = bool(term_hits) or excerpt_has_error_marker(excerpt.text)
            if not has_signal:
                score = 0
            else:
                score *= 0.35
                if looks_like_raw_tool_dump(excerpt.text):
                    score *= 0.15
        if score > 0:
            scored.append((score, excerpt))
    scored.sort(key=lambda item: (item[0], item[1].index), reverse=True)
    selected: list[Excerpt] = []
    tool_count = 0
    for _, excerpt in scored:
        if excerpt.role == "tool":
            if tool_count >= 1:
                continue
            tool_count += 1
        selected.append(excerpt)
        if len(selected) >= limit:
            break
    if selected:
        return selected
    fallback = [
        item
        for item in excerpts
        if item.role in {"user", "assistant"} and not looks_like_bridge_noise(item)
    ]
    return fallback[-limit:] if fallback else excerpts[-limit:]


def render_list(records: list[SessionRecord], as_json: bool, show_index: bool = False) -> str:
    current_id = current_session_id()
    if as_json:
        return json.dumps(
            [
                {
                    "alias_code": item.alias_code,
                    "state": item.state,
                    "source": item.source,
                    "session_id": item.session_id,
                    "title": item.title,
                    "cwd": item.cwd,
                    "updated_at": item.updated_at.isoformat(),
                    "transcript_path": str(item.transcript_path) if item.transcript_path else None,
                    "live_ask_supported": item.live_ask_supported,
                    "native_fork_supported": item.native_fork_supported,
                    "readiness": session_material_status(item).readiness,
                    "is_current": item.session_id == current_id,
                }
                for item in records
            ],
            indent=2,
        )
    if not records:
        return "No sessions found."
    if show_index:
        lines = [
            "#   STATE   CODE     SOURCE  UPDATED                  SESSION                              TITLE",
            "--  ------  -------  ------  -----------------------  -----------------------------------  -----",
        ]
    else:
        lines = [
            "STATE   CODE     SOURCE  UPDATED                  SESSION                              TITLE",
            "------  -------  ------  -----------------------  -----------------------------------  -----",
        ]
    use_ansi = ansi_supported()
    for idx, item in enumerate(records, start=1):
        prefix = f"{idx:>2}  " if show_index else ""
        lines.append(
            f"{prefix}{item.state:<6}  {(item.alias_code or '-'): <7}  {source_label(item.source, ansi=use_ansi)}  {format_dt(item.updated_at):<23}  {item.session_id:<35}  {truncate(item.title, 72)}"
        )
        readiness = session_material_status(item)
        if readiness.readiness != "ready":
            lines.append(f"          readiness: {readiness.readiness} ({readiness.message})")
        if item.cwd:
            lines.append(f"          cwd: {item.cwd}")
        if item.transcript_path:
            lines.append(f"          transcript: {item.transcript_path}")
    unresolved = unresolved_alias_counts()
    if unresolved.get("codex") or unresolved.get("claude"):
        lines.extend(
            [
                "",
                f"Alias-only sessions not yet discoverable: codex={unresolved.get('codex', 0)}, claude={unresolved.get('claude', 0)}",
            ]
        )
    return "\n".join(lines)


def render_digest(session: SessionRecord, excerpts: list[Excerpt], tools: Counter[str]) -> str:
    material_state, material_detail = classify_material_state(session, excerpts)
    user_turns = recent_by_role(excerpts, "user", 5)
    assistant_turns = recent_by_role(excerpts, "assistant", 5)
    lines = [
        f"# Session Digest: {session.source}:{session.session_id}",
        "",
        f"- Title: `{session.title}`",
        f"- Updated: `{format_dt(session.updated_at)}`",
        f"- CWD: `{session.cwd or 'unknown'}`",
        f"- Transcript: `{session.transcript_path or 'missing'}`",
        f"- Native fork: `{session.native_fork_supported}`",
        f"- Live ask: `{session.live_ask_supported}`",
        f"- Material state: `{material_state}`",
        f"- Extracted messages: `{len(excerpts)}`",
        "",
    ]
    if material_detail:
        lines.extend([f"Material detail: {material_detail}", ""])
    if tools:
        lines.extend(
            [
                "## Tool usage",
                "",
                *[f"- `{name}` x{count}" for name, count in tools.most_common(12)],
                "",
            ]
        )
    if user_turns:
        lines.append("## Recent user turns")
        lines.append("")
        for entry in user_turns:
            lines.append(f"- {truncate(entry.text, 900)}")
        lines.append("")
    if assistant_turns:
        lines.append("## Recent assistant turns")
        lines.append("")
        for entry in assistant_turns:
            lines.append(f"- {truncate(entry.text, 900)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_question_pack(
    session: SessionRecord,
    question: str,
    excerpts: list[Excerpt],
    fallback_reason: str | None = None,
    transcript_status: str | None = None,
) -> str:
    lines = [
        f"# Session Question Pack: {session.source}:{session.session_id}",
        "",
        f"Question: {question}",
        "",
        "Use these excerpts to answer from the session without re-reading the full transcript.",
        "",
    ]
    if fallback_reason:
        lines.extend([f"Fallback: {fallback_reason}", ""])
    if transcript_status:
        lines.extend([f"Transcript status: {transcript_status}", ""])
    if not excerpts:
        lines.append("No relevant excerpts were extracted.")
        lines.append("")
        return "\n".join(lines)
    for entry in excerpts:
        label = entry.role.upper()
        lines.append(f"## {label} excerpt")
        lines.append("")
        if entry.timestamp:
            lines.append(f"- Timestamp: `{entry.timestamp}`")
        lines.append(f"- Message index: `{entry.index}`")
        lines.append("")
        lines.append(truncate(entry.text, 1600))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def brief_dir(workspace: Path) -> Path:
    target = workspace / ".session-absorb" / "briefs"
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_brief(
    workspace: Path,
    session: SessionRecord,
    question: str | None,
    excerpts: list[Excerpt],
    tools: Counter[str],
    *,
    limit: int,
    notes: dict | None = None,
) -> Path:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    safe_id = session.session_id.replace("/", "-")
    path = brief_dir(workspace) / f"{stamp}-{session.source}-{safe_id}.md"
    material_state, material_detail = classify_material_state(session, excerpts)
    brief_ready_excerpts = [item for item in excerpts if not looks_like_bridge_noise(item)]
    recent_users = recent_by_role(brief_ready_excerpts, "user", 6)
    recent_assistant = recent_by_role(brief_ready_excerpts, "assistant", 6)
    ranked = select_brief_excerpts(excerpts, question or session.title, limit)
    lines = [
        f"# Session Absorb Brief",
        "",
        f"- Source: `{session.source}`",
        f"- Session: `{session.session_id}`",
        f"- Title: `{session.title}`",
        f"- Updated: `{format_dt(session.updated_at)}`",
        f"- CWD: `{session.cwd or 'unknown'}`",
        f"- Transcript: `{session.transcript_path or 'missing'}`",
        "",
    ]
    if notes:
        done = (notes.get("done") or "").strip()
        pending = (notes.get("pending") or "").strip()
        blocked = (notes.get("blocked") or "").strip()
        if done or pending or blocked:
            lines.extend([
                "## Handoff Notes",
                "",
                "### What's done",
                done or "(none)",
                "",
                "### What's pending",
                pending or "(none)",
                "",
                "### What's blocked",
                blocked or "(none)",
                "",
                "---",
                "",
            ])
    lines.extend([
        "## Absorb Goal",
        "",
        question or "Absorb the important context from this session into the current conversation.",
        "",
        "## Transfer Readiness",
        "",
        f"- Status: `{material_state}`",
        f"- Detail: {material_detail or 'ready'}",
        "",
    ])
    if tools:
        lines.extend(["## Dominant tools", "", *[f"- `{name}` x{count}" for name, count in tools.most_common(10)], ""])
    if recent_users:
        lines.append("## Recent user prompts")
        lines.append("")
        for item in recent_users:
            lines.append(f"- {truncate(item.text, 600)}")
        lines.append("")
    if recent_assistant:
        lines.append("## Recent assistant responses")
        lines.append("")
        for item in recent_assistant:
            lines.append(f"- {truncate(item.text, 700)}")
        lines.append("")
    if ranked and material_state not in {"missing_transcript", "empty_transcript"}:
        lines.append("## Highest-signal excerpts")
        lines.append("")
        for item in ranked:
            lines.append(f"### {item.role.upper()} #{item.index}")
            lines.append("")
            lines.append(truncate(item.text, 1500 if item.role != "tool" else 800))
            lines.append("")
    elif material_state in {"missing_transcript", "empty_transcript"}:
        lines.extend(
            [
                "## Brief Limitation",
                "",
                "This session is not ready for transcript-backed transfer yet. Prefer native fork if the target CLI matches, or retry the brief after transcript material persists.",
                "",
            ]
        )
    lines.extend(
        [
            "## Instructions For The Receiving Session",
            "",
            "1. Read this brief fully before acting.",
            "2. Treat it as a compressed transfer, not the complete truth. Re-open the source transcript path if the question depends on nuance.",
            "3. Answer with the minimum context needed to continue the target task.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def live_answer_anchor_terms(session: SessionRecord, question: str) -> list[str]:
    terms = tokenize(question)
    if session.cwd:
        terms.extend(tokenize(Path(session.cwd).name))
    terms.extend(tokenize(session.title))
    deduped: list[str] = []
    for term in terms:
        if term not in deduped:
            deduped.append(term)
    return deduped[:12]


def classify_live_claude_failure(text: str) -> tuple[str | None, str | None]:
    haystack = text.lower()
    patterns = [
        ("not_resumable", "session not resumable by claude -r", "no conversation found with session id"),
        ("stale_marker", "resumed session marker stale or already consumed", "no deferred tool marker found"),
        ("stale_marker", "resumed session marker stale or already consumed", "provide a prompt to continue the conversation"),
        ("stale_marker", "resumed session marker stale or already consumed", "marker is stale"),
        ("stale_marker", "resumed session marker stale or already consumed", "tool already ran"),
        ("tool_refusal", "live output was a tool/refusal boilerplate", "i don't have access to the bash tool"),
        ("tool_refusal", "live output was a tool/refusal boilerplate", "i don't have access to"),
        ("tool_refusal", "live output was a tool/refusal boilerplate", "i cannot access"),
        ("tool_refusal", "live output was a tool/refusal boilerplate", "i can't access"),
    ]
    for code, detail, pattern in patterns:
        if pattern in haystack:
            return code, detail
    return None, None


def looks_like_low_quality_live_answer(session: SessionRecord, question: str, stdout: str) -> str | None:
    lowered = stdout.lower()
    _, detail = classify_live_claude_failure(lowered)
    if detail:
        return detail
    anchors = live_answer_anchor_terms(session, question)
    if "```" in stdout and not any(term in lowered for term in anchors):
        return "live output looked unrelated to session context"
    return None


def assess_live_claude_answer(
    session: SessionRecord,
    question: str,
    result: subprocess.CompletedProcess[str],
) -> LiveAskOutcome:
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    combined = f"{stdout}\n{stderr}"
    failure_reason, failure_detail = classify_live_claude_failure(combined)
    if result.returncode != 0:
        return LiveAskOutcome(
            ok=False,
            stdout=stdout,
            stderr=stderr,
            returncode=result.returncode,
            failure_reason=failure_reason or "nonzero_exit",
            failure_detail=failure_detail or "Claude live ask returned a non-zero exit code.",
        )
    if not stdout.strip():
        return LiveAskOutcome(
            ok=False,
            stdout=stdout,
            stderr=stderr,
            returncode=result.returncode,
            failure_reason="empty_output",
            failure_detail="Claude live ask returned success but no output.",
        )
    quality_detail = looks_like_low_quality_live_answer(session, question, stdout)
    if quality_detail:
        return LiveAskOutcome(
            ok=False,
            stdout=stdout,
            stderr=stderr,
            returncode=result.returncode,
            failure_reason="quality_gate",
            failure_detail=quality_detail,
        )
    return LiveAskOutcome(
        ok=True,
        stdout=stdout,
        stderr=stderr,
        returncode=result.returncode,
    )


def format_live_ask_fallback_reason(session: SessionRecord, outcome: LiveAskOutcome) -> str:
    detail = outcome.failure_detail or "Claude live ask failed."
    return f"Claude live ask failed; using transcript fallback instead. Reason: {detail}"


def format_live_ask_failure(session: SessionRecord, outcome: LiveAskOutcome) -> str:
    stderr = ensure_text(outcome.stderr).strip()
    stdout = ensure_text(outcome.stdout).strip()
    lines = [
        f"Claude live ask failed for {session.source}:{session.session_id}.",
        f"Reason: {outcome.failure_detail or 'unknown failure'}",
    ]
    if stderr:
        lines.extend(["", stderr])
    elif stdout:
        lines.extend(["", stdout])
    return "\n".join(lines).rstrip() + "\n"


def run_live_claude_question(
    session: SessionRecord,
    question: str,
    timeout_seconds: int = DEFAULT_CLAUDE_LIVE_ASK_TIMEOUT_SECONDS,
) -> LiveAskOutcome:
    if not session.cwd:
        return LiveAskOutcome(
            ok=False,
            stdout="",
            stderr="",
            returncode=None,
            failure_reason="missing_cwd",
            failure_detail="Claude live ask requires a session cwd.",
        )
    cmd = [
        "claude",
        "-p",
        "-r",
        session.session_id,
        "--fork-session",
        "--tools",
        "",
        question,
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=session.cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return LiveAskOutcome(
            ok=False,
            stdout="",
            stderr="",
            returncode=None,
            failure_reason="missing_cli",
            failure_detail="Claude CLI is not installed or not on PATH.",
        )
    except subprocess.TimeoutExpired as exc:
        return LiveAskOutcome(
            ok=False,
            stdout=ensure_text(exc.stdout),
            stderr=ensure_text(exc.stderr),
            returncode=None,
            failure_reason="timeout",
            failure_detail=f"Claude live ask exceeded {timeout_seconds}s.",
        )
    return assess_live_claude_answer(session, question, result)


def shell_command_for_native_fork(session: SessionRecord, question: str | None) -> tuple[str, str]:
    cwd = session.cwd or str(Path.cwd())
    if session.source == "codex":
        argv = ["codex", "fork", session.session_id]
        if question:
            argv.append(question)
    elif session.source == "claude":
        argv = ["claude", "-r", session.session_id, "--fork-session"]
        if question:
            argv.append(question)
    else:
        raise SystemExit(f"Native fork is not supported for source: {session.source}")
    shell_cmd = f"cd {shlex.quote(cwd)} && " + " ".join(shlex.quote(part) for part in argv)
    return cwd, shell_cmd


def shell_command_for_brief_launch(
    target_cli: str,
    cwd: str,
    brief_path: Path,
    question: str | None,
) -> str:
    prompt = f"Absorb the session brief at {brief_path}. Read it first, then continue the task."
    if question:
        prompt += f" Focus question: {question}"
    argv = [target_cli, prompt]
    return f"cd {shlex.quote(cwd)} && " + " ".join(shlex.quote(part) for part in argv)


def shell_command_for_interactive_list(args: argparse.Namespace) -> str:
    argv = ["session-absorb", "list", "--interactive"]
    if args.source and args.source != "all":
        argv.extend(["--source", args.source])
    if args.query:
        argv.extend(["--query", args.query])
    if args.cwd:
        argv.extend(["--cwd", args.cwd])
    if args.limit:
        argv.extend(["--limit", str(args.limit)])
    if args.active_only:
        argv.append("--active-only")
    if getattr(args, "select_only", False):
        argv.append("--select-only")
    return " ".join(shlex.quote(part) for part in argv)


def _first_available(*candidates: str) -> str | None:
    for name in candidates:
        if shutil.which(name):
            return name
    return None


def _print_manual_fallback(shell_cmd: str) -> str:
    print(
        f"[context-absorb] No supported terminal emulator found. "
        f"Run this command manually:\n\n  {shell_cmd}\n"
    )
    return shell_cmd


def open_in_terminal(shell_cmd: str, dry_run: bool) -> str:
    if dry_run:
        return shell_cmd
    if sys.platform == "darwin":
        applescript = [
            "osascript",
            "-e",
            'tell application "Terminal" to activate',
            "-e",
            f'tell application "Terminal" to do script {json.dumps(shell_cmd)}',
        ]
        result = subprocess.run(applescript, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            raise SystemExit(result.stderr.strip() or "Failed to open Terminal.")
        return shell_cmd
    if sys.platform.startswith("linux"):
        launcher = _first_available("x-terminal-emulator")
        if launcher:
            subprocess.Popen([launcher, "-e", shell_cmd])
            return shell_cmd
        launcher = _first_available("gnome-terminal")
        if launcher:
            subprocess.Popen([launcher, "--", "bash", "-c", shell_cmd])
            return shell_cmd
        launcher = _first_available("konsole")
        if launcher:
            subprocess.Popen([launcher, "-e", "bash", "-c", shell_cmd])
            return shell_cmd
        launcher = _first_available("xfce4-terminal")
        if launcher:
            subprocess.Popen([launcher, "-e", shell_cmd])
            return shell_cmd
        launcher = _first_available("alacritty")
        if launcher:
            subprocess.Popen([launcher, "-e", "bash", "-c", shell_cmd])
            return shell_cmd
        launcher = _first_available("kitty")
        if launcher:
            subprocess.Popen([launcher, "bash", "-c", shell_cmd])
            return shell_cmd
        launcher = _first_available("xterm")
        if launcher:
            subprocess.Popen([launcher, "-e", shell_cmd])
            return shell_cmd
        return _print_manual_fallback(shell_cmd)
    if sys.platform == "win32":
        launcher = _first_available("wt.exe", "wt")
        if launcher:
            subprocess.Popen([launcher, "--", "powershell", "-NoExit", "-Command", shell_cmd])
            return shell_cmd
        launcher = _first_available("cmd.exe", "cmd")
        if launcher:
            subprocess.Popen([launcher, "/c", "start", "cmd.exe", "/k", shell_cmd])
            return shell_cmd
        return _print_manual_fallback(shell_cmd)
    return _print_manual_fallback(shell_cmd)


def codex_session_start_hook_path() -> Path:
    return LOCAL_SHARE_HOME / "session-start-hook-codex.sh"


def claude_session_start_hook_path() -> Path:
    return LOCAL_SHARE_HOME / "session-start-hook-claude.sh"


def find_session_record(source: str, session_id: str) -> SessionRecord | None:
    for session in all_sessions():
        if session.source == source and session.session_id == session_id:
            return session
    return None


def alias_registry_entry(
    *,
    source: str,
    session_id: str,
    code: str,
    cwd: str,
    title: str,
    assigned_by: str,
) -> dict[str, Any]:
    return {
        "source": source,
        "session_id": session_id,
        "title": title,
        "cwd": cwd,
        "updated_at": utc_now().isoformat(),
        "assigned_by": assigned_by,
        "code": code,
    }


def ensure_session_alias(
    *,
    source: str,
    session_id: str,
    cwd: str,
    title: str,
    assigned_by: str,
) -> tuple[str, bool]:
    registry = load_alias_registry()
    existing_code = find_existing_alias_code(registry, source, session_id)
    if existing_code:
        return existing_code, False

    effective_title = title.strip() or f"{Path(cwd).name or source}-session"
    code = generate_alias_code(source, session_id, effective_title, registry, cwd)
    registry[code] = alias_registry_entry(
        source=source,
        session_id=session_id,
        code=code,
        cwd=cwd,
        title=effective_title,
        assigned_by=assigned_by,
    )
    save_alias_registry(registry)
    return code, True


def update_alias_registry_title(
    *,
    code: str,
    source: str,
    session_id: str,
    cwd: str,
    title: str,
    assigned_by: str,
) -> None:
    registry = load_alias_registry()
    registry[code] = alias_registry_entry(
        source=source,
        session_id=session_id,
        code=code,
        cwd=cwd,
        title=title,
        assigned_by=assigned_by,
    )
    save_alias_registry(registry)


def install_session_start_hook_scripts() -> list[str]:
    LOCAL_SHARE_HOME.mkdir(parents=True, exist_ok=True)
    scripts = {
        codex_session_start_hook_path(): "codex",
        claude_session_start_hook_path(): "claude",
    }
    results: list[str] = []
    for path, source in scripts.items():
        path.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'HOME_DIR="${HOME:-$(cd ~ && pwd)}"\n'
            f'exec python3 "$HOME_DIR/.local/share/session-absorb/session_absorb_core.py" hook-session-start --source {source}\n',
            encoding="utf-8",
        )
        path.chmod(0o755)
        results.append(f"installed hook script {path}")
    return results


def ensure_hook_command(
    hook_groups: list[Any],
    *,
    command: str,
    timeout: int,
) -> bool:
    for group in hook_groups:
        if not isinstance(group, dict):
            continue
        hooks = group.get("hooks")
        if not isinstance(hooks, list):
            continue
        for hook in hooks:
            if not isinstance(hook, dict):
                continue
            if hook.get("type") == "command" and hook.get("command") == command:
                if timeout and hook.get("timeout") != timeout:
                    hook["timeout"] = timeout
                    return True
                return False
    hook_groups.append(
        {
            "hooks": [
                {
                    "type": "command",
                    "command": command,
                    "timeout": timeout,
                }
            ]
        }
    )
    return True


def install_codex_session_start_hook_registration() -> str:
    config_path = CODEX_HOME / "hooks.json"
    payload: dict[str, Any] = {}
    if config_path.exists():
        try:
            loaded = read_json(config_path)
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:
            payload = {}
    hooks = payload.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        payload["hooks"] = hooks
    groups = hooks.setdefault("SessionStart", [])
    if not isinstance(groups, list):
        groups = []
        hooks["SessionStart"] = groups
    changed = ensure_hook_command(
        groups,
        command=str(codex_session_start_hook_path()),
        timeout=DEFAULT_HOOK_TIMEOUT_SECONDS,
    )
    if changed or not config_path.exists():
        write_json(config_path, payload)
        return f"updated Codex hook config {config_path}"
    return f"unchanged Codex hook config {config_path}"


def install_claude_session_start_hook_registration() -> str:
    settings_path = CLAUDE_HOME / "settings.json"
    payload: dict[str, Any] = {}
    if settings_path.exists():
        try:
            loaded = read_json(settings_path)
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:
            payload = {}
    hooks = payload.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        payload["hooks"] = hooks
    groups = hooks.setdefault("SessionStart", [])
    if not isinstance(groups, list):
        groups = []
        hooks["SessionStart"] = groups
    changed = ensure_hook_command(
        groups,
        command=str(claude_session_start_hook_path()),
        timeout=DEFAULT_HOOK_TIMEOUT_SECONDS,
    )
    if changed or not settings_path.exists():
        write_json(settings_path, payload)
        return f"updated Claude hook config {settings_path}"
    return f"unchanged Claude hook config {settings_path}"


def install_skill_link(source_dir: Path, target_dir: Path, force: bool) -> str:
    if target_dir.exists() or target_dir.is_symlink():
        if target_dir.is_symlink() and target_dir.resolve() == source_dir.resolve():
            return f"unchanged {target_dir} -> {source_dir}"
        if not force:
            raise SystemExit(
                f"Refusing to overwrite existing target without --force: {target_dir}"
            )
        if target_dir.is_symlink() or target_dir.is_file():
            target_dir.unlink()
        else:
            raise SystemExit(f"Target exists and is not a symlink: {target_dir}")
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    target_dir.symlink_to(source_dir)
    return f"linked {target_dir} -> {source_dir}"


def ensure_removed(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def install_runtime_copy(repo_root: Path) -> list[str]:
    runtime_source = repo_root / "skills" / "shared" / "session_absorb_core.py"
    runtime_target = LOCAL_SHARE_HOME / "session_absorb_core.py"
    LOCAL_SHARE_HOME.mkdir(parents=True, exist_ok=True)
    shutil.copy2(runtime_source, runtime_target)

    wrapper_path = LOCAL_BIN_HOME / "session-absorb"
    LOCAL_BIN_HOME.mkdir(parents=True, exist_ok=True)
    wrapper_path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'HOME_DIR="${HOME:-$(cd ~ && pwd)}"\n'
        'exec python3 "$HOME_DIR/.local/share/session-absorb/session_absorb_core.py" "$@"\n',
        encoding="utf-8",
    )
    wrapper_path.chmod(0o755)
    return [
        f"copied runtime {runtime_target}",
        f"installed wrapper {wrapper_path}",
        install_webapp_copy(repo_root),
        *install_session_start_hook_scripts(),
    ]


def install_skill_copy(source_dir: Path, target_dir: Path) -> str:
    ensure_removed(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_dir / "SKILL.md", target_dir / "SKILL.md")
    agents_source = source_dir / "agents" / "openai.yaml"
    if agents_source.exists():
        agents_target = target_dir / "agents"
        agents_target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(agents_source, agents_target / "openai.yaml")
    return f"copied skill {target_dir}"


def install_webapp_copy(repo_root: Path) -> str:
    source_dir = repo_root / "webapp"
    target_dir = LOCAL_SHARE_HOME / "webapp"
    ensure_removed(target_dir)
    shutil.copytree(source_dir, target_dir)
    return f"copied web app {target_dir}"


def render_init_result(session: SessionRecord, code: str, new_title: str, native_result: str) -> str:
    lines = [
        f"# Session Initialized: {session.source}:{session.session_id}",
        "",
        f"- Code: `{code}`",
        f"- New title: `{new_title}`",
        f"- Native update: {native_result}",
        "",
        "Use this session with any standard command by passing the code instead of the full id:",
        "",
        f"- `session-absorb digest --source {session.source} --session {code}`",
        f"- `session-absorb ask --source {session.source} --session {code} --question \"...\"`",
        f"- `session-absorb launch --source {session.source} --session {code}`",
        "",
    ]
    return "\n".join(lines)


def render_init_shortlist(
    records: list[SessionRecord],
    source: str | None,
    query: str | None,
    cwd_filter: str | None,
) -> str:
    lines = [
        "# Session Init",
        "",
        "Pick a session from the shortlist below, then rerun `init` with either a position, an alias, or a session id prefix.",
        "",
        "- Fastest path: `session-absorb init --session 1 --code DASH1`",
        "- Auto-code path: `session-absorb init --session 1`",
        "- Most recent session: `session-absorb init --session latest`",
        "- Natural language filter: `session-absorb init trade mirror`",
        "- Narrow the list: add `--source claude`, `--source codex`, `--query <text>`, or `--cwd <path-fragment>`",
        "",
    ]
    if source or query or cwd_filter:
        lines.extend(
            [
                "Current filters:",
                f"- source: `{source or 'all'}`",
                f"- query: `{query or '-'}`",
                f"- cwd: `{cwd_filter or '-'}`",
                "",
            ]
        )
    lines.append(render_list(records, as_json=False, show_index=True))
    return "\n".join(lines)


def render_selected_session(session: SessionRecord) -> str:
    selector = session.alias_code or session.session_id
    lines = [
        f"# Selected Session: {session.source}:{session.session_id}",
        "",
        f"- Selector: `{selector}`",
        f"- State: `{session.state}`",
        f"- Title: `{session.title}`",
        f"- Updated: `{format_dt(session.updated_at)}`",
        f"- CWD: `{session.cwd or 'unknown'}`",
        "",
        "Common next steps:",
        "",
        f"- `session-absorb init --source {session.source} --session {session.session_id}`",
        f"- `session-absorb digest --source {session.source} --session {selector}`",
        f"- `session-absorb ask --source {session.source} --session {selector} --question \"What changed?\"`",
        "",
    ]
    return "\n".join(lines)


def render_chat_menu(
    records: list[SessionRecord],
    *,
    snapshot_id: str,
    source: str,
    query: str | None,
    cwd_filter: str | None,
    active_only: bool,
) -> str:
    lines = [
        "# Session Chat Menu",
        "",
        f"- Snapshot: `{snapshot_id}`",
        f"- Source: `{source}`",
        f"- Query: `{query or '-'}`",
        f"- CWD filter: `{cwd_filter or '-'}`",
        f"- Active only: `{active_only}`",
        "",
    ]
    if not records:
        lines.append("No sessions matched.")
        lines.append("")
        lines.append("Adjust the filters and run `session-absorb list --chat-menu` again.")
        return "\n".join(lines)
    lines.extend(
        [
            "Use `session-absorb pick <number>` to select from this snapshot.",
            "Use `session-absorb pick <number> --snapshot <id>` if you want to target an older snapshot explicitly.",
            "",
            "Legend: ◆C = Claude  |  ◇X = Codex",
            "",
            "#   STATE   CODE     SRC  SOURCE  UPDATED                  TITLE",
            "--  ------  -------  ---  ------  -----------------------  -----",
        ]
    )
    current_id = current_session_id()
    for idx, session in enumerate(records, start=1):
        marker = " *self*" if session.session_id == current_id else ""
        lines.append(
            f"{idx:>2}  {session.state:<6}  {(session.alias_code or '-'): <7}  {source_badge(session.source)}   {session.source:<6}  {format_dt(session.updated_at):<23}  {truncate(session.title, 64)}{marker}"
        )
    lines.extend(
        [
            "",
            "Examples:",
            "",
            f"- `session-absorb pick 1 --snapshot {snapshot_id}`",
            f"- `session-absorb init --session 1 --query {shlex.quote(query)}`" if query else "- `session-absorb init --session 1`",
            "",
        ]
    )
    return "\n".join(lines)


def can_render_interactive_menu() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def interactive_session_menu(records: list[SessionRecord]) -> SessionRecord | None:
    if not records:
        return None
    try:
        import curses
    except Exception as exc:
        raise SystemExit(f"Interactive menu is unavailable in this Python environment: {exc}")

    def run_menu(stdscr: Any) -> SessionRecord | None:
        curses.curs_set(0)
        stdscr.keypad(True)
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, 214, -1)
            curses.init_pair(2, 51, -1)
            color_claude = curses.color_pair(1)
            color_codex = curses.color_pair(2)
            colors_ok = True
        except Exception:
            color_claude = curses.A_NORMAL
            color_codex = curses.A_NORMAL
            colors_ok = False
        index = 0
        top = 0
        while True:
            height, width = stdscr.getmaxyx()
            visible_rows = max(1, height - 4)
            if index < top:
                top = index
            if index >= top + visible_rows:
                top = index - visible_rows + 1

            stdscr.erase()
            title = "Session Absorb | arrows/jk move | Enter select | q quit  [Claude=orange Codex=cyan]"
            stdscr.addnstr(0, 0, title, width - 1, curses.A_BOLD)
            current_id_curses = current_session_id()
            for row_offset, session in enumerate(records[top : top + visible_rows], start=1):
                record_index = top + row_offset - 1
                marker = ">" if record_index == index else " "
                prefix = f"{marker} {record_index + 1:>2} {session.state[:6]:<6} {(session.alias_code or '-'): <7} "
                source_text = f"{session.source:<6}"
                self_tag = " *self*" if session.session_id == current_id_curses else ""
                suffix = f" {truncate(session.title, 42)}{self_tag}"
                row_attr = curses.A_REVERSE if record_index == index else curses.A_NORMAL
                src_color = color_claude if session.source == "claude" else color_codex if session.source == "codex" else curses.A_NORMAL
                stdscr.addnstr(row_offset, 0, prefix, width - 1, row_attr)
                col = min(len(prefix), width - 1)
                stdscr.addnstr(row_offset, col, source_text, max(0, width - 1 - col), row_attr | src_color | (curses.A_BOLD if colors_ok else 0))
                col2 = min(col + len(source_text), width - 1)
                stdscr.addnstr(row_offset, col2, suffix, max(0, width - 1 - col2), row_attr)
            selected = records[index]
            footer = f"{selected.session_id} | {selected.cwd or '-'}"
            stdscr.addnstr(height - 2, 0, footer, width - 1)
            stdscr.addnstr(height - 1, 0, "Enter selects. q cancels.", width - 1)
            stdscr.refresh()

            key = stdscr.getch()
            if key in (curses.KEY_UP, ord("k")):
                index = max(0, index - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                index = min(len(records) - 1, index + 1)
            elif key in (curses.KEY_NPAGE,):
                index = min(len(records) - 1, index + visible_rows)
            elif key in (curses.KEY_PPAGE,):
                index = max(0, index - visible_rows)
            elif key in (10, 13, curses.KEY_ENTER):
                return selected
            elif key in (27, ord("q")):
                return None

    return curses.wrapper(run_menu)


ACTION_MENU_ITEMS: list[tuple[str, str]] = [
    ("digest", "Digest this session"),
    ("ask", "Ask a question about this session"),
    ("brief", "Write a bridge brief"),
    ("launch-native", "Launch native fork in same CLI"),
    ("launch-claude", "Launch bridge into Claude"),
    ("launch-codex", "Launch bridge into Codex"),
    ("print", "Print selection only"),
    ("cancel", "Cancel"),
]


def interactive_action_menu(session: SessionRecord) -> str | None:
    try:
        import curses
    except Exception as exc:
        raise SystemExit(f"Interactive menu is unavailable in this Python environment: {exc}")

    items = ACTION_MENU_ITEMS

    def run_menu(stdscr: Any) -> str | None:
        curses.curs_set(0)
        stdscr.keypad(True)
        index = 0
        while True:
            height, width = stdscr.getmaxyx()
            stdscr.erase()
            header = (
                f"Action for {session.source}:{session.alias_code or session.session_id} "
                f"| arrows/jk move | Enter select | q cancel"
            )
            stdscr.addnstr(0, 0, header, width - 1, curses.A_BOLD)
            subheader = truncate(session.title, width - 1)
            stdscr.addnstr(1, 0, subheader, width - 1)
            for row_offset, (_key, label) in enumerate(items, start=3):
                marker = ">" if row_offset - 3 == index else " "
                line = f"{marker} {label}"
                attr = curses.A_REVERSE if row_offset - 3 == index else curses.A_NORMAL
                stdscr.addnstr(row_offset, 0, line, width - 1, attr)
            stdscr.refresh()

            key = stdscr.getch()
            if key in (curses.KEY_UP, ord("k")):
                index = max(0, index - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                index = min(len(items) - 1, index + 1)
            elif key in (10, 13, curses.KEY_ENTER):
                return items[index][0]
            elif key in (27, ord("q")):
                return None

    return curses.wrapper(run_menu)


def prompt_question(action: str) -> str:
    default = {
        "ask": "What changed, what failed, and what should the receiving session know?",
        "brief": "Absorb the implementation context and continue from there.",
    }.get(action, "")
    try:
        prompt = f"Question [{default}]: " if default else "Question: "
        text = input(prompt).strip()
    except EOFError:
        text = ""
    return text or default


def execute_action_for_session(action: str, session: SessionRecord) -> int:
    if action == "print":
        print(render_selected_session(session))
        return 0
    if action == "digest":
        ns = argparse.Namespace(source=session.source, session=session.session_id)
        return command_digest(ns)
    if action == "ask":
        question = prompt_question("ask")
        ns = argparse.Namespace(
            source=session.source,
            session=session.session_id,
            question=question,
            limit=6,
            live="auto",
        )
        return command_ask(ns)
    if action == "brief":
        question = prompt_question("brief")
        ns = argparse.Namespace(
            source=session.source,
            session=session.session_id,
            question=question,
            limit=8,
            workspace=None,
        )
        return command_brief(ns)
    if action.startswith("launch"):
        target = (
            session.source if action == "launch-native"
            else "claude" if action == "launch-claude"
            else "codex"
        )
        mode = "native" if action == "launch-native" else "auto"
        question = prompt_question("brief") if action != "launch-native" else None
        ns = argparse.Namespace(
            source=session.source,
            session=session.session_id,
            target=target,
            mode=mode,
            question=question,
            workspace=None,
            limit=8,
            dry_run=False,
        )
        return command_launch(ns)
    return 0


def get_init_query(args: argparse.Namespace) -> str | None:
    if args.query:
        return args.query
    terms = [term for term in (args.query_terms or []) if term.strip()]
    if not terms:
        return None
    return " ".join(terms)


def command_init(args: argparse.Namespace) -> int:
    query = get_init_query(args)
    if not args.session:
        records = resolve_recent_sessions(args.source, query, args.cwd, args.limit)
        print(render_init_shortlist(records, args.source, query, args.cwd))
        return 0

    session = find_session_or_die(
        args.source,
        args.session,
        query=query,
        cwd_filter=args.cwd,
        limit=args.limit,
    )
    registry = load_alias_registry()
    code = normalize_code(args.code) if args.code else generate_alias_code(
        session.source,
        session.session_id,
        session.title,
        registry,
        session.cwd,
    )
    registry_entry = registry.get(code)
    if registry_entry and registry_entry.get("session_id") != session.session_id:
        raise SystemExit(f"Alias code already belongs to another session: {code}")
    base_title = args.title or session.title
    new_title = format_native_title(code, base_title)
    if session.source == "codex":
        native_result = update_codex_native_title(session.session_id, new_title)
    elif session.source == "claude":
        native_result = update_claude_native_title(session.session_id, new_title)
    else:
        raise SystemExit(f"Unsupported source for init: {session.source}")
    registry[code] = {
        "source": session.source,
        "session_id": session.session_id,
        "title": new_title,
        "cwd": session.cwd,
        "updated_at": utc_now().isoformat(),
    }
    save_alias_registry(registry)
    print(render_init_result(session, code, new_title, native_result))
    return 0


def command_list(args: argparse.Namespace) -> int:
    records = filter_sessions(
        all_sessions(),
        args.source,
        args.query,
        args.cwd,
        args.limit,
        active_only=args.active_only,
    )
    is_tty = can_render_interactive_menu()
    use_chat_menu = args.chat_menu or (
        not is_tty
        and not args.json
        and not args.plain
        and not args.open_terminal
        and not args.interactive
    )
    if use_chat_menu:
        snapshot_id = write_menu_snapshot(
            records,
            source=args.source,
            query=args.query,
            cwd_filter=args.cwd,
            active_only=args.active_only,
        )
        print(
            render_chat_menu(
                records,
                snapshot_id=snapshot_id,
                source=args.source,
                query=args.query,
                cwd_filter=args.cwd,
                active_only=args.active_only,
            )
        )
        return 0
    wants_interactive = not args.json and not args.plain and bool(records) and (
        args.interactive or is_tty
    )
    if wants_interactive:
        if not is_tty:
            if args.open_terminal:
                print(open_in_terminal(shell_command_for_interactive_list(args), args.dry_run))
                return 0
            raise SystemExit(
                "Interactive list requires a real terminal. Re-run in a shell, or use `--open-terminal` from slash-command contexts."
            )
        selected = interactive_session_menu(records)
        if not selected:
            return 0
        if args.select_only:
            print(render_selected_session(selected))
            return 0
        action = interactive_action_menu(selected)
        if not action or action == "cancel":
            print(render_selected_session(selected))
            return 0
        return execute_action_for_session(action, selected)
    if args.open_terminal:
        print(open_in_terminal(shell_command_for_interactive_list(args), args.dry_run))
        return 0
    print(render_list(records, args.json))
    return 0


def command_here(args: argparse.Namespace) -> int:
    return _shortcut_dispatch(args, scope="here")


def command_last(args: argparse.Namespace) -> int:
    return _shortcut_dispatch(args, scope="last")


def _shortcut_dispatch(args: argparse.Namespace, scope: str) -> int:
    cwd = os.getcwd()
    current_id = current_session_id()
    sessions = filter_sessions(all_sessions(), "all", None, None, 50, active_only=False)
    candidates = [s for s in sessions if s.session_id != current_id]
    if scope == "here":
        candidates = [s for s in candidates if s.cwd == cwd]
    if not candidates:
        scope_msg = f"in cwd `{cwd}`" if scope == "here" else "anywhere"
        raise SystemExit(f"No matching session {scope_msg}.")
    candidates.sort(key=lambda s: s.updated_at, reverse=True)
    target = candidates[0]
    action = args.action
    selector = target.alias_code or target.session_id
    if action == "digest":
        ns = argparse.Namespace(source=target.source, session=selector)
        return command_digest(ns)
    if action == "ask":
        question = args.question or "What changed, what failed, and what should the receiving session know?"
        ns = argparse.Namespace(source=target.source, session=selector, question=question, limit=6, live="auto")
        return command_ask(ns)
    if action == "brief":
        question = args.question or "Absorb the implementation context and continue from there."
        ns = argparse.Namespace(source=target.source, session=selector, question=question, limit=8, workspace=None)
        return command_brief(ns)
    if action == "launch":
        ns = argparse.Namespace(
            source=target.source, session=selector, target=target.source,
            mode="native", question=None, workspace=None, limit=8, dry_run=False,
        )
        return command_launch(ns)
    if action == "show":
        print(render_selected_session(target))
        return 0
    raise SystemExit(f"Unknown action: {action}")


def command_fork_myself(args: argparse.Namespace) -> int:
    current_id = current_session_id()
    if not current_id:
        raise SystemExit(
            "fork-myself: CLAUDE_CODE_SESSION_ID and CODEX_SESSION_ID are both unset. "
            "Run this from inside an active Claude Code or Codex session."
        )
    if os.environ.get("CLAUDE_CODE_SESSION_ID"):
        source = "claude"
    elif os.environ.get("CODEX_SESSION_ID"):
        source = "codex"
    else:
        raise SystemExit("fork-myself: cannot infer source from env vars.")
    session = find_session_record(source, current_id)
    if not session:
        cwd = os.getcwd()
        session = SessionRecord(
            source=source,
            session_id=current_id,
            title=f"self-fork from {source}:{current_id[:8]}",
            cwd=cwd,
            updated_at=utc_now(),
            transcript_path=None,
            live_ask_supported=(source == "claude"),
            native_fork_supported=True,
        )
    _, shell_cmd = shell_command_for_native_fork(session, args.question)
    print(open_in_terminal(shell_cmd, args.dry_run))
    return 0


def command_db(args: argparse.Namespace) -> int:
    print(render_catalog_status(args.limit, args.json))
    return 0


def command_pick(args: argparse.Namespace) -> int:
    snapshot_id, records = load_menu_snapshot(args.snapshot)
    try:
        index = int(args.selection)
    except ValueError as exc:
        raise SystemExit(f"Selection must be a number: {args.selection}") from exc
    if index < 1 or index > len(records):
        raise SystemExit(
            f"Selection out of range: {index}. Snapshot `{snapshot_id}` has {len(records)} entries."
        )
    session = records[index - 1]
    lines = [render_selected_session(session).rstrip(), f"- Snapshot: `{snapshot_id}`", ""]
    print("\n".join(lines))
    return 0


def command_digest(args: argparse.Namespace) -> int:
    session = find_session_or_die(args.source, args.session)
    excerpts, tools = extract_session_material(session)
    material_state, material_detail = classify_material_state(session, excerpts)
    if material_state in {"missing_transcript", "empty_transcript"}:
        raise SystemExit(material_detail)
    print(render_digest(session, excerpts, tools))
    return 0


def command_brief(args: argparse.Namespace) -> int:
    session = find_session_or_die(args.source, args.session)
    excerpts, tools = extract_session_material(session)
    material_state, material_detail = classify_material_state(session, excerpts)
    if material_state in {"missing_transcript", "empty_transcript"}:
        raise SystemExit(material_detail)
    workspace = Path(args.workspace or os.getcwd()).resolve()
    path = write_brief(workspace, session, args.question, excerpts, tools, limit=args.limit)
    print(path)
    return 0


def command_ask(args: argparse.Namespace) -> int:
    session = find_session_or_die(args.source, args.session)
    fallback_reason: str | None = None
    if args.live in {"auto", "always"} and session.source == "claude":
        outcome = run_live_claude_question(session, args.question)
        if outcome.ok:
            print(outcome.stdout.strip())
            return 0
        if args.live == "always":
            sys.stderr.write(format_live_ask_failure(session, outcome))
            return outcome.returncode or 1
        fallback_reason = format_live_ask_fallback_reason(session, outcome)
    excerpts, _ = extract_session_material(session)
    material_state, material_detail = classify_material_state(session, excerpts)
    if args.live == "never" and material_state in {"missing_transcript", "empty_transcript"}:
        raise SystemExit(material_detail)
    if args.live == "auto" and fallback_reason and material_state in {"missing_transcript", "empty_transcript"}:
        raise SystemExit(f"{fallback_reason}\nTranscript status: {material_detail}")
    ranked = rank_excerpts(excerpts, args.question, args.limit)
    transcript_status = material_detail if material_state != "ready" else None
    print(render_question_pack(session, args.question, ranked, fallback_reason=fallback_reason, transcript_status=transcript_status))
    return 0


def command_launch(args: argparse.Namespace) -> int:
    session = find_session_or_die(args.source, args.session)
    target_cli = args.target or session.source
    workspace = Path(args.workspace or os.getcwd()).resolve()
    use_native = args.mode == "native" or (
        args.mode == "auto" and target_cli == session.source and session.native_fork_supported
    )
    if use_native:
        _, shell_cmd = shell_command_for_native_fork(session, args.question)
        print(open_in_terminal(shell_cmd, args.dry_run))
        return 0

    excerpts, tools = extract_session_material(session)
    material_state, material_detail = classify_material_state(session, excerpts)
    if material_state in {"missing_transcript", "empty_transcript"}:
        raise SystemExit(material_detail)
    path = write_brief(workspace, session, args.question, excerpts, tools, limit=args.limit)
    cwd = session.cwd or str(workspace)
    shell_cmd = shell_command_for_brief_launch(target_cli, cwd, path, args.question)
    print(open_in_terminal(shell_cmd, args.dry_run))
    return 0


def insert_handoff(
    source_cli: str,
    source_session_id: str,
    source_cwd: str,
    target_cli: str | None,
    target_cwd: str | None,
    target_session_id: str | None,
    brief_path: str | None,
    note_done: str | None,
    note_pending: str | None,
    note_blocked: str | None,
    require_ack: bool,
) -> int:
    created_at = utc_now().isoformat()
    with catalog_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO handoffs (
                created_at, source_cli, source_session_id, source_cwd,
                target_cli, target_cwd, target_session_id, brief_path,
                note_done, note_pending, note_blocked, require_ack, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                created_at,
                source_cli,
                source_session_id,
                source_cwd,
                target_cli,
                target_cwd,
                target_session_id,
                brief_path,
                note_done,
                note_pending,
                note_blocked,
                int(bool(require_ack)),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def fetch_handoff_by_id(handoff_id: int) -> dict | None:
    with catalog_connection() as conn:
        row = conn.execute(
            "SELECT * FROM handoffs WHERE id = ?", (handoff_id,)
        ).fetchone()
        return dict(row) if row else None


def fetch_inbox(
    target_cli: str | None,
    cwd: str,
    session_id: str | None,
    *,
    show_all: bool,
    limit: int,
) -> list[dict]:
    with catalog_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM handoffs ORDER BY id DESC"
        ).fetchall()
    results: list[dict] = []
    for row in rows:
        item = dict(row)
        if not show_all and item.get("status") != "pending":
            continue
        t_cli = item.get("target_cli")
        if t_cli and target_cli and t_cli != target_cli:
            continue
        t_cwd = item.get("target_cwd")
        if t_cwd and not cwd.startswith(t_cwd):
            continue
        t_sess = item.get("target_session_id")
        if t_sess and session_id and t_sess != session_id:
            continue
        if t_sess and not session_id:
            continue
        results.append(item)
        if len(results) >= limit:
            break
    return results


def update_handoff_ack(handoff_id: int, ack_session_id: str | None, note: str | None) -> bool:
    ack_at = utc_now().isoformat()
    with catalog_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE handoffs
            SET status = 'acked', ack_at = ?, ack_session_id = ?, ack_note = ?
            WHERE id = ?
            """,
            (ack_at, ack_session_id, note, handoff_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def _relative_age(iso: str | None) -> str:
    if not iso:
        return "-"
    parsed = parse_iso_datetime(iso)
    if not parsed:
        return "-"
    delta = utc_now() - parsed
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def format_handoff_row(row: dict) -> tuple[str, str, str, str, str, str]:
    rid = str(row.get("id") or "?")
    age = _relative_age(row.get("created_at"))
    src_cli = row.get("source_cli") or "?"
    src_sess = (row.get("source_session_id") or "")[:8]
    src_cwd = row.get("source_cwd") or "?"
    src_cwd_short = src_cwd
    home = str(Path.home())
    if src_cwd_short.startswith(home):
        src_cwd_short = "~" + src_cwd_short[len(home):]
    badge = source_badge(src_cli)
    frm = f"{badge} {src_cli}:{src_sess} ({src_cwd_short})"
    brief = row.get("brief_path") or "-"
    if brief and brief != "-":
        brief_short = brief
        if brief_short.startswith(home):
            brief_short = "~" + brief_short[len(home):]
        brief = brief_short
    req = "yes" if row.get("require_ack") else "no"
    status = row.get("status") or "pending"
    return rid, age, frm, brief, req, status


def command_handoff(args: argparse.Namespace) -> int:
    source = args.source
    if not source:
        if os.environ.get("CLAUDE_CODE_SESSION_ID"):
            source = "claude"
        elif os.environ.get("CODEX_SESSION_ID"):
            source = "codex"
        else:
            raise SystemExit(
                "Cannot infer --source: no CLAUDE_CODE_SESSION_ID or CODEX_SESSION_ID env var set. Pass --source explicitly."
            )

    session_selector = args.session
    if not session_selector:
        env_id = current_session_id()
        if not env_id:
            raise SystemExit("--session not given and no current session id env var present.")
        session_selector = env_id

    session = find_session_or_die(source, session_selector)

    target_cli = args.target_cli or source
    target_cwd = args.target_cwd
    target_session_id = args.target_session

    if args.launch is None:
        launch = (target_cli != source) or bool(target_session_id)
    else:
        launch = args.launch

    workspace = Path(args.workspace or os.getcwd()).resolve()

    excerpts, tools = extract_session_material(session)
    material_state, material_detail = classify_material_state(session, excerpts)
    brief_path: Path | None = None
    if material_state in {"missing_transcript", "empty_transcript"}:
        # Skip brief generation if transcript is empty; still record the handoff with notes.
        brief_path = None
    else:
        notes = {
            "done": args.done,
            "pending": args.pending,
            "blocked": args.blocked,
        }
        brief_path = write_brief(
            workspace,
            session,
            args.question,
            excerpts,
            tools,
            limit=args.limit,
            notes=notes,
        )

    if args.dry_run:
        print("Plan:")
        print(f"  source         : {source}:{session.session_id}")
        print(f"  source_cwd     : {session.cwd or os.getcwd()}")
        print(f"  target_cli     : {target_cli}")
        print(f"  target_cwd     : {target_cwd or '(any)'}")
        print(f"  target_session : {target_session_id or '(any)'}")
        print(f"  brief_path     : {brief_path or '(none - transcript not ready)'}")
        print(f"  require_ack    : {args.require_ack}")
        print(f"  launch         : {launch}")
        return 0

    handoff_id = insert_handoff(
        source_cli=source,
        source_session_id=session.session_id,
        source_cwd=session.cwd or os.getcwd(),
        target_cli=target_cli,
        target_cwd=target_cwd,
        target_session_id=target_session_id,
        brief_path=str(brief_path) if brief_path else None,
        note_done=args.done,
        note_pending=args.pending,
        note_blocked=args.blocked,
        require_ack=args.require_ack,
    )

    launch_status = "skipped"
    if launch:
        if target_cli == source and brief_path is None:
            _, shell_cmd = shell_command_for_native_fork(session, args.question)
            open_in_terminal(shell_cmd, False)
            launch_status = "native fork"
        elif brief_path is not None:
            cwd = session.cwd or str(workspace)
            shell_cmd = shell_command_for_brief_launch(target_cli, cwd, brief_path, args.question)
            open_in_terminal(shell_cmd, False)
            launch_status = "brief launch"
        else:
            launch_status = "skipped (no brief, cross-CLI requires brief)"

    print(f"Handoff #{handoff_id} recorded.")
    print(f"  target_cli   : {target_cli}")
    print(f"  target_cwd   : {target_cwd or '(any)'}")
    print(f"  brief_path   : {brief_path or '(none)'}")
    print(f"  launch       : {launch_status}")
    print(f"  require_ack  : {args.require_ack}")
    return 0


def command_inbox(args: argparse.Namespace) -> int:
    target_cli = args.source
    if target_cli in (None, "all"):
        if target_cli is None:
            if os.environ.get("CLAUDE_CODE_SESSION_ID"):
                target_cli = "claude"
            elif os.environ.get("CODEX_SESSION_ID"):
                target_cli = "codex"
            else:
                target_cli = None
        else:
            target_cli = None

    cwd = str(Path(args.cwd or os.getcwd()).resolve())
    session_id = current_session_id()

    items = fetch_inbox(
        target_cli=target_cli,
        cwd=cwd,
        session_id=session_id,
        show_all=args.show_all,
        limit=args.limit,
    )

    if args.json:
        print(json.dumps(items, indent=2))
        return 0

    if not items:
        print("# Inbox: 0 pending handoff(s)")
        return 0

    print(f"# Inbox: {len(items)} pending handoff(s)")
    print()
    header = f"  {'ID':<4}{'AGE':<10}{'FROM':<48}{'BRIEF':<50}{'REQ_ACK':<9}{'STATUS':<8}"
    print(header)
    print(f"  {'-' * 2:<4}{'-' * 8:<10}{'-' * 46:<48}{'-' * 48:<50}{'-' * 7:<9}{'-' * 7:<8}")
    for row in items:
        rid, age, frm, brief, req, status = format_handoff_row(row)
        if len(frm) > 47:
            frm = frm[:44] + "..."
        if len(brief) > 49:
            brief = brief[:46] + "..."
        print(f"  {rid:<4}{age:<10}{frm:<48}{brief:<50}{req:<9}{status:<8}")
    return 0


def command_ack(args: argparse.Namespace) -> int:
    handoff_id = args.handoff_id
    row = fetch_handoff_by_id(handoff_id)
    if row is None:
        raise SystemExit(f"Handoff not found: #{handoff_id}")
    ack_session = current_session_id()
    ok = update_handoff_ack(handoff_id, ack_session, args.note)
    if not ok:
        raise SystemExit(f"Failed to update handoff #{handoff_id}.")
    src_cli = row.get("source_cli") or "?"
    src_sess = row.get("source_session_id") or "?"
    brief = row.get("brief_path") or "(none)"
    print(f"Acknowledged handoff #{handoff_id}. Source: {src_cli}:{src_sess}. Brief: {brief}.")
    return 0


def command_hook_session_start(args: argparse.Namespace) -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    session_id = str(payload.get("session_id") or "").strip()
    cwd = str(payload.get("cwd") or payload.get("working_dir") or "").strip()
    title = str(payload.get("title") or payload.get("session_title") or "").strip()

    if not session_id:
        print("{}")
        return 0

    session = find_session_record(args.source, session_id)
    effective_cwd = session.cwd if session and session.cwd else cwd
    effective_title = session.title if session and session.title else title
    code, created = ensure_session_alias(
        source=args.source,
        session_id=session_id,
        cwd=effective_cwd,
        title=effective_title,
        assigned_by="session-start-hook",
    )
    desired_title = format_native_title(code, effective_title)
    title_updated = False
    if desired_title != effective_title:
        try:
            update_native_title(args.source, session_id, desired_title)
            update_alias_registry_title(
                code=code,
                source=args.source,
                session_id=session_id,
                cwd=effective_cwd,
                title=desired_title,
                assigned_by="session-start-hook",
            )
            title_updated = True
        except Exception:
            title_updated = False
    if created:
        sys.stderr.write(f"session-absorb id: {code}\n")
    if title_updated:
        sys.stderr.write(f"session-absorb title: {desired_title}\n")
    print("{}")
    return 0


def command_install(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    codex_source = repo_root / "skills" / "codex" / "session-absorb"
    claude_source = repo_root / "skills" / "claude" / "session-absorb"
    claude_alias_source = repo_root / "skills" / "claude" / "absorb"
    results = install_runtime_copy(repo_root)
    results.extend(
        [
            install_skill_copy(codex_source, CODEX_HOME / "skills" / "session-absorb"),
            install_skill_copy(claude_source, CLAUDE_HOME / "skills" / "session-absorb"),
            install_codex_session_start_hook_registration(),
            install_claude_session_start_hook_registration(),
        ]
    )
    if claude_alias_source.exists():
        results.append(
            install_skill_copy(claude_alias_source, CLAUDE_HOME / "skills" / "absorb")
        )
    for alias_name in ("handoff", "inbox", "ack"):
        alias_source = repo_root / "skills" / "claude" / alias_name
        if alias_source.exists():
            results.append(
                install_skill_copy(alias_source, CLAUDE_HOME / "skills" / alias_name)
            )
    print("\n".join(results))
    print()
    print("--- Onboarding ---")
    print("Daily fast paths (run inside Claude Code with the bang prefix `!`):")
    print()
    print("  Add a shell alias for brevity (one time):")
    print("    echo 'alias sa=\"$HOME/.local/bin/session-absorb\"' >> ~/.zshrc && source ~/.zshrc")
    print()
    print("  Common invocations:")
    print("    !sa here                       # digest cwd-default sibling session")
    print("    !sa here ask --question \"...\"  # ask cwd-default session a question")
    print("    !sa here launch                # fork cwd-default session in new Terminal")
    print("    !sa last                       # digest most-recent session anywhere")
    print("    !sa fork-myself                # fork the CURRENT session into new Terminal")
    print("    !sa list --active-only         # list active sessions")
    print()
    print("  Slash commands available in Claude Code:")
    print("    /absorb       # click picker, default daily flow")
    print("    /handoff      # write a structured handoff (with --done / --pending / --blocked)")
    print("    /inbox        # see pending handoffs targeted at this session / cwd / CLI")
    print("    /ack <id>     # acknowledge a handoff so the source knows it landed")
    print()
    print("Full reference: see docs/reference.md or run `session-absorb --help`.")
    return 0


def command_web(args: argparse.Namespace) -> int:
    return serve_web_dashboard(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bridge Codex and Claude sessions with transcript extraction, session aliasing, question packs, and native fork launchers."
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    list_parser = subparsers.add_parser("list", help="List recent Codex and Claude sessions.")
    list_parser.add_argument("--source", choices=["all", "codex", "claude"], default="all")
    list_parser.add_argument("--query")
    list_parser.add_argument("--cwd")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.add_argument("--json", action="store_true")
    list_parser.add_argument("--plain", action="store_true")
    list_parser.add_argument("--interactive", action="store_true")
    list_parser.add_argument("--chat-menu", action="store_true")
    list_parser.add_argument("--open-terminal", action="store_true")
    list_parser.add_argument("--dry-run", action="store_true")
    list_parser.add_argument("--active-only", action="store_true")
    list_parser.add_argument(
        "--select-only",
        action="store_true",
        help="In interactive mode, print the selection and exit instead of opening the action menu.",
    )
    list_parser.set_defaults(func=command_list)

    pick_parser = subparsers.add_parser(
        "pick",
        help="Select one item from the latest chat-menu snapshot, or an explicit snapshot id.",
    )
    pick_parser.add_argument("selection")
    pick_parser.add_argument("--snapshot")
    pick_parser.set_defaults(func=command_pick)

    here_parser = subparsers.add_parser(
        "here",
        help="Run an action on the most recent non-self session in the current cwd. Defaults to digest.",
    )
    here_parser.add_argument(
        "action", nargs="?", default="digest",
        choices=["digest", "ask", "brief", "launch", "show"],
    )
    here_parser.add_argument("--question")
    here_parser.set_defaults(func=command_here)

    last_parser = subparsers.add_parser(
        "last",
        help="Run an action on the most recent non-self session anywhere. Defaults to digest.",
    )
    last_parser.add_argument(
        "action", nargs="?", default="digest",
        choices=["digest", "ask", "brief", "launch", "show"],
    )
    last_parser.add_argument("--question")
    last_parser.set_defaults(func=command_last)

    fork_self_parser = subparsers.add_parser(
        "fork-myself",
        help="Fork the CURRENT active session into a new Terminal window. Reads CLAUDE_CODE_SESSION_ID or CODEX_SESSION_ID.",
    )
    fork_self_parser.add_argument("--question", help="Optional initial prompt for the forked session.")
    fork_self_parser.add_argument("--dry-run", action="store_true", help="Print the shell command without executing.")
    fork_self_parser.set_defaults(func=command_fork_myself)

    init_parser = subparsers.add_parser(
        "init",
        help="Assign a short code to a session and prefix the native title for easy targeting.",
    )
    init_parser.add_argument("--source", choices=["codex", "claude"])
    init_parser.add_argument("--session")
    init_parser.add_argument("--code")
    init_parser.add_argument("--title")
    init_parser.add_argument("--query")
    init_parser.add_argument("--cwd")
    init_parser.add_argument("--limit", type=int, default=10)
    init_parser.add_argument("query_terms", nargs="*")
    init_parser.set_defaults(func=command_init)

    digest_parser = subparsers.add_parser("digest", help="Render a compact digest for one session.")
    digest_parser.add_argument("--source", choices=["codex", "claude"], required=True)
    digest_parser.add_argument("--session", required=True)
    digest_parser.set_defaults(func=command_digest)

    brief_parser = subparsers.add_parser("brief", help="Write a bridge brief for another session.")
    brief_parser.add_argument("--source", choices=["codex", "claude"], required=True)
    brief_parser.add_argument("--session", required=True)
    brief_parser.add_argument("--question")
    brief_parser.add_argument("--limit", type=int, default=8)
    brief_parser.add_argument("--workspace")
    brief_parser.set_defaults(func=command_brief)

    ask_parser = subparsers.add_parser("ask", help="Ask a targeted question about a session.")
    ask_parser.add_argument("--source", choices=["codex", "claude"], required=True)
    ask_parser.add_argument("--session", required=True)
    ask_parser.add_argument("--question", required=True)
    ask_parser.add_argument("--limit", type=int, default=6)
    ask_parser.add_argument("--live", choices=["auto", "always", "never"], default="auto")
    ask_parser.set_defaults(func=command_ask)

    launch_parser = subparsers.add_parser("launch", help="Launch a native fork or brief-driven bridge session in Terminal.")
    launch_parser.add_argument("--source", choices=["codex", "claude"], required=True)
    launch_parser.add_argument("--session", required=True)
    launch_parser.add_argument("--question")
    launch_parser.add_argument("--target", choices=["codex", "claude"])
    launch_parser.add_argument("--mode", choices=["auto", "native", "brief"], default="auto")
    launch_parser.add_argument("--workspace")
    launch_parser.add_argument("--limit", type=int, default=8)
    launch_parser.add_argument("--dry-run", action="store_true")
    launch_parser.set_defaults(func=command_launch)

    handoff_parser = subparsers.add_parser(
        "handoff",
        help="Record a structured handoff with optional brief and launch.",
    )
    handoff_parser.add_argument("--source", choices=["codex", "claude"])
    handoff_parser.add_argument("--session")
    handoff_parser.add_argument("--target-cli", choices=["codex", "claude"])
    handoff_parser.add_argument("--target-cwd")
    handoff_parser.add_argument("--target-session")
    handoff_parser.add_argument("--done")
    handoff_parser.add_argument("--pending")
    handoff_parser.add_argument("--blocked")
    handoff_parser.add_argument(
        "--launch",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Force launch on/off. Defaults to True when target differs from source or target-session is set.",
    )
    handoff_parser.add_argument("--require-ack", action="store_true")
    handoff_parser.add_argument("--question")
    handoff_parser.add_argument("--workspace")
    handoff_parser.add_argument("--limit", type=int, default=8)
    handoff_parser.add_argument("--dry-run", action="store_true")
    handoff_parser.set_defaults(func=command_handoff)

    inbox_parser = subparsers.add_parser(
        "inbox",
        help="Show pending handoffs targeted at the current CLI / cwd / session.",
    )
    inbox_parser.add_argument("--source", choices=["codex", "claude", "all"])
    inbox_parser.add_argument("--cwd")
    inbox_parser.add_argument("--show-all", action="store_true")
    inbox_parser.add_argument("--json", action="store_true")
    inbox_parser.add_argument("--limit", type=int, default=20)
    inbox_parser.set_defaults(func=command_inbox)

    ack_parser = subparsers.add_parser(
        "ack",
        help="Acknowledge a pending handoff by id.",
    )
    ack_parser.add_argument("handoff_id", type=int)
    ack_parser.add_argument("--note")
    ack_parser.set_defaults(func=command_ack)

    web_parser = subparsers.add_parser(
        "web",
        help="Serve a live local web dashboard for session state, aliases, and project activity.",
    )
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=DEFAULT_WEB_PORT)
    web_parser.add_argument("--limit", type=int, default=DEFAULT_WEB_LIMIT)
    web_parser.add_argument("--interval", type=int, default=DEFAULT_WEB_STREAM_INTERVAL_SECONDS)
    web_parser.add_argument("--open-browser", action="store_true")
    web_parser.add_argument("--quiet", action="store_true")
    web_parser.set_defaults(func=command_web)

    install_parser = subparsers.add_parser(
        "install",
        help="Install the runtime and skill wrappers into ~/.local, ~/.codex, and ~/.claude.",
    )
    install_parser.add_argument("--repo-root", required=True)
    install_parser.add_argument("--force", action="store_true")
    install_parser.set_defaults(func=command_install)

    hook_parser = subparsers.add_parser(
        "hook-session-start",
        help=argparse.SUPPRESS,
    )
    hook_parser.add_argument("--source", choices=["codex", "claude"], required=True)
    hook_parser.set_defaults(func=command_hook_session_start)

    db_parser = subparsers.add_parser(
        "db",
        help="Inspect the SQLite session catalog used for active-state tracking and discovery.",
    )
    db_parser.add_argument("--limit", type=int, default=20)
    db_parser.add_argument("--json", action="store_true")
    db_parser.set_defaults(func=command_db)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        is_tty = can_render_interactive_menu()
        defaults = argparse.Namespace(
            source="all",
            query=None,
            cwd=None,
            limit=20,
            json=False,
            plain=False,
            interactive=is_tty,
            chat_menu=not is_tty,
            open_terminal=False,
            dry_run=False,
            active_only=False,
            select_only=False,
        )
        return command_list(defaults)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
