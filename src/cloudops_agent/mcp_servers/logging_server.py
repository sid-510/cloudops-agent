"""MCP server exposing Google Cloud Logging tools"""

import os
from datetime import datetime, timedelta, timezone

from google.cloud import logging as cloud_logging
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from cloudops_agent.mcp_servers.logging_helpers import (
    MAX_MINUTES,
    MAX_RESULTS,
    build_error_filter,
    build_text_search_filter,
    clamp,
    clean_search_text,
    entry_to_dict,
)

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
    minutes = clamp(minutes, 1, MAX_MINUTES)
    max_results = clamp(max_results, 1, MAX_RESULTS)
    log_filter = build_error_filter(minutes, now=datetime.now(timezone.utc))

    entries = client.list_entries(
        filter_ = log_filter,
        order_by = cloud_logging.DESCENDING,
        max_results = max_results,
    )
    return [entry_to_dict(entry) for entry in entries]

@mcp.tool()
def search_logs_by_text(text: str, minutes: int = 60, max_results: int = 20) -> list[dict]:
    """Search recent log entries of any severity that mention the given text.

    Use this to find logs about a specific symptom, such as "timeout",
    "connection refused" or a service name. Matching ignores upper/lower case
    but is literal: "timeout" does not match "timed out". If a search finds
    nothing, try related wording before concluding there are no matches.
    
    Args:
        text: Word or phrase to search for. Quote marks are removed.
        minutes: How far back to look, in minutes (1 to 10080, i.e. 7 days).
        max_results: Maximum number of entries to return (1 to 100).
    """
    if not clean_search_text(text):
        raise ToolError("text must contain at least one searchable character")

    minutes = clamp(minutes, 1, MAX_MINUTES)
    max_results = clamp(max_results, 1, MAX_RESULTS)
    log_filter = build_text_search_filter(text, minutes, now=datetime.now(timezone.utc))

    entries = client.list_entries(
        filter_=log_filter,
        order_by=cloud_logging.DESCENDING,
        max_results=max_results,
    )
    return [entry_to_dict(entry) for entry in entries]

if __name__ == "__main__":
    mcp.run()