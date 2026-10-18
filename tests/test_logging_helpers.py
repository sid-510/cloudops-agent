"""Tests for the pure helper functions in logging_helpers."""

from datetime import datetime, timezone
from types import SimpleNamespace

from cloudops_agent.mcp_servers.logging_helpers import (
    build_error_filter,
    clamp,
    entry_to_dict,
)


# ---------- clamp ----------

def test_clamp_keeps_value_inside_range():
    assert clamp(50, 1, 100) == 50


def test_clamp_raises_value_below_range():
    assert clamp(-5, 1, 100) == 1


def test_clamp_lowers_value_above_range():
    assert clamp(999999, 1, 100) == 100


# ---------- build_error_filter ----------

def test_build_error_filter_uses_correct_time_window():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    result = build_error_filter(minutes=30, now=now)

    assert result == 'severity>=ERROR AND timestamp>="2026-01-01T11:30:00+00:00"'


# ---------- entry_to_dict ----------

def test_entry_to_dict_with_text_payload():
    fake_entry = SimpleNamespace(
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        severity="ERROR",
        log_name="projects/demo/logs/app",
        payload="Database connection timed out",
        insert_id="abc123",
        resource=SimpleNamespace(type="cloud_run_revision"),
    )

    result = entry_to_dict(fake_entry)

    assert result == {
        "timestamp": "2026-01-01T12:00:00+00:00",
        "severity": "ERROR",
        "log_name": "projects/demo/logs/app",
        "message": "Database connection timed out",
        "insert_id": "abc123",
        "resource_type": "cloud_run_revision",
    }


def test_entry_to_dict_keeps_json_payload_and_handles_missing_fields():
    fake_entry = SimpleNamespace(
        timestamp=None,
        severity="ERROR",
        log_name="projects/demo/logs/app",
        payload={"error": "timeout", "latency_ms": 5200},
        insert_id="xyz789",
        resource=None,
    )

    result = entry_to_dict(fake_entry)

    assert result["message"] == {"error": "timeout", "latency_ms": 5200}
    assert result["timestamp"] is None
    assert result["resource_type"] is None