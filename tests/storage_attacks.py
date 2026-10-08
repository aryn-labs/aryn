"""Deliberate owner-level corruption beyond SQL append-only enforcement.

Tests that exercise receipt verification disable DDL guards explicitly, preserving
their old assertions. Separate tests prove ordinary SQL cannot mutate history.
This helper does not touch the independent commitment or signing authority.
"""
from contextlib import contextmanager

from database.governance_protection import install_history_protection, remove_history_protection


@contextmanager
def corrupt_storage(engine):
    with engine.begin() as connection:
        remove_history_protection(connection)
        try:
            yield connection
        finally:
            install_history_protection(connection)
