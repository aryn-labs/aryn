"""Deterministic backend test partition without altering any test assertion."""
import pytest


def select_backend_tests(items, shard):
    try:
        index, count = map(int, shard.split("/"))
        assert 1 <= index <= count <= 4
    except (ValueError, AssertionError):
        raise pytest.UsageError("Backend shard must be INDEX/COUNT, with 1 <= INDEX <= COUNT <= 4.") from None
    complete = sorted(item.nodeid for item in items if not item.get_closest_marker("postgresql"))
    assert len(complete) == len(set(complete)), "Duplicate collected test identities."
    chosen = set(complete[index - 1::count])
    return [item for item in items if item.nodeid in chosen], complete
