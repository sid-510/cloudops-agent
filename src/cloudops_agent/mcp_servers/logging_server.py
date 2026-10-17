"""MCP server exposing Google Cloud Logging tools"""

import os
from datetime import datetime, timedelta, timezone

from google.cloud import logging as cloud_logging
from mcp.server.mcpserver import MCPServer

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]

mcp = MCPServer("cloudops-logging")
client = cloud_logging.Client(project=PROJECT_ID)

@mcp.tool()
def get_recent_errors(minutes: int = 60, max_results: int = 20) -> list[dict]:
    """Return recent log entries with severity ERROR or worse, newest first.
    
    Args:
        minutes: How far back to look, in minutes (1 to 10080, i.e. 7 days).
        max_results: Maximum number of entries to return (1 to 100).
    """
    minutes = max(1, min(minutes, 10080))
    max_results = max(1, min(max_results, 100))

    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    log_filter = f'severity>=ERROR AND timestamp>="{since.isoformat()}"'

    entries = client.list_entries(
        filter_ = log_filter,
        order_by = cloud_logging.DESCENDING,
        max_results = max_results,
    )

    results = []
    for entry in entries:
        payload = entry.payload
        if not isinstance(payload, (str, dict)):
            payload = str(payload)

        results.append(
            {
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "severity": entry.severity,
                "log_name": entry.log_name,
                "message": payload,
                "insert_id": entry.insert_id,
                "resource_type": entry.resource.type if entry.resource else None, 
            }
        )
    return results

if __name__ == "__main__":
    mcp.run()