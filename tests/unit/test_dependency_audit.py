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
                        lambda **kwargs: [SimpleNamespace(metadata={"Name": "installed-but-omitted"}, version="1.0")])
    with pytest.raises(AssertionError, match="inventory differs"):
        verify_report(path)


def test_native_dependency_audit_requires_aryn_contract_dependencies(audit_report):
    path, _ = audit_report
    report = {"dependencies": [{"name": name, "vulns": []} for name in ["aiohttp", "openai", "httpx", "pydantic"]]}
    path.write_text(json.dumps(report))
    with pytest.raises(AssertionError, match="actual application/runtime"):
        verify_report(path, native=True)
    report["dependencies"].append({"name": "jsonschema", "vulns": []})
    path.write_text(json.dumps(report))
    verify_report(path, native=True)


def test_audit_of_different_version_cannot_authorize_installed_dependency(audit_report, monkeypatch):
    path, report = audit_report
    monkeypatch.setattr("scripts.check_dependency_audit.importlib.metadata.distributions",
                        lambda **kwargs: [SimpleNamespace(metadata={"Name": "authlib"}, version="1.7.2")])
    report["dependencies"][0]["version"] = "1.7.1"
    path.write_text(json.dumps(report))
    with pytest.raises(AssertionError, match="different installed version"):
        verify_report(path)
    report["dependencies"][0]["version"] = "1.7.2"
    path.write_text(json.dumps(report))
    verify_report(path)
