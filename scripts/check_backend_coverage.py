"""The complete Linux suite and union of Windows shards must cover the same tests."""
import json
import os
from pathlib import Path
import sys
from xml.etree import ElementTree


def verify_coverage(directory):
    groups = {"posix": [], "nt": []}
    complete = None
    for path in Path(directory).rglob("backend-selection.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["commit"], "Selection must bind to a commit."
        if os.getenv("GITHUB_SHA"):
            assert report["commit"] == os.environ["GITHUB_SHA"], "Selection must match the workflow commit."
        current = set(report["complete"])
        assert current and len(current) == len(report["complete"])
        if complete is None:
            complete = current
            commit = report["commit"]
        assert current == complete and report["commit"] == commit, "Runner collections or commits differ."
        selected = set(report["selected"])
        assert selected <= complete and len(selected) == len(report["selected"])
        xml = ElementTree.parse(path.with_name("backend.xml"))
        assert len(list(xml.iter("testcase"))) == len(selected), "Interrupted or partial test execution."
        assert not list(xml.iter("failure")) and not list(xml.iter("error"))
        groups[report["platform"]].append((report["shard"], selected))
    assert len(groups["posix"]) == 1 and len(groups["nt"]) == 4, "Every backend runner is required."
    for platform, reports in groups.items():
        assert {shard for shard, _ in reports} == ({"1/1"} if platform == "posix" else {"1/4", "2/4", "3/4", "4/4"})
        covered = set()
        for _, selected in reports:
            assert not covered & selected, "Backend shards overlap."
            covered.update(selected)
        assert covered == complete, "Backend tests are missing."
    print(f"Complete backend coverage verified for both platforms: {len(complete)} tests at {commit}.")


if __name__ == "__main__":
    verify_coverage(sys.argv[1])
