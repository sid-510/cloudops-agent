"""Baseline for comparison: one prompt with recent log lines pasted in, no tools.

It sees the same snapshot and the same cut-off time as the agent, and answers in the
same Diagnosis format. The only thing missing is the ability to investigate.
"""

import json
import os
from datetime import datetime

from langchain_google_genai import ChatGoogleGenerativeAI

from cloudops_agent.agent import MODEL, Diagnosis
from cloudops_agent.mcp_servers.logging_helpers import is_run_change, summarize_change
from cloudops_agent.replay import in_window

WINDOW_MINUTES = 60   # how far back the pasted logs go
MAX_LINES = 200       # how many log lines fit in the prompt
MESSAGE_CHARS = 300   # long messages are cut to this length

BASELINE_PROMPT = """You help an on-call engineer investigate a production incident in a \
Google Cloud project that runs services on Cloud Run.

The current time is {now} UTC. Below are the most recent log entries (newest first);
you have no other information. Each line shows: timestamp, severity, log name,
Cloud Run revision, insert_id, message.

- Base every claim on these log lines. Cite the insert_id of each line you rely on.
  Never invent insert_ids.
- If the lines do not show enough evidence to establish the root cause, use the category
  "cannot_establish". An honest "cannot establish" is better than a confident guess."""


def format_entry(entry: dict) -> str:
    """One compact text line per log entry. Cloud Run changes use the same summary as the agent's tool."""
    if is_run_change(entry):
        message = json.dumps(summarize_change(entry), default=str)
    elif isinstance(entry["message"], str):
        message = entry["message"]
    else:
        message = json.dumps(entry["message"], default=str)

    log = entry["log_name"].split("/logs/")[-1]
    revision = (entry.get("resource_labels") or {}).get("revision_name") or "-"
    return (
        f"{entry['timestamp']} {entry['severity']} [{log}] rev={revision} "
        f"id={entry['insert_id']} {message[:MESSAGE_CHARS]}"
    )


def select_lines(entries: list[dict], now: datetime) -> tuple[list[str], list[str]]:
    """The most recent entries before `now`, as text lines, plus the insert_ids shown."""
    recent = in_window(entries, WINDOW_MINUTES, now)[:MAX_LINES]
    return [format_entry(e) for e in recent], [e["insert_id"] for e in recent]


def baseline_diagnose(question: str, entries: list[dict], now: datetime) -> dict:
    """Answer in a single model call, with the log lines pasted into the prompt."""
    lines, shown_ids = select_lines(entries, now)
    llm = ChatGoogleGenerativeAI(
        model=MODEL,
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location="global",
        temperature=0,
    ).with_structured_output(Diagnosis, include_raw=True)

    result = llm.invoke([
        {"role": "system", "content": BASELINE_PROMPT.format(now=now.isoformat())},
        {"role": "user", "content": question + "\n\nLog entries:\n" + "\n".join(lines)},
    ])

    parsed = result["parsed"]
    usage = getattr(result["raw"], "usage_metadata", None) or {}
    return {
        "model": MODEL,
        "approach": "baseline",
        "diagnosis": parsed.model_dump() if parsed else None,
        "tool_calls": [],
        "returned_insert_ids": sorted(set(shown_ids)),
        "lines_in_prompt": len(lines),
        "total_tokens": usage.get("total_tokens", 0),
    }
