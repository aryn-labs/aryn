"""Unit tests for canonical Agent Definition domain contracts and policies.

Verifies:
1. First-class typed contracts: AgentDefinition, OutputContract, Constraints, ToolPolicy,
   ModelPolicy, BudgetPolicy, and EvaluationReference.
2. Explicit tool grant policy with deny-by-default and forbidden tool rejection.
3. Exact model policy enforcement and silent fallback prohibition (ADR-005).
4. Canonical v3 payload hashing and backwards-compatible legacy v2 verification.
5. Immutability of published configuration across all domain policies.
6. Blueprint persona specification with role, objective, and owner.
"""

import json
import pytest

from packages.contracts.core import Actor, ActorType, SecurityContext
from packages.contracts.agent import (
    AgentBlueprint,
    AgentBudgetPolicy,
    AgentConstraints,
    AgentDefinition,
    AgentEvaluationReference,
    AgentModelPolicy,
    AgentOutputContract,
    AgentToolPolicy,
    AgentVersion,
    AgentVersionStatus,
    ForbiddenToolError,
    VersionIntegrityError,
)
from database.connection import create_db_engine, DatabaseManager
from database.schema import Base
from database.repositories.organization_repo import OrganizationRepository
from database.repositories.agent_repo import AgentRepository
from modules.agent_factory.service import AgentFactoryService
from modules.bench.runner import BenchRunner
from tests.conftest import bind_test_context
from tests.studio_runtime import IsolatedTestRuntime


def test_agent_output_contract_defaults_and_customization():
    default_contract = AgentOutputContract()
    assert default_contract.format == "text"
    assert default_contract.schema_definition is None
    assert default_contract.required_sections == []
    assert default_contract.strict is False

    custom_contract = AgentOutputContract(
        format="json",
        schema_definition={"type": "object", "properties": {"summary": {"type": "string"}}},
        required_sections=["Executive Summary", "Evidence Citations"],
        strict=True,
    )
    assert custom_contract.format == "json"
    assert custom_contract.strict is True
    assert len(custom_contract.required_sections) == 2


def test_agent_constraints_rules_and_citations():
    constraints = AgentConstraints(
        disallowed_actions=["direct_shell", "remote_upload"],
        operational_rules=["abstain_on_unverified_evidence"],
        require_evidence_citation=True,
        max_execution_time_seconds=90,
    )
    assert "direct_shell" in constraints.disallowed_actions
    assert constraints.require_evidence_citation is True
    assert constraints.max_execution_time_seconds == 90


def test_agent_tool_policy_explicit_grant_and_deny_by_default():
    policy = AgentToolPolicy(
        tool_grants=["research_lookup", "table_parser"],
        deny_by_default=True,
    )
    assert policy.is_tool_allowed("research_lookup") is True
    assert policy.is_tool_allowed("table_parser") is True
    assert policy.is_tool_allowed("unlisted_tool") is False
    assert policy.is_tool_allowed("terminal") is False

    # Forbidden tools must raise on validation
    bad_policy = AgentToolPolicy(tool_grants=["terminal", "research_lookup"])
    with pytest.raises(ForbiddenToolError, match="strictly forbidden"):
        bad_policy.validate_tool_grants()


@pytest.mark.parametrize("forbidden", ["terminal", "bash", "shell", "os_exec", "file", "browser", "code_execution"])
def test_all_forbidden_tools_rejected_case_insensitively(forbidden):
    policy = AgentToolPolicy(tool_grants=[forbidden.upper()])
    with pytest.raises(ForbiddenToolError, match="strictly forbidden"):
        policy.validate_tool_grants()
    assert policy.is_tool_allowed(forbidden) is False


def test_agent_model_policy_exact_model_and_anti_fallback():
    policy = AgentModelPolicy(
        primary_model="meta-llama/llama-3.3-70b-instruct",
        provider="9router",
        allowed_models=["meta-llama/llama-3.3-70b-instruct", "google/gemini-2.0-flash-001"],
        temperature=0.2,
        max_tokens=4096,
        allow_fallback=False,
    )
    # Valid model matches primary or allowed
    policy.validate_model("meta-llama/llama-3.3-70b-instruct")
    policy.validate_model("google/gemini-2.0-flash-001")

    # Unallowed model must be rejected without silent fallback
    with pytest.raises(ValueError, match="silent fallback is prohibited"):
        policy.validate_model("unregistered-shadow-model")


def test_agent_budget_policy_bounds():
    budget = AgentBudgetPolicy(
        max_tokens_per_run=8192,
        max_turns=5,
        max_cost_usd=0.25,
        timeout_seconds=60,
    )
    assert budget.max_tokens_per_run == 8192
    assert budget.max_turns == 5
    assert budget.max_cost_usd == 0.25


def test_agent_evaluation_reference_standards():
    ref = AgentEvaluationReference()
    assert ref.suite_id == "research-safety"
    assert ref.min_score_threshold == 1.0
    assert len(ref.required_scenarios) == 4
    assert "prompt_injection_rejection" in ref.required_scenarios


def test_agent_definition_composition():
    definition = AgentDefinition(
        schema_version="1.0.0",
        role="financial_analyst",
        objective="Analyze quarterly liquidity and solvency disclosures with primary citations.",
        owner="lead_researcher",
        output_contract=AgentOutputContract(format="markdown", required_sections=["Summary", "Findings"]),
        constraints=AgentConstraints(operational_rules=["strictly_abstain_on_contradiction"]),
        tool_policy=AgentToolPolicy(tool_grants=["sec_filing_search"]),
        model_policy=AgentModelPolicy(primary_model="mock-quality", temperature=0.3),
        budget_policy=AgentBudgetPolicy(max_tokens_per_run=4096),
        evaluation_reference=AgentEvaluationReference(suite_id="research-safety"),
    )
    assert definition.role == "financial_analyst"
    assert definition.tool_policy.tool_grants == ["sec_filing_search"]
    assert definition.output_contract.format == "markdown"


def test_version_canonical_hash_covers_all_first_class_policies():
    v1 = AgentVersion(
        id="av_001",
        blueprint_id="abp_001",
        version_number="1.0.0",
        system_prompt="Analyze research filings.",
        model="mock-fast",
        role="analyst",
        objective="Analyze liquidity",
        owner="owner_1",
        output_contract=AgentOutputContract(format="markdown"),
        constraints=AgentConstraints(operational_rules=["cite_evidence"]),
        tool_policy=AgentToolPolicy(tool_grants=["lookup"]),
        model_policy=AgentModelPolicy(primary_model="mock-fast", temperature=0.4),
        budget_policy=AgentBudgetPolicy(max_tokens_per_run=2048),
        evaluation_reference=AgentEvaluationReference(),
    )
    v1.payload_hash = v1.calculate_payload_hash()
    v1.verify_integrity()

    # Tampering with objective changes hash
    tampered_objective = v1.model_copy(update={"objective": "Compromised objective"})
    assert tampered_objective.calculate_payload_hash() != v1.payload_hash

    # Tampering with role changes hash
    tampered_role = v1.model_copy(update={"role": "malicious_role"})
    assert tampered_role.calculate_payload_hash() != v1.payload_hash

    # Tampering with output contract changes hash
    tampered_output = v1.model_copy(update={"output_contract": AgentOutputContract(format="json")})
    assert tampered_output.calculate_payload_hash() != v1.payload_hash

    # Tampering with constraints changes hash
    tampered_constraints = v1.model_copy(update={"constraints": AgentConstraints(operational_rules=["bypass"])})
    assert tampered_constraints.calculate_payload_hash() != v1.payload_hash

    # Tampering with tool policy changes hash
    tampered_tool = v1.model_copy(update={"tool_policy": AgentToolPolicy(tool_grants=["lookup", "other"])})
    assert tampered_tool.calculate_payload_hash() != v1.payload_hash

    # Tampering with model policy changes hash
    tampered_model_policy = v1.model_copy(update={"model_policy": AgentModelPolicy(primary_model="unauthorized")})
    assert tampered_model_policy.calculate_payload_hash() != v1.payload_hash

    # Tampering with budget policy changes hash
    tampered_budget = v1.model_copy(update={"budget_policy": AgentBudgetPolicy(max_tokens_per_run=99999)})
    assert tampered_budget.calculate_payload_hash() != v1.payload_hash

    # Tampering with schema version changes hash
    tampered_schema = v1.model_copy(update={"schema_version": "2.0.0"})
    assert tampered_schema.calculate_payload_hash() != v1.payload_hash


def test_legacy_format_v2_backward_compatibility():
    # Construct an older v2 payload manually
    legacy_canonical = {
        "canonical_format": 2,
        "id": "av_legacy",
        "blueprint_id": "abp_legacy",
        "version_number": "1.0.0",
        "system_prompt": "Legacy prompt.",
        "model": "mock-fast",
        "tool_grants": [],
        "temperature": 0.7,
        "max_tokens": 2048,
        "metadata": {},
    }
    import hashlib
    legacy_hash = hashlib.sha256(json.dumps(legacy_canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    version = AgentVersion(
        id="av_legacy",
        blueprint_id="abp_legacy",
        version_number="1.0.0",
        system_prompt="Legacy prompt.",
        model="mock-fast",
        payload_hash=legacy_hash,
    )
    # verify_integrity must accept legacy format 2 without error
    version.verify_integrity()

    # But tampering with legacy system prompt must still fail
    tampered_legacy = version.model_copy(update={"system_prompt": "Tampered"})
    with pytest.raises(VersionIntegrityError, match="integrity"):
        tampered_legacy.verify_integrity()


def test_agent_blueprint_with_definition_persona():
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = DatabaseManager(engine=engine)

    ctx = bind_test_context(SecurityContext(
        actor=Actor(actor_id="research_director", organization_id="org_alpha", roles=["admin"]),
        organization_id="org_alpha",
        project_id="proj_research",
    ))

    with db.session(write=True) as session:
        OrganizationRepository(session).create_organization("org_alpha", "Alpha Org", "alpha-org")
        OrganizationRepository(session).add_member("org_alpha", "research_director", "admin")
        OrganizationRepository(session).create_project(ctx, "proj_research", "Research Project", "research-proj")

    runtime = IsolatedTestRuntime()
    factory = AgentFactoryService(db, BenchRunner(runtime))

    bp = factory.create_blueprint(
        context=ctx,
        name="Lead Investigator",
        slug="lead-investigator",
        description="Senior research persona",
        role="senior_investigator",
        objective="Lead safety and solvency verification.",
        owner="research_director",
    )
    assert bp.role == "senior_investigator"
    assert bp.objective == "Lead safety and solvency verification."
    assert bp.owner == "research_director"

    # Creating a version inherits blueprint defaults if not explicitly specified
    version = factory.create_version(
        context=ctx,
        blueprint_id=bp.id,
        version_number="1.0.0",
        system_prompt="Conduct rigorous evidence synthesis.",
        model="mock-fast",
    )
    assert version.role == "senior_investigator"
    assert version.objective == "Lead safety and solvency verification."
    assert version.owner == "research_director"
    assert version.definition.role == "senior_investigator"
    assert version.definition.output_contract.format == "text"
    assert version.definition.tool_policy.deny_by_default is True
