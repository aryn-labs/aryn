"""Bounded UTC planning; wall time gaps skip, folds choose the first instant."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from packages.contracts.automation import Schedule
from modules.core.automations.cron import matching_day, time_slots
from bisect import bisect_left

UTC = timezone.utc


def wall_instant(date, minute, zone):
    wall = datetime(
        date.year, date.month, date.day, minute // 60, minute % 60, tzinfo=zone, fold=0
    )
    candidate = wall.astimezone(UTC)
    return (
        candidate
        if candidate.astimezone(zone).replace(tzinfo=None) == wall.replace(tzinfo=None)
        else None
    )


def instant(value):
    parsed = (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, str)
        else value
    )
    if parsed.tzinfo is None:
        raise ValueError("Scheduler clock must be timezone aware.")
    return parsed.astimezone(UTC)


def next_instant(schedule: Schedule, after):
    after, start = instant(after), instant(schedule.start_at)
    if schedule.kind == "interval":
        seconds = schedule.interval_minutes * 60
        count = max(0, int((after - start).total_seconds() // seconds) + 1)
        return start + timedelta(seconds=count * seconds)
    if schedule.kind == "webhook":
        raise ValueError("Event triggers have no timed recurrence.")
    zone = ZoneInfo(schedule.timezone)
    lower = max(after, start - timedelta(microseconds=1))
    day = lower.astimezone(zone).date()
    hour, minute = map(int, schedule.local_time.split(":"))
    times = [hour * 60 + minute]
    if schedule.kind == "cron":
        times = time_slots(schedule.cron_expression)
    for offset in range(366 * 8 if schedule.kind == "cron" else 15):
        date = day + timedelta(days=offset)
        if schedule.kind == "cron" and not matching_day(schedule.cron_expression, date):
            continue
        if schedule.kind == "weekly" and date.weekday() not in schedule.weekdays:
            continue
        local = lower.astimezone(zone)
        begin = bisect_left(times, local.hour * 60 + local.minute) if offset == 0 else 0
        for value in times[begin:]:
            candidate = wall_instant(date, value, zone)
            if candidate is not None and candidate > after and candidate >= start:
                return candidate
    raise ValueError("No supported recurrence within the bounded planning window.")


def preview(schedule, after, count=5):
    result = []
    current = instant(after)
    for _ in range(count):
        current = next_instant(schedule, current)
        result.append(
            {
                "utc": current.isoformat(),
                "local": current.astimezone(ZoneInfo(schedule.timezone)).isoformat(),
            }
        )
    return result


def due_window(schedule, next_at, clock, limit):
    """Keep the latest bounded catchup. Older history is explicitly coalesced."""
    current, clock = instant(next_at), instant(clock)
    if current > clock:
        return [], current, None
    original = current
    cutoff = clock - timedelta(days=7)
    if schedule.kind == "cron":
        # Select only the latest bounded instants, rather than iterating every
        # missed minute. Older history remains an explicit coalesced interval.
        zone, kept = ZoneInfo(schedule.timezone), []
        lower = max(current, cutoff, instant(schedule.start_at))
        day, final_day = clock.astimezone(zone).date(), lower.astimezone(zone).date()
        times = time_slots(schedule.cron_expression)
        for offset in range((day - final_day).days + 1):
            date = day - timedelta(days=offset)
            if not matching_day(schedule.cron_expression, date):
                continue
            for minute in reversed(times):
                candidate = wall_instant(date, minute, zone)
                if candidate is not None and lower <= candidate <= clock:
                    kept.append(candidate)
                    if len(kept) == limit:
                        break
            if len(kept) == limit:
                break
        kept.reverse()
        omitted = (
            kept[0] - timedelta(microseconds=1)
            if kept and kept[0] > original
            else clock
            if not kept and original < cutoff
            else None
        )
        return kept, next_instant(schedule, clock), omitted
    if current < cutoff:
        current = next_instant(schedule, cutoff - timedelta(microseconds=1))
    kept = []
    while current <= clock:
        kept.append(current)
        kept = kept[-limit:]
        current = next_instant(schedule, current)
    omitted_through = (
        kept[0] - timedelta(microseconds=1) if kept and kept[0] > original else None
    )
    return kept, current, omitted_through
