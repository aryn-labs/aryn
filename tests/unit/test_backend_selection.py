"""Missing, duplicated or interrupted shards cannot pass the quality gate."""
import json
from types import SimpleNamespace

import pytest

from scripts.check_backend_coverage import verify_coverage
from tests.backend_selection import select_backend_tests


def test_real_selection_is_order_independent_disjoint_and_complete():
    items = [SimpleNamespace(nodeid=f"test_{index}", get_closest_marker=lambda _: None) for index in range(29)]
    hosted = SimpleNamespace(nodeid="postgresql_only", get_closest_marker=lambda _: True)
    covered = set()
    for index in range(1, 5):
        selected, complete = select_backend_tests(items + [hosted], f"{index}/4")
        reversed_selection, reversed_complete = select_backend_tests(list(reversed(items)) + [hosted], f"{index}/4")
        ids = {item.nodeid for item in selected}
        assert ids == {item.nodeid for item in reversed_selection} and complete == reversed_complete
        assert not ids & covered and "postgresql_only" not in complete
        covered.update(ids)
    assert covered == {item.nodeid for item in items}
    with pytest.raises(pytest.UsageError):
        select_backend_tests(items, "0/4")


@pytest.fixture
def coverage(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    complete = [f"test_{index}" for index in range(8)]
    for platform, count in [("posix", 1), ("nt", 4)]:
        for index in range(count):
            folder = tmp_path / f"{platform}-{index}"
            folder.mkdir()
            selected = complete[index::count]
            (folder / "backend-selection.json").write_text(json.dumps({"platform": platform,
                "shard": f"{index+1}/{count}", "commit": "a" * 40, "complete": complete, "selected": selected}))
            (folder / "backend.xml").write_text("<testsuite>" + "<testcase/>" * len(selected) + "</testsuite>")
    return tmp_path


def test_full_coverage_is_accepted(coverage):
    verify_coverage(coverage)


@pytest.mark.parametrize("corruption", ["missing", "overlap", "interrupted", "commit"])
def test_partial_or_duplicated_execution_blocks_gate(coverage, corruption):
    path = coverage / "nt-0/backend-selection.json"
    if corruption == "missing":
        path.unlink()
    elif corruption == "interrupted":
        path.with_name("backend.xml").write_text("<testsuite/>")
    else:
        report = json.loads(path.read_text())
        if corruption == "overlap":
            report["selected"] = ["test_1", "test_5"]
        else:
            report["commit"] = "b" * 40
        path.write_text(json.dumps(report))
    with pytest.raises(AssertionError):
        verify_coverage(coverage)
