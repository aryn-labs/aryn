"""Calendar semantics are asserted as UTC instants, including DST transitions."""

import pytest
from pydantic import ValidationError
from packages.contracts.automation import Schedule, AutomationInput
from modules.core.automations.recurrence import (
    next_instant,
    due_window,
    instant,
    preview,
)


@pytest.mark.parametrize(
    "zone,wall,after,expected",
    [
        (
            "America/New_York",
            "02:30",
            "2026-03-07T12:00:00Z",
            "2026-03-09T06:30:00+00:00",
        ),
        (
            "America/New_York",
            "01:30",
            "2026-11-01T04:00:00Z",
            "2026-11-01T05:30:00+00:00",
        ),
        (
            "America/New_York",
            "01:30",
            "2026-11-01T05:31:00Z",
            "2026-11-02T06:30:00+00:00",
        ),
        ("Asia/Bangkok", "09:00", "2026-10-09T01:00:00Z", "2026-10-09T02:00:00+00:00"),
        (
            "Australia/Lord_Howe",
            "02:15",
            "2026-10-03T12:00:00Z",
            "2026-10-04T15:15:00+00:00",
        ),
    ],
)
def test_wall_clock_gap_skip_and_fold_once(zone, wall, after, expected):
    schedule = Schedule(
        timezone=zone, kind="daily", local_time=wall, start_at="2026-01-01T00:00:00Z"
    )
    assert next_instant(schedule, instant(after)).isoformat() == expected


def test_interval_is_utc_and_weekly_preview_respects_days():
    interval = Schedule(
        timezone="America/New_York",
        kind="interval",
        interval_minutes=60,
        start_at="2026-11-01T04:30:00Z",
    )
    values = preview(interval, instant("2026-11-01T04:29:00Z"), 4)
    assert [v["utc"] for v in values] == [
        f"2026-11-01T0{h}:30:00+00:00" for h in (4, 5, 6, 7)
    ]
    schedule = Schedule(kind="weekly", weekdays=[0], start_at="2026-10-09T00:00:00Z")
    assert (
        next_instant(schedule, instant("2026-10-09T00:00:00Z")).isoformat()
        == "2026-10-12T09:00:00+00:00"
    )


def test_clock_forward_catchup_is_bounded_and_backward_not_due():
    schedule = Schedule(
        kind="interval", interval_minutes=1, start_at="2026-01-01T00:00:00Z"
    )
    values, following, omitted = due_window(
        schedule, schedule.start_at, instant("2026-10-09T12:00:00Z"), 3
    )
    assert [v.isoformat() for v in values] == [
        "2026-10-09T11:58:00+00:00",
        "2026-10-09T11:59:00+00:00",
        "2026-10-09T12:00:00+00:00",
    ]
    assert omitted and following.isoformat() == "2026-10-09T12:01:00+00:00"
    assert due_window(schedule, following, instant("2026-10-08T12:00:00Z"), 3) == (
        [],
        following,
        None,
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"timezone": "Invalid/Unknown"},
        {"start_at": "2026-01-01T00:00:00"},
        {"interval_minutes": 0},
        {"weekdays": [7]},
        {"weekdays": [1, 1]},
        {"local_time": "25:00"},
        {"command": "whoami"},
    ],
)
def test_schedule_rejects_unsupported_or_ambiguous_input(extra):
    with pytest.raises(ValidationError):
        Schedule.model_validate({"start_at": "2026-01-01T00:00:00Z", **extra})


def test_browser_cannot_supply_scheduler_identity_or_native_jobs():
    with pytest.raises(ValidationError):
        AutomationInput.model_validate(
            {"owner_id": "admin", "native_job": {"command": "whoami"}}
        )
