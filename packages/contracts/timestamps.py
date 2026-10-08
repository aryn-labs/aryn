"""Canonical UTC timestamps shared by persisted governance envelopes."""
import datetime


def canonical_timestamp(value, *, stored=False):
    value = datetime.datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(value, datetime.datetime):
        raise ValueError("Invalid governance timestamp.")
    if value.tzinfo is None:
        if not stored:
            raise ValueError("Governance timestamps must specify a timezone.")
        # SQLAlchemy's SQLite DateTime drops tzinfo after storing normalized UTC.
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc).isoformat(timespec="microseconds")
