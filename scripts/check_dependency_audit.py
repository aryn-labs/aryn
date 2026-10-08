"""An empty/partial dependency audit is not a successful vulnerability gate."""
import argparse
import importlib.metadata
import json
from pathlib import Path

from packaging.utils import canonicalize_name


def verify_report(path, *, native=False, site_packages=None):
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    records = report["dependencies"]
    audited = {canonicalize_name(item["name"]) for item in records}
    required = {"aiohttp", "openai", "httpx", "pydantic", "jsonschema"} if native else {"authlib", "pyjwt", "cryptography", "sqlalchemy", "fastapi", "jsonschema", "alembic", "httpx", "pydantic"}
    assert required <= audited, "Audit did not inspect the actual application/runtime dependencies."
    inventory = {canonicalize_name(item.metadata["Name"]): item.version for item in importlib.metadata.distributions(
        **({"path": [site_packages]} if site_packages else {}))}
    assert inventory.keys() <= audited, "Installed dependency inventory differs from scanner report."
    for item in records:
        assert not item.get("vulns"), "Known vulnerability blocks delivery."
        if item.get("skip_reason"):
            assert canonicalize_name(item["name"]) in {"aryn", "hermes-agent"}, "Unverifiable third-party dependency."
        elif canonicalize_name(item["name"]) in inventory:
            assert item["version"] == inventory[canonicalize_name(item["name"])], "Audit inspected a different installed version."
    print(f"Verified complete dependency audit: {len(audited)} distributions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--site-packages")
    options = parser.parse_args()
    verify_report(options.report, native=options.native, site_packages=options.site_packages)
