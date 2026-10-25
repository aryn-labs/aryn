"""Real bounded file/Git reads, current claims and fail-closed source changes."""

import json
from pathlib import Path
import pytest
from tests.integration.test_studio_api import studio as studio, PREFIX
from services.api.studio import DEV_ORG, DEV_PROJECT
from packages.tool_adapters.evidence import LocalEvidence, EvidenceBoundaryError


def configure(app, root, kind="file"):
    binding = {"binding_id": "reviewed_runbooks", "organization_id": DEV_ORG, "project_id": DEV_PROJECT,
        "kind": kind, "root": str(root), "files": {"selected_file": "README.md" if kind == "git" else "runbook.md"}}
    app.state.brief.local_evidence = LocalEvidence({"bindings": [binding]})
    return binding


def register(client):
    response = client.post(PREFIX + "/brief/connections", json={
        "binding_id": "reviewed_runbooks", "name": "Reviewed operational source"})
    assert response.status_code == 201, response.text
    return response.json()


def collect(client, connection, **changes):
    response = client.post(PREFIX + "/brief/collect", json={"connection_id": connection["id"],
        "file_key": "selected_file", "title": "Authorized physical source", **changes})
    assert response.status_code == 201, response.text
    return response.json()


def bundle(client, source, hypothesis=None):
    response = client.post(PREFIX + "/brief", json={"title": "Bounded source observation",
        "hypothesis": hypothesis or {"question": "Does this source literally contain the recovery instruction?",
            "predicate": "contains_text", "text": "approved recovery"}, "source_ids": [source["id"]]})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("change", ["modify", "remove", "revoke"])
def test_physical_file_change_or_revocation_invalidates_claim(studio, tmp_path, change):
    client, db, runtime, app = studio
    path = tmp_path / "runbook.md"
    path.write_text("Runbook: use approved recovery after human review.", encoding="utf-8")
    configure(app, tmp_path)
    connection = register(client)
    captured = collect(client, connection)
    verified = bundle(client, captured["source"])
    assert verified["evaluation"]["status"] == "SUPPORTED"
    if change == "modify":
        path.write_text("The recovery procedure was withdrawn.", encoding="utf-8")
    elif change == "remove":
        path.unlink()
    else:
        response = client.post(PREFIX + f"/brief/connections/{connection['id']}/grant", json={
            "expected_configuration_hash": connection["configuration_hash"], "enabled": False})
        assert response.status_code == 200, response.text
    current = client.get(PREFIX + "/brief/" + verified["id"]).json()
    assert current["evaluation"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert current["evaluation"]["items"][0]["integrity"] == "UNVERIFIED"
    assert not runtime.requests


def test_real_git_blob_revision_and_head_drift_without_creating_commits(studio, tmp_path):
    client, db, runtime, app = studio
    source_root = Path(__file__).resolve().parents[2]
    repository = tmp_path / "source_repository"
    repository.mkdir()

    def git(*args):
        return LocalEvidence.git(repository, "-c", "protocol.file.allow=always", *args).decode().strip()

    git("init", "--initial-branch=main")
    # Copy existing history into this test-owned object database. No commit,
    # checkout, remote account, provider or source repository write is involved.
    git("fetch", "--no-tags", "--depth=2", str(source_root), "HEAD")
    revision = git("rev-parse", "FETCH_HEAD")
    parent = git("rev-parse", "FETCH_HEAD^")
    git("update-ref", "refs/heads/main", revision)
    configure(app, repository, "git")
    connection = register(client)
    captured = collect(client, connection)
    assert captured["reference"]["git_revision"] == revision
    hypothesis = {"question": "Does this captured blob describe the repository's current revision?",
        "predicate": "source_matches_revision", "subject_id": captured["reference"]["id"], "text": revision}
    verified = bundle(client, captured["source"], hypothesis)
    assert verified["evaluation"]["status"] == "SUPPORTED"
    git("update-ref", "refs/heads/main", parent, revision)
    current = client.get(PREFIX + "/brief/" + verified["id"]).json()
    assert current["evaluation"]["status"] == "INSUFFICIENT_EVIDENCE"
    historical = collect(client, connection, git_revision=revision)
    hypothesis["subject_id"] = historical["reference"]["id"]
    assert bundle(client, historical["source"], hypothesis)["evaluation"]["status"] == "CONFLICTING"
    assert git("rev-parse", "HEAD") == parent


def test_file_selection_secret_redaction_and_cross_scope(studio, tmp_path):
    client, db, runtime, app = studio
    secret = "isolated-source-redaction-value-473912"
    db.protected_credentials = (*db.protected_credentials, secret)
    (tmp_path / "runbook.md").write_text("approved recovery " + secret, encoding="utf-8")
    configure(app, tmp_path)
    connection = register(client)
    captured = collect(client, connection)
    assert captured["source"]["sanitized"]
    repeated = collect(client, connection)
    duplicate = client.post(PREFIX + "/brief", json={"title": "Duplicate origin cannot inflate coverage",
        "source_ids": [captured["source"]["id"], repeated["source"]["id"]], "hypothesis": {
            "question": "Do two independent source origins support this literal?", "predicate": "contains_text",
            "text": "approved recovery", "minimum_sources": 2}})
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["evaluation"]["coverage"] == 1
    assert duplicate.json()["evaluation"]["status"] == "INSUFFICIENT_EVIDENCE"
    body = client.get(PREFIX + "/brief/sources/" + captured["source"]["id"])
    assert secret not in body.text
    assert client.post(PREFIX + "/brief/collect", json={"connection_id": connection["id"],
        "file_key": "unreviewed_file", "title": "Denied selection"}).status_code == 409
    assert client.post("/api/projects/another_project/brief/collect", json={"connection_id": connection["id"],
        "file_key": "selected_file", "title": "Cross scope denied"}).status_code in {403, 404}
    # No host paths are returned in configuration or source projections.
    assert str(tmp_path) not in json.dumps(client.get(PREFIX + "/brief/connections").json())


@pytest.mark.parametrize("path", ["../runbook.md", "/etc/passwd", "C:/runbook.md", "runbooks\\entry.md", ".env", "secrets.txt"])
def test_trusted_binding_rejects_unsafe_paths(tmp_path, path):
    with pytest.raises(EvidenceBoundaryError):
        LocalEvidence({"bindings": [{"binding_id": "unsafe", "organization_id": DEV_ORG,
            "project_id": DEV_PROJECT, "root": str(tmp_path), "kind": "file", "files": {"file": path}}]})


def test_shared_file_identity_cannot_escape_evidence_boundary(studio, tmp_path):
    import os
    client, db, runtime, app = studio
    original = tmp_path / "original.md"
    original.write_text("approved recovery", encoding="utf-8")
    os.link(original, tmp_path / "runbook.md")
    configure(app, tmp_path)
    connection = register(client)
    response = client.post(PREFIX + "/brief/collect", json={"connection_id": connection["id"],
        "file_key": "selected_file", "title": "Shared file must be denied"})
    assert response.status_code == 409 and not runtime.requests


@pytest.mark.parametrize("redirection", ["commondir", "config_include"])
def test_git_binding_refuses_external_metadata_redirection(tmp_path, redirection):
    LocalEvidence.git(tmp_path, "init", "--initial-branch=main")
    if redirection == "commondir":
        (tmp_path / ".git" / "commondir").write_text("../another_store", encoding="utf-8")
    else:
        with (tmp_path / ".git" / "config").open("a", encoding="utf-8") as stream:
            stream.write('\n[include]\npath = ../another_configuration\n')
    with pytest.raises(EvidenceBoundaryError):
        LocalEvidence({"bindings": [{"binding_id": "redirected_history", "organization_id": DEV_ORG,
            "project_id": DEV_PROJECT, "root": str(tmp_path), "kind": "git", "files": {"readme": "README.md"}}]})


@pytest.mark.parametrize("root", ["relative_directory", "//example.invalid/share"])
def test_root_configuration_denies_ambient_or_unc_network_paths(root):
    with pytest.raises(EvidenceBoundaryError):
        LocalEvidence({"bindings": [{"binding_id": "denied_root", "organization_id": DEV_ORG,
            "project_id": DEV_PROJECT, "root": root, "kind": "file", "files": {"runbook": "runbook.md"}}]})
