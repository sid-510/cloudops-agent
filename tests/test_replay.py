from datetime import datetime, timezone

from cloudops_agent.replay import (
    in_window,
    replay_get_recent_errors,
    replay_search_logs_by_text,
    replay_top_errors,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def entry(minute, severity="ERROR", message="Payment provider request timed out", insert_id="x"):
    return {
        "timestamp": f"2026-01-01T{minute}+00:00",
        "severity": severity,
        "message": message,
        "insert_id": insert_id,
    }


def test_replay_never_shows_entries_after_now():
    entries = [entry("11:55:00", insert_id="before"), entry("12:05:00", insert_id="after")]

    result = in_window(entries, minutes=60, now=NOW)

    assert [e["insert_id"] for e in result] == ["before"]


def test_replay_respects_the_time_window():
    entries = [entry("11:50:00", insert_id="recent"), entry("10:00:00", insert_id="old")]

    result = in_window(entries, minutes=30, now=NOW)

    assert [e["insert_id"] for e in result] == ["recent"]


def test_replay_errors_only_returns_error_or_worse():
    entries = [entry("11:50:00", "INFO"), entry("11:51:00", "ERROR"), entry("11:52:00", "CRITICAL")]

    result = replay_get_recent_errors(entries, NOW, minutes=60)

    assert [e["severity"] for e in result] == ["CRITICAL", "ERROR"]


def test_replay_text_search_ignores_case():
    entries = [entry("11:50:00", "INFO", "Checkout completed"), entry("11:51:00")]

    result = replay_search_logs_by_text(entries, NOW, "TIMED OUT", minutes=60)

    assert len(result) == 1


def test_replay_top_errors_counts_messages():
    entries = [entry("11:50:00"), entry("11:51:00"), entry("11:52:00", message="POST /checkout -> 502")]

    result = replay_top_errors(entries, NOW, minutes=60)

    assert result["top_errors"][0]["message"] == "Payment provider request timed out"
    assert result["top_errors"][0]["count"] == 2