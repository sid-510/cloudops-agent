"""Tests for the pure helper functions in logging_helpers."""

from datetime import datetime, timezone
from types import SimpleNamespace

from cloudops_agent.mcp_servers.logging_helpers import (
    build_error_filter,
    build_text_search_filter,
    clamp,
    clean_search_text,
    entry_to_dict,
    summarize_errors,
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

# ---------- additional_clamp_test_for_at_limit_case ----------

def test_clamp_exactly_at_the_limit():
    assert clamp(100, 1, 100) == 100

# ---------- clean_search_text ----------

def test_clean_search_text_leaves_normal_text_alone():
    assert clean_search_text("timeout") == "timeout"


def test_clean_search_text_removes_quotes():
    assert clean_search_text('timeout" OR severity>="DEBUG') == "timeout OR severity>=DEBUG"


def test_clean_search_text_trims_spaces():
    assert clean_search_text("   database   ") == "database"


# ---------- build_text_search_filter ----------

def test_build_text_search_filter_uses_text_and_time_window():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    result = build_text_search_filter("timeout", minutes=60, now=now)

    assert result == '"timeout" AND timestamp>="2026-01-01T11:00:00+00:00"'

# ---------- summarize_errors ----------

def make_entry(message, insert_id, timestamp="2026-01-01T12:00:00+00:00"):
    """Build a tidy entry dict for tests (like entry_to_dict's output)."""
    return {
        "timestamp": timestamp,
        "severity": "ERROR",
        "log_name": "projects/demo/logs/app",
        "message": message,
        "insert_id": insert_id,
        "resource_type": "cloud_run_revision",
    }


def test_summarize_errors_counts_and_orders_by_frequency():
    entries = [
        make_entry("timeout", "a"),
        make_entry("db error", "b"),
        make_entry("timeout", "c"),
        make_entry("timeout", "d"),
    ]

    result = summarize_errors(entries, top_n=10)

    assert [r["message"] for r in result] == ["timeout", "db error"]
    assert [r["count"] for r in result] == [3, 1]


def test_summarize_errors_keeps_the_latest_entry_as_evidence():
    entries = [
        make_entry("timeout", "newest", timestamp="2026-01-01T12:00:00+00:00"),
        make_entry("timeout", "older", timestamp="2026-01-01T11:00:00+00:00"),
    ]

    result = summarize_errors(entries, top_n=10)

    assert result[0]["latest_insert_id"] == "newest"
    assert result[0]["latest_timestamp"] == "2026-01-01T12:00:00+00:00"


def test_summarize_errors_respects_top_n():
    entries = [make_entry("a", "1"), make_entry("b", "2"), make_entry("c", "3")]

    result = summarize_errors(entries, top_n=2)

    assert len(result) == 2


def test_summarize_errors_with_no_entries_returns_empty_list():
    assert summarize_errors([], top_n=5) == []