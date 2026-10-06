"""Public Bench completion is persisted and verified before the terminal event."""
import json

import pytest

from tests.integration.test_studio_api import studio, draft, PREFIX


def events(response):
    return [(frame.splitlines()[0].removeprefix("event: "),
             json.loads(frame.splitlines()[1].removeprefix("data: ")))
            for frame in response.text.strip().split("\n\n")]


@pytest.mark.parametrize("streaming", [False, True])
def test_bench_completion_identifies_exact_persisted_evaluation(studio, streaming):
    client, db, runtime, app = studio
    bp, version = draft(client)
    previous = client.post(PREFIX + f"/versions/{version['id']}/bench",
                           json={"allow_remote_model": True}).json()
    response = client.post(PREFIX + f"/versions/{version['id']}/bench",
                           json={"allow_remote_model": True},
                           headers={"Accept": "text/event-stream"} if streaming else {})
    assert response.status_code == 200, response.text
    if streaming:
        frames = events(response)
        assert len([name for name, _ in frames if name == "bench.completed"]) == 1
        assert frames[-1][0] == "bench.completed"
        assert len([name for name, _ in frames if name == "scenario.completed"]) == 4
        result = frames[-1][1]
    else:
        result = response.json()
    assert result["evaluation_id"] != previous["evaluation_id"]
    assert result["version_id"] == version["id"]
    assert result["evaluation"]["id"] == result["evaluation_id"]
    assert result["evaluation"]["version_id"] == result["version_id"]
    assert result["evaluation"]["verified"] is True
    snapshot = client.get(PREFIX + "/snapshot").json()
    saved = next(e for e in snapshot["evaluations"] if e["id"] == result["evaluation_id"])
    assert result["evaluation"] == saved


def test_bench_stream_does_not_complete_before_persistence(studio, monkeypatch):
    client, db, runtime, app = studio
    _, version = draft(client)
    def refuse_storage(*args, **kwargs):
        raise RuntimeError("isolated persistence failure")
    monkeypatch.setattr("database.repositories.bench_repo.BenchRepository.record_evaluation", refuse_storage)
    response = client.post(PREFIX + f"/versions/{version['id']}/bench",
                           json={"allow_remote_model": True}, headers={"Accept": "text/event-stream"})
    names = [name for name, _ in events(response)]
    assert names[-1] == "bench.error"
    assert "bench.completed" not in names
    assert client.get(PREFIX + "/snapshot").json()["evaluations"] == []
