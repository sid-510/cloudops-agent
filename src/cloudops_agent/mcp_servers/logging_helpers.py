"""Pure helper functions for the logging MCP server.

Nothing in this file talks to Google Cloud, so it can be tested
quickly and without credentials.
"""

from datetime import datetime, timedelta
from typing import Any
from collections import Counter

MAX_MINUTES = 10080 # 7 days
MAX_RESULTS = 100
MAX_TOP_N = 50      # most distinct messages top_errors will return
MAX_SCAN = 1000     # most raw entries top_errors will fetch and count

def clamp(value: int, low: int, high: int) -> int:
    """Returen value limited to the range [low, high]."""
    return max(low, min(value, high))

def build_error_filter(minutes: int, now: datetime) -> str:
    """Build a Cloud Logging filter for ERROR-or-worse entries in the last N minutes."""
    since = now - timedelta(minutes=minutes)
    return f'severity>=ERROR AND timestamp>="{since.isoformat()}"'


def entry_to_dict(entry: Any) -> dict:
    """Convert a Cloud Logging entry into a plain dict an MCP client can read."""
    payload = entry.payload
    if not isinstance(payload, (str, dict)):
        payload = str(payload)

    return {
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        "severity": entry.severity,
        "log_name": entry.log_name,
        "message": payload,
        "insert_id": entry.insert_id,
        "resource_type": entry.resource.type if entry.resource else None,
        "resource_labels": dict(entry.resource.labels) if entry.resource else {},
    }

def clean_search_text(text: str) -> str:
    """Remove characters that could break out of a quoted filter value.

    Also trims spaces from the start and end.
    """
    return text.replace('"', "").replace("\\", "").strip()


def build_text_search_filter(text: str, minutes: int, now: datetime) -> str:
    """Build a filter for entries mentioning `text` in the last N minutes."""
    since = now - timedelta(minutes=minutes)
    safe_text = clean_search_text(text)
    return f'"{safe_text}" AND timestamp>="{since.isoformat()}"'

def summarize_errors(entries: list[dict], top_n: int) -> list[dict]:
    """Group entries by message and return the most common ones.

    `entries` must be newest first (as returned by Cloud Logging with
    DESCENDING order), so the first entry seen for each message is the latest.
    """
    counts = Counter()
    latest = {}

    for entry in entries:
        message = str(entry["message"])
        counts[message] += 1
        if message not in latest:
            latest[message] = entry

    summary = []
    for message, count in counts.most_common(top_n):
        summary.append(
            {
                "message": message,
                "count": count,
                "latest_timestamp": latest[message]["timestamp"],
                "latest_insert_id": latest[message]["insert_id"],
            }
        )
    return summary