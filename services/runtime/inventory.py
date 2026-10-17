"""Discover installed Hermes metadata without executing tools or availability probes."""
import hashlib
import inspect
from pathlib import Path

from packages.contracts.runtime_control import RuntimeFeature, RuntimeInventory, RuntimeSkill


def discover_skill_content():
    """Bounded source reads under native skill roots; symlinks cannot escape them."""
    from hermes_constants import get_hermes_home
    from tools import skills_tool
    roots = [(get_hermes_home() / "skills").resolve(), (Path(skills_tool.__file__).resolve().parents[1] / "skills").resolve()]
    result = {}
    catalog = getattr(skills_tool, "_skill_catalog", None)
    if catalog is None:
        return result
    for entry in catalog(skip_disabled=True):
        name = entry.get("load_name")
        path = Path(entry["path"]).resolve()
        if not name or not any(path.is_relative_to(root) for root in roots) or path.stat().st_size > 65536:
            continue
        raw = path.read_bytes()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if name in result:
            result.pop(name)
            continue
        result[name] = {"name": name, "description": entry.get("description", "")[:2000],
            "category": entry.get("category") or "", "content_hash": hashlib.sha256(raw).hexdigest(),
            "content": content}
    return result


def discover_toolsets():
    from toolsets import get_all_toolsets, resolve_toolset
    toolsets = []
    for name, spec in sorted(get_all_toolsets().items()):
        tools = sorted(set(resolve_toolset(name)))
        # Unknown and composite tools remain high risk until operator-reviewed.
        toolsets.append(RuntimeFeature(name=name, description=str(spec.get("description", ""))[:2000],
            tools=tools, availability="unknown", verification="runtime_observed", native_cli=True,
            native_api=True, reason="native_toolset_discovered_execution_readiness_unverified"))
    return toolsets


def discover_inventory(configuration_id):
    from hermes_cli.version_info import get_version_info
    from gateway.platforms.api_server import _STATIC_FEATURE_FLAGS
    identity = get_version_info()
    toolsets = discover_toolsets()
    features = [RuntimeFeature(name=name, availability="unknown" if enabled is True else "unavailable",
        verification="installed_source", native_api=enabled is True,
        reason="native_api_advertised_execution_unverified" if enabled is True else "unsupported_by_native_api")
        for name, enabled in sorted(_STATIC_FEATURE_FLAGS.items()) if isinstance(enabled, bool)]
    # Jobs routes exist even when the API's static feature flags say otherwise.
    from gateway.platforms.api_server import APIServerAdapter
    for name, method in (("jobs", "_handle_create_job"), ("scheduler", "_handle_cron_fire")):
        present = callable(getattr(APIServerAdapter, method, None))
        features.append(RuntimeFeature(name=name, native_api=present, native_cli=True,
            availability="unknown" if present else "unavailable", verification="installed_source",
            risk="persistent_state", reason="native_dispatch_requires_scoped_worker_and_core_readmission"))
    skills = []
    try:
        from tools.skills_tool import _find_all_skills
        # Supported signatures differ between the installed source and CI pin.
        kwargs = {"skip_disabled": True}
        if "include_editorial" in inspect.signature(_find_all_skills).parameters:
            kwargs["include_editorial"] = True
        contents = discover_skill_content()
        for item in _find_all_skills(**kwargs):
            content = contents.get(item["name"])
            skills.append(RuntimeSkill(name=item["name"], description=item.get("description", "")[:2000],
                category=item.get("category") or "", content_hash=content["content_hash"] if content else None))
    except (ImportError, ValueError, TypeError, OSError):
        features.append(RuntimeFeature(name="skills_metadata", reason="installed_skill_discovery_failed"))
    return RuntimeInventory(version=identity.base_version, source_revision=identity.commit,
        configuration_id=configuration_id, toolsets=toolsets, skills=skills, features=features,
        settings={"model_gateway": "9Router", "native_model_fallback": False,
            "native_host_tool_execution": False, "auxiliary_model_requests": False,
            "native_profile_ingress": False, "credential_persistence": False,
            "settings_revision": hashlib.sha256(configuration_id.encode()).hexdigest()},
        reason="installed_runtime_metadata_only")
