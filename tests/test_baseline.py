"""Tests for the baseline's log-line selection and formatting."""

from datetime import datetime, timezone

from cloudops_agent.baseline import MESSAGE_CHARS, format_entry, select_lines

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def entry(time, insert_id, message="Payment provider request timed out", log="run.googleapis.com%2Fstdout"):
    return {
        "timestamp": f"2026-01-01T{time}+00:00",
        "severity": "ERROR",
        "log_name": f"projects/demo/logs/{log}",
        "insert_id": insert_id,
        "resource_labels": {"revision_name": "shop-00005"},
        "message": message,
    }


def test_format_entry_shows_id_revision_and_message():
    line = format_entry(entry("11:50:00", "a1"))

    assert "id=a1" in line
    assert "rev=shop-00005" in line
    assert "Payment provider request timed out" in line


def test_format_entry_cuts_long_messages():
    line = format_entry(entry("11:50:00", "a1", message="x" * 5000))

    assert line.count("x") == MESSAGE_CHARS


def test_format_entry_summarises_cloud_run_changes():
    change = entry("11:41:00", "c1", log="cloudaudit.googleapis.com%2Fsystem_event", message={
        "serviceName": "run.googleapis.com",
        "methodName": "/Services.ReplaceService",
        "authenticationInfo": {"principalEmail": "someone@example.com"},
        "response": {"spec": {"containers": [{"env": [{"name": "PAYMENT_TIMEOUT_MS", "value": "150"}]}]}},
    })

    line = format_entry(change)

    assert '"PAYMENT_TIMEOUT_MS": "150"' in line
    assert "someone@example.com" not in line


def test_select_lines_never_includes_entries_after_now():
    lines, ids = select_lines([entry("11:50:00", "before"), entry("12:10:00", "after")], NOW)

    assert ids == ["before"]
    assert len(lines) == 1
