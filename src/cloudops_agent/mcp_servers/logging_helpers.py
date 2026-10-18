"""Pure helper functions for the logging MCP server.

Nothing in this file talks to Google Cloud, so it can be tested
quickly and without credentials.
"""

from datetime import datetime, timedelta
from typing import Any

MAX_MINUTES = 10080 # 7 days
MAX_RESULTS = 100

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
    }