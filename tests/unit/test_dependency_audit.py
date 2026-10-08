"""Security reports must cover the installed dependencies, including unknowns."""
import json
from types import SimpleNamespace

import pytest

from scripts.check_dependency_audit import verify_report


@pytest.fixture
def audit_report(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.check_dependency_audit.importlib.metadata.distributions", lambda **kwargs: [])
    names = ["authlib", "pyjwt", "cryptography", "sqlalchemy", "fastapi", "jsonschema", "alembic", "httpx", "pydantic"]
    path = tmp_path / "audit.json"
    return path, {"dependencies": [{"name": name, "vulns": []} for name in names]}


def test_complete_dependency_report_is_accepted(audit_report):
    path, report = audit_report
    path.write_text(json.dumps(report))
    verify_report(path)


@pytest.mark.parametrize("failure", ["missing", "unknown", "vulnerable", "empty"])
def test_partial_or_unverified_dependency_report_blocks_delivery(audit_report, failure):
    path, report = audit_report
    if failure == "missing":
        report["dependencies"].pop()
    elif failure == "empty":
        report["dependencies"] = []
    else:
        report["dependencies"].append({"name": "unverifiable-vendor", "skip_reason": "not in registry"}
                                       if failure == "unknown" else {"name": "vendor", "vulns": [{"id": "synthetic-advisory"}]})
    path.write_text(json.dumps(report))
    with pytest.raises(AssertionError):
        verify_report(path)


def test_installed_dependency_omitted_from_audit_blocks_delivery(audit_report, monkeypatch):
    path, report = audit_report
    path.write_text(json.dumps(report))
    monkeypatch.setattr("scripts.check_dependency_audit.importlib.metadata.distributions",
                        lambda **kwargs: [SimpleNamespace(metadata={"Name": "installed-but-omitted"})])
    with pytest.raises(AssertionError, match="inventory differs"):
        verify_report(path)
