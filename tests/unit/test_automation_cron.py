"""Cron syntax, calendar/DST, frequency, and bounded recovery semantics."""

import pytest
from pydantic import ValidationError
from packages.contracts.automation import Schedule
from modules.core.automations.recurrence import (
    next_instant,
    instant,
    preview,
    due_window,
)


def cron(expression, zone="UTC"):
    return Schedule(
        kind="cron",
        cron_expression=expression,
        timezone=zone,
        start_at="2024-01-01T00:00:00Z",
    )


@pytest.mark.parametrize(
    "expression,after,expected",
    [
        ("0 9 * * 1-5", "2026-10-09T10:00:00Z", "2026-10-12T09:00:00+00:00"),
        ("*/15 8-10 * * *", "2026-10-12T08:14:59Z", "2026-10-12T08:15:00+00:00"),
        ("0 9 1 * 0", "2026-10-02T00:00:00Z", "2026-10-04T09:00:00+00:00"),
        ("0 9 * * 7", "2026-10-03T00:00:00Z", "2026-10-04T09:00:00+00:00"),
        ("0 9 29 2 *", "2026-01-01T00:00:00Z", "2028-02-29T09:00:00+00:00"),
        ("1,31 12 * 1,10 *", "2026-10-12T12:01:01Z", "2026-10-12T12:31:00+00:00"),
    ],
)
def test_numeric_cron_calendar_and_traditional_dom_dow(expression, after, expected):
    assert next_instant(cron(expression), instant(after)).isoformat() == expected


@pytest.mark.parametrize(
    "expression",
    [
        "@daily",
        "* * * *",
        "60 0 * * *",
        "0 24 * * *",
        "0 9 0 * *",
        "0 9 * 13 *",
        "0 9 * * 8",
        "*/0 * * * *",
        "* * * * MON",
        "0 9 L * *",
        "0 9 * * 1#2",
        "0 9 * * ?",
        "0, 9 * * *",
        "0 9 30 2 *",
        "0 9 31 4 *",
        "1-0 * * * *",
        "$(whoami)",
        "* * * * *;id",
    ],
)
def test_cron_rejects_code_names_impossible_dates_and_bounds(expression):
    with pytest.raises(ValidationError):
        cron(expression)


@pytest.mark.parametrize(
    "expression,after,expected",
    [
        ("30 2 * * *", "2026-03-07T12:00:00Z", "2026-03-09T06:30:00+00:00"),
        ("30 1 * * *", "2026-11-01T04:00:00Z", "2026-11-01T05:30:00+00:00"),
        ("30 1 * * *", "2026-11-01T05:31:00Z", "2026-11-02T06:30:00+00:00"),
    ],
)
def test_cron_skips_gap_and_only_uses_first_fold(expression, after, expected):
    assert (
        next_instant(cron(expression, "America/New_York"), instant(after)).isoformat()
        == expected
    )


def test_preview_and_per_minute_recovery_have_no_duplicate_or_backward_rewind():
    schedule = cron("* * * * *", "Asia/Jakarta")
    values = preview(schedule, instant("2026-10-12T00:00:00Z"))
    assert len(values) == 5 and len({v["utc"] for v in values}) == 5
    assert values[0]["local"] == "2026-10-12T07:01:00+07:00"
    due, following, omitted = due_window(
        schedule, "2026-10-12T00:00:00Z", instant("2026-10-12T00:10:00Z"), 3
    )
    assert len(due) == 3 and omitted
    assert due_window(schedule, following, instant("2026-10-12T00:00:00Z"), 3) == (
        [],
        following,
        None,
    )


def test_trigger_contract_forbids_mixed_cron_and_webhook_and_has_no_fake_event_preview():
    with pytest.raises(ValidationError):
        Schedule(kind="cron", start_at="2026-01-01T00:00:00Z")
    with pytest.raises(ValidationError):
        Schedule(
            kind="daily", cron_expression="* * * * *", start_at="2026-01-01T00:00:00Z"
        )
    with pytest.raises(ValueError):
        next_instant(
            Schedule(kind="webhook", start_at="2026-01-01T00:00:00Z"),
            instant("2026-01-01T00:00:00Z"),
        )


@pytest.mark.parametrize(
    "value",
    ["0001-01-01T00:00:00Z", "9999-12-31T00:00:00Z", "0001-01-01T00:00:00+14:00"],
)
def test_unrepresentable_planning_horizon_rejected_before_recurrence(value):
    with pytest.raises(ValidationError):
        Schedule(kind="cron", cron_expression="* * * * *", start_at=value)


@pytest.mark.parametrize(
    "expression,zone,after,clock",
    [
        ("* * * * *", "UTC", "2026-10-12T00:00:00Z", "2026-10-12T03:00:00Z"),
        (
            "*/15 * * * *",
            "Asia/Jakarta",
            "2026-10-12T00:00:00Z",
            "2026-10-12T03:02:00Z",
        ),
        (
            "30 2 * * *",
            "America/New_York",
            "2026-03-06T07:30:00Z",
            "2026-03-10T08:00:00Z",
        ),
        (
            "30 1 * * *",
            "America/New_York",
            "2026-10-30T05:30:00Z",
            "2026-11-02T07:00:00Z",
        ),
        ("0 9 1 * 0", "UTC", "2026-10-01T09:00:00Z", "2026-10-05T09:00:00Z"),
    ],
)
def test_reverse_bounded_catchup_matches_forward_actual_instants(
    expression, zone, after, clock
):
    schedule = cron(expression, zone)
    current, cutoff, recorded = instant(after), instant(clock), []
    while current <= cutoff:
        recorded.append(current)
        current = next_instant(schedule, current)
    values, following, _ = due_window(schedule, after, cutoff, 3)
    assert values == recorded[-3:] and following == current


def test_sparse_old_cron_cursor_is_coalesced_without_fake_individual_occurrences():
    schedule = cron("0 9 1 1 *")
    values, following, omitted = due_window(
        schedule, "2024-01-01T09:00:00Z", instant("2026-10-12T00:00:00Z"), 3
    )
    assert values == [] and following == instant("2027-01-01T09:00:00Z")
    assert omitted == instant("2026-10-12T00:00:00Z")
