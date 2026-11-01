"""CloudOps diagnosis agent: Gemini + the logging tools, run against a recorded incident.

Usage: uv run python -m cloudops_agent.agent incidents/inc-001
"""

import json
import os
import re
import sys
from datetime import datetime
from typing import Literal

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, Field

from cloudops_agent.replay import (
    load_snapshot,
    replay_get_recent_changes,
    replay_get_recent_errors,
    replay_search_logs_by_text,
    replay_top_errors,
)

MODEL = os.environ.get("AGENT_MODEL", "gemini-3.7-flash")
MAX_STEPS = 25  # hard cap on reasoning/tool steps per diagnosis

SYSTEM_PROMPT = """You help an on-call engineer investigate a production incident in a \
Google Cloud project that runs services on Cloud Run.

The current time is {now} UTC. The tools can see logs and changes up to this moment only.

How to work:
- Start broad (what is failing, since when), then narrow down (which revision, which change).
- Check whether the problem started right after a deployment or configuration change.
- Base every claim on tool results. Cite the insert_id of each log entry or change you rely on.
  Never invent insert_ids.
- If the tools do not show enough evidence to establish the root cause, use the category
  "cannot_establish". An honest "cannot establish" is better than a confident guess."""


class Diagnosis(BaseModel):
    """The agent's final answer."""

    root_cause_category: Literal[
        "bad_config_deploy",
        "bad_code_deploy",
        "dependency_failure",
        "resource_exhaustion",
        "traffic_spike",
        "other",
        "cannot_establish",
    ]
    root_cause: str = Field(description="One or two sentences: the root cause, or why it cannot be established.")
    affected_revision: str | None = Field(description="The Cloud Run revision the problem is tied to, if any.")
    evidence_insert_ids: list[str] = Field(description="insert_ids of the entries and changes that support the conclusion.")
    confidence: Literal["high", "medium", "low"]


def as_json(data) -> str:
    return json.dumps(data, default=str)


def build_replay_tools(entries: list[dict], now: datetime) -> list:
    """Wrap the replay functions as tools the model can call. Descriptions mirror the MCP tools."""

    @tool
    def get_recent_errors(minutes: int = 60, max_results: int = 20) -> str:
        """Return recent log entries with severity ERROR or worse, newest first.

        Args:
            minutes: How far back to look, in minutes (1 to 10080, i.e. 7 days).
            max_results: Maximum number of entries to return (1 to 100).
        """
        return as_json(replay_get_recent_errors(entries, now, minutes, max_results))

    @tool
    def search_logs_by_text(text: str, minutes: int = 60, max_results: int = 20) -> str:
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
        try:
            return as_json(replay_search_logs_by_text(entries, now, text, minutes, max_results))
        except ValueError as exc:
            return as_json({"error": str(exc)})

    @tool
    def top_errors(minutes: int = 60, top_n: int = 10) -> str:
        """Return the most frequent ERROR-or-worse messages in the last N minutes, with counts.

        Use this first during an incident to see what is failing most often.
        Each result includes the latest timestamp and insert_id as evidence.
        If "truncated" is true, the counts cover only the most recent 1000 errors.

        Args:
            minutes: How far back to look, in minutes (1 to 10080, i.e. 7 days).
            top_n: How many distinct error messages to return (1 to 50).
        """
        return as_json(replay_top_errors(entries, now, minutes, top_n))

    @tool
    def get_recent_changes(minutes: int = 120, max_results: int = 20) -> str:
        """Return recent deployments and configuration changes to Cloud Run services, newest first.

        Use this to check whether an incident started right after a deploy or config change.
        Each entry shows the service, the revision (if one was created), the container image
        and the environment variables of the resulting configuration (secret-looking values
        are masked), with the audit log insert_id as evidence.
        The env shown is the full configuration, not a diff: compare a revision with the
        previous one to see what changed. The same image digest in two revisions means the
        code did not change.

        Args:
            minutes: How far back to look, in minutes (1 to 10080, i.e. 7 days).
            max_results: Maximum number of entries to return (1 to 100).
        """
        return as_json(replay_get_recent_changes(entries, now, minutes, max_results))

    return [get_recent_errors, search_logs_by_text, top_errors, get_recent_changes]


INSERT_ID = re.compile(r'"(?:latest_)?insert_id": "([^"]+)"')


def diagnose(question: str, entries: list[dict], now: datetime) -> dict:
    """Run the agent once and return its diagnosis plus a trace for scoring."""
    llm = ChatGoogleGenerativeAI(
        model=MODEL,
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location="global",
        temperature=0,
    )
    agent = create_agent(
        llm,
        tools=build_replay_tools(entries, now),
        system_prompt=SYSTEM_PROMPT.format(now=now.isoformat()),
        response_format=Diagnosis,
    )

    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
            config={"recursion_limit": MAX_STEPS},
        )
    except GraphRecursionError:
        return {"model": MODEL, "diagnosis": None, "error": f"step limit ({MAX_STEPS}) reached"}

    messages = result["messages"]
    tool_calls = [
        {"name": call["name"], "args": call["args"]}
        for m in messages if isinstance(m, AIMessage)
        for call in m.tool_calls
        if call["name"] != "Diagnosis"  # the final-answer step, not an investigation
    ]
    returned_ids = sorted({
        found
        for m in messages if isinstance(m, ToolMessage)
        for found in INSERT_ID.findall(str(m.content))
    })
    tokens = sum(
        (m.usage_metadata or {}).get("total_tokens", 0)
        for m in messages if isinstance(m, AIMessage)
    )

    return {
        "model": MODEL,
        "diagnosis": result["structured_response"].model_dump(),
        "tool_calls": tool_calls,
        "returned_insert_ids": returned_ids,
        "total_tokens": tokens,
    }


def main() -> None:
    incident_dir = sys.argv[1]
    label = json.loads(open(f"{incident_dir}/label.json").read())
    snapshot = load_snapshot(incident_dir)
    now = datetime.fromisoformat(label["asked_at"])

    run = diagnose(label["question"], snapshot["entries"], now)
    print(json.dumps(run, indent=2))


if __name__ == "__main__":
    main()
