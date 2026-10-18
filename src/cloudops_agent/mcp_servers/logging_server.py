"""MCP server exposing Google Cloud Logging tools"""

import os
from datetime import datetime, timedelta, timezone

from google.cloud import logging as cloud_logging
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from cloudops_agent.mcp_servers.logging_helpers import (
    MAX_MINUTES,
    MAX_RESULTS,
    MAX_SCAN,
    MAX_TOP_N,
    build_error_filter,
    build_text_search_filter,
    clamp,
    clean_search_text,
    entry_to_dict,
    summarize_errors,
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

@mcp.tool()
def top_errors(minutes: int = 60, top_n: int = 10) -> dict:
    """Return the most frequent ERROR-or-worse messages in the last N minutes, with counts.

    Use this first during an incident to see what is failing most often.
    Each result includes the latest timestamp and insert_id as evidence.
    Up to 1000 recent errors are scanned. If "truncated" is true, the
    counts cover only the most recent 1000 entries, not the whole window.

    Args:
        minutes: How far back to look, in minutes (1 to 10080, i.e. 7 days).
        top_n: How many distinct error messages to return (1 to 50).
    """
    minutes = clamp(minutes, 1, MAX_MINUTES)
    top_n = clamp(top_n, 1, MAX_TOP_N)
    log_filter = build_error_filter(minutes, now=datetime.now(timezone.utc))

    entries = client.list_entries(
        filter_=log_filter,
        order_by=cloud_logging.DESCENDING,
        max_results=MAX_SCAN,
    )
    tidy_entries = [entry_to_dict(entry) for entry in entries]

    return {
        "scanned": len(tidy_entries),
        "truncated": len(tidy_entries) == MAX_SCAN,
        "top_errors": summarize_errors(tidy_entries, top_n),
    }

if __name__ == "__main__":
    mcp.run()