"""Replay the logging tools against a recorded incident snapshot (no Google Cloud calls)."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from cloudops_agent.mcp_servers.logging_helpers import (
    MAX_MINUTES,
    MAX_RESULTS,
    MAX_SCAN,
    MAX_TOP_N,
    clamp,
    clean_search_text,
    summarize_errors,
    is_run_change,
    summarize_change,
)

SEVERITY_RANK = {
    "DEFAULT": 0, "DEBUG": 100, "INFO": 200, "NOTICE": 300, "WARNING": 400,
    "ERROR": 500, "CRITICAL": 600, "ALERT": 700, "EMERGENCY": 800,
}


def load_snapshot(incident_dir) -> dict:
    """Read incidents/<id>/logs.json."""
    return json.loads((Path(incident_dir) / "logs.json").read_text())


def in_window(entries: list[dict], minutes: int, now: datetime) -> list[dict]:
    """Entries from the last N minutes before `now`, newest first. Never anything after `now`."""
    since = now - timedelta(minutes=minutes)
    selected = [
        e for e in entries
        if e["timestamp"] and since <= datetime.fromisoformat(e["timestamp"]) <= now
    ]
    return sorted(selected, key=lambda e: e["timestamp"], reverse=True)


def is_error(entry: dict) -> bool:
    return SEVERITY_RANK.get(str(entry["severity"]), 0) >= SEVERITY_RANK["ERROR"]


def replay_get_recent_errors(entries, now, minutes=60, max_results=20) -> list[dict]:
    minutes = clamp(minutes, 1, MAX_MINUTES)
    max_results = clamp(max_results, 1, MAX_RESULTS)
    return [e for e in in_window(entries, minutes, now) if is_error(e)][:max_results]


def replay_search_logs_by_text(entries, now, text, minutes=60, max_results=20) -> list[dict]:
    needle = clean_search_text(text).lower()
    if not needle:
        raise ValueError("text must contain at least one searchable character")
    minutes = clamp(minutes, 1, MAX_MINUTES)
    max_results = clamp(max_results, 1, MAX_RESULTS)
    matches = [
        e for e in in_window(entries, minutes, now)
        if needle in json.dumps(e, default=str).lower()
    ]
    return matches[:max_results]


def replay_top_errors(entries, now, minutes=60, top_n=10) -> dict:
    minutes = clamp(minutes, 1, MAX_MINUTES)
    top_n = clamp(top_n, 1, MAX_TOP_N)
    errors = [e for e in in_window(entries, minutes, now) if is_error(e)][:MAX_SCAN]
    return {
        "scanned": len(errors),
        "truncated": len(errors) == MAX_SCAN,
        "top_errors": summarize_errors(errors, top_n),
    }

def replay_get_recent_changes(entries, now, minutes=120, max_results=20) -> list[dict]:
    minutes = clamp(minutes, 1, MAX_MINUTES)
    max_results = clamp(max_results, 1, MAX_RESULTS)
    changes = [summarize_change(e) for e in in_window(entries, minutes, now) if is_run_change(e)]
    return changes[:max_results]