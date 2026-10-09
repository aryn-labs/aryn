"""Bounded UTC planning; wall time gaps skip, folds choose the first instant."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from packages.contracts.automation import Schedule

UTC = timezone.utc


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
    zone = ZoneInfo(schedule.timezone)
    lower = max(after, start - timedelta(microseconds=1))
    day = lower.astimezone(zone).date()
    hour, minute = map(int, schedule.local_time.split(":"))
    for offset in range(15):
        date = day + timedelta(days=offset)
        if schedule.kind == "weekly" and date.weekday() not in schedule.weekdays:
            continue
        wall = datetime(
            date.year, date.month, date.day, hour, minute, tzinfo=zone, fold=0
        )
        candidate = wall.astimezone(UTC)
        # A round trip rejects nonexistent local times during a DST gap.
        restored = candidate.astimezone(zone)
        if restored.replace(tzinfo=None) != wall.replace(tzinfo=None):
            continue
        if candidate > after and candidate >= start:
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
