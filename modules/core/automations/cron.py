"""Bounded five-field numeric cron, never executable expressions."""

from functools import lru_cache
from datetime import date, timedelta
import re


@lru_cache(maxsize=256)
def fields(expression):
    if not isinstance(expression, str) or not 1 <= len(expression) <= 160:
        raise ValueError("Cron expression must be bounded.")
    pieces = expression.split()
    if len(pieces) != 5 or any(not re.fullmatch(r"[0-9*/,\-]+", p) for p in pieces):
        raise ValueError(
            "Cron requires five numeric fields; names/macros/code are unsupported."
        )
    result = []
    for token, (low, high) in zip(
        pieces, ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7)), strict=True
    ):
        values = set()
        for entry in token.split(","):
            parts = entry.split("/")
            if len(parts) > 2:
                raise ValueError("Invalid cron step.")
            base, step = parts[0], int(parts[1]) if len(parts) == 2 else 1
            if not 1 <= step <= high - low + 1:
                raise ValueError("Cron step is outside field bounds.")
            if base == "*":
                first, last = low, high
            elif "-" in base:
                bounds = base.split("-")
                if len(bounds) != 2:
                    raise ValueError("Invalid cron range.")
                first, last = map(int, bounds)
            else:
                first = int(base)
                last = high if len(parts) == 2 else first
            if not low <= first <= last <= high:
                raise ValueError("Cron value is outside field bounds.")
            values.update(range(first, last + 1, step))
        result.append(frozenset(values))
    return tuple(result), tuple(p == "*" for p in pieces)


def matching_day(expression, day):
    (_, _, days, months, weekdays), wild = fields(expression)
    dom, dow = day.day in days, ((day.weekday() + 1) % 7) in {v % 7 for v in weekdays}
    matched = (dom or dow) if not wild[2] and not wild[4] else dom and dow
    return day.month in months and matched


@lru_cache(maxsize=256)
def time_slots(expression):
    (minutes, hours, *_), _ = fields(expression)
    return tuple(sorted(h * 60 + m for h in hours for m in minutes))


@lru_cache(maxsize=256)
def validate(expression):
    fields(expression)
    start = date(2024, 1, 1)
    if not any(
        matching_day(expression, start + timedelta(days=offset))
        for offset in range(366 * 8)
    ):
        raise ValueError(
            "Cron has no occurrence in the supported eight-year calendar horizon."
        )
