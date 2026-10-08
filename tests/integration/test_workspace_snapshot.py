"""Snapshot query reuse must preserve verification for every legacy record."""
from sqlalchemy import event

from database.repositories.audit_repo import AuditRepository
from services.api.studio import DEV_ACTOR, DEV_ORG, DEV_PROJECT
from tests.integration.test_studio_api import studio as studio, PREFIX
from tests.workspace_dataset import seed_workspace_dataset


def test_snapshot_reuses_loaded_audits_without_skipping_authentication(studio, monkeypatch):
    client, db, _, app = studio
    context = app.state.binder.create_trusted_context(DEV_ACTOR, DEV_ORG, DEV_PROJECT)
    counts = seed_workspace_dataset(db, context, "small")
    verified = []
    original = AuditRepository.verify_authenticated_event
    def check(self, record):
        verified.append(record.id)
        return original(self, record)
    monkeypatch.setattr(AuditRepository, "verify_authenticated_event", check)
    selects = []
    def observe(connection, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT") and "FROM audit_events" in statement:
            selects.append(statement)
    event.listen(db.engine, "before_cursor_execute", observe)
    try:
        response = client.get(PREFIX + "/snapshot")
        assert response.status_code == 200, response.text
        audit = response.json()["audit"]
        assert len(audit) == len(set(verified)) == counts["audits"]
        assert all(item["authenticated"] for item in audit)
        assert len(selects) == 1
    finally:
        event.remove(db.engine, "before_cursor_execute", observe)
