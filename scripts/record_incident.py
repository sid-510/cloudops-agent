"""Save every log entry around an incident into incidents/<id>/logs.json.

Usage: uv run python scripts/record_incident.py incidents/inc-001
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

from google.api_core.exceptions import ResourceExhausted

from google.cloud import logging as cloud_logging

from cloudops_agent.mcp_servers.logging_helpers import entry_to_dict

MARGIN = timedelta(minutes=30)  # extra context before and after the incident
MAX_ENTRIES = 5000

PAGE_SIZE = 1000  # fewer, larger pages = fewer API requests
RETRIES = 3


def fetch_entries(client, log_filter: str) -> list[dict]:
    """Fetch entries, waiting and retrying if Cloud Logging rate-limits us."""
    for attempt in range(1, RETRIES + 1):
        try:
            return [
                entry_to_dict(e)
                for e in client.list_entries(
                    filter_=log_filter,
                    order_by=cloud_logging.DESCENDING,
                    max_results=MAX_ENTRIES,
                    page_size=PAGE_SIZE,
                )
            ]
        except ResourceExhausted:
            if attempt == RETRIES:
                raise
            print(f"rate limited, waiting 60s (attempt {attempt}/{RETRIES})")
            time.sleep(60)

def main() -> None:
    incident_dir = Path(sys.argv[1])
    label = json.loads((incident_dir / "label.json").read_text())

    start = datetime.fromisoformat(label["window_start"]) - MARGIN
    end = datetime.fromisoformat(label["window_end"]) + MARGIN
    log_filter = f'timestamp>="{start.isoformat()}" AND timestamp<="{end.isoformat()}"'

    snapshot = {
        "incident_id": label["id"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "query": {"filter": log_filter, "start": start.isoformat(), "end": end.isoformat()},
    }

    client = cloud_logging.Client(project=os.environ["GOOGLE_CLOUD_PROJECT"])
    try:
        entries = fetch_entries(client, log_filter)
        snapshot.update(
            status="ok",
            entry_count=len(entries),
            truncated=len(entries) == MAX_ENTRIES,
            entries=entries,
        )
    except Exception as exc:
        snapshot.update(status="query_failed", error=str(exc), entries=[])

    out = incident_dir / "logs.json"
    out.write_text(json.dumps(snapshot, indent=2, default=str))
    print(f"{snapshot['status']}: {len(snapshot['entries'])} entries -> {out}")
    if snapshot["status"] == "query_failed":
        print(f"error: {snapshot['error']}")


if __name__ == "__main__":
    main()