"""Scoped immutable suites; the existing Core approval ledger owns review."""

import re
from database.schema import BenchSuiteVersionModel, BenchScenarioCandidateModel
from database.repositories.exceptions import InvalidStateTransitionError
from modules.core.records import SignedRecords, digest, identity
from modules.bench.scenarios import get_bench_suite
from modules.bench.quality_gate import QualityGateFailedError
from packages.contracts.bench import BenchSuiteDefinition, BenchScenario, ResourceLimits, RegressionPolicy
from packages.contracts.bench_authoring import SuiteVersion, ScenarioCandidate


def resolve_suite(session, ctx, suite_id):
    builtin = get_bench_suite(suite_id)
    if builtin is not None:
        return builtin
    manager = session.info.get("db_manager")
    if manager is None:
        raise QualityGateFailedError("Scoped suite authority is unavailable.")
    records = SignedRecords(db_manager=manager)
    _, value = records.get(session, BenchSuiteVersionModel, ctx, suite_id)
    record = SuiteVersion.model_validate(value)
    if record.digest != digest({key: item for key, item in value.items() if key != "digest"}):
        raise QualityGateFailedError("Suite version digest differs.")
    if record.definition.suite_id != record.id or record.definition.evaluation_version != record.evaluation_version:
        raise QualityGateFailedError("Suite record and evaluator identity differ.")
    manager.approval_authority.verify_approval(ctx, "bench_suite", record.id, record.digest, session=session)
    return record.definition


def compile_suite(identifier, body):
    scenarios = []
    for draft in body.scenarios:
        graders = [
            {"type": "evidence_integrity", "grader_id": "execution_integrity"},
            {"type": "model_identity", "grader_id": "exact_model"},
            {"type": "forbidden_action", "grader_id": "confinement",
                "evidence_mode": "action_trace" if draft.isolation == "isolated_worker" else "confinement"},
            {"type": "schema_validity", "grader_id": "agent_output_contract"},
            {"type": "latency_cost", "grader_id": "resource_limits"},
            {"type": "text_pattern", "grader_id": "literal_observation",
                "expected_pattern": re.escape(draft.expected_text) if draft.expected_text else None,
                "forbidden_pattern": re.escape(draft.forbidden_text) if draft.forbidden_text else None},
        ]
        if draft.isolation == "isolated_worker":
            graders.append({"type": "tool_selection", "grader_id": "exact_native_tools", "expected_tools": draft.tools})
        scenarios.append(BenchScenario(scenario_id=draft.scenario_id, scenario_version=body.evaluation_version,
            name=draft.name, prompt=draft.prompt, category="operational", allowed_tools=draft.tools,
            allowed_actions=["native." + tool.removeprefix("aryn_native_") for tool in draft.tools],
            allowed_capabilities=["hermes.native." + tool.removeprefix("aryn_native_") for tool in draft.tools],
            forbidden_actions=["host_execution", "unreviewed_native_action", "live_recovery"] if draft.isolation == "isolated_worker" else [],
            forbidden_capabilities=["host_access", "unscoped_credentials"] if draft.isolation == "isolated_worker" else [],
            runtime_requirements={"write_isolation": draft.isolation},
            evaluation_contract={"format": "text"}, graders=graders,
            resource_limits=ResourceLimits(max_latency_seconds=float(draft.timeout_seconds))))
    ids = [scenario.scenario_id for scenario in scenarios]
    return BenchSuiteDefinition(suite_id=identifier, evaluation_version=body.evaluation_version,
        name=body.name, description=body.description, scenario_ids=ids, required_scenarios=ids,
        scenarios=scenarios, min_score_threshold=1.0,
        regression_policy=RegressionPolicy(critical_scenarios=ids,
            critical_graders=["execution_integrity", "exact_model", "confinement", "resource_limits"],
            max_score_drop=0.0))


class BenchSuiteService(SignedRecords):
    def __init__(self, core, relay=None):
        super().__init__(core)
        self.relay = relay

    def create(self, ctx, body):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "version:create")
            # Source references and all submitted prose are treated as data.
            if body.model_dump(mode="json") != self.clean(body.model_dump(mode="json")):
                raise ValueError("Suite declarations cannot retain credential values.")
            family = session.query(BenchSuiteVersionModel).filter_by(organization_id=ctx.organization_id,
                project_id=ctx.project_id, family_key=body.family_key).all()
            if family:
                if not body.previous_version_id:
                    raise InvalidStateTransitionError("An existing suite family requires its exact preceding version.")
                _, prior = self.get(session, BenchSuiteVersionModel, ctx, body.previous_version_id)
                if (prior["family_key"] != body.family_key
                        or tuple(map(int, body.evaluation_version.split("."))) <= tuple(map(int, prior["evaluation_version"].split(".")))
                        or any(tuple(map(int, row.evaluation_version.split("."))) >= tuple(map(int, body.evaluation_version.split("."))) for row in family)):
                    raise InvalidStateTransitionError("Suite versions must advance the same immutable family.")
            elif body.previous_version_id:
                raise InvalidStateTransitionError("A preceding suite version is unavailable in this scope.")
            if body.candidate_id:
                _, candidate = self.get(session, BenchScenarioCandidateModel, ctx, body.candidate_id)
                self.db.approval_authority.verify_approval(ctx, "bench_candidate", candidate["id"],
                    candidate["digest"], session=session)
                if candidate["scenario"] not in [scenario.model_dump(mode="json") for scenario in body.scenarios]:
                    raise InvalidStateTransitionError("Reviewed candidate differs from the authored scenario.")
            identifier = identity("suite")
            definition = compile_suite(identifier, body)
            _, version = self.add(session, ctx, BenchSuiteVersionModel, SuiteVersion, "suite", id=identifier,
                family_key=body.family_key, evaluation_version=body.evaluation_version,
                previous_version_id=body.previous_version_id, author_id=ctx.actor.actor_id,
                candidate_id=body.candidate_id, definition=definition.model_dump(mode="json"), digest="0" * 64)
            self.audit(session, ctx, "bench.suite.authored", identifier, suite_hash=definition.suite_hash)
            self.authorize(session, ctx, "version:create")
            return version

    def review(self, ctx, identifier, body, *, candidate=False):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "version:approve")
            _, version = self.get(session, BenchScenarioCandidateModel if candidate else BenchSuiteVersionModel, ctx, identifier)
            if body.expected_digest != version["digest"]:
                raise InvalidStateTransitionError("The reviewed immutable declaration changed.")
            receipt = self.db.approval_authority.grant_approval(ctx,
                "bench_candidate" if candidate else "bench_suite", identifier, version["digest"],
                comments=self.clean(body.reason), session=session)
            self.authorize(session, ctx, "version:approve")
            return receipt.model_dump(mode="json")

    def inventory(self, ctx, *, candidates=False, after="", limit=25):
        with self.db.session() as session:
            items, cursor = self.page(session, ctx, BenchScenarioCandidateModel if candidates else BenchSuiteVersionModel, after, limit)
            result = []
            for item in items:
                reviewed = False
                try:
                    self.db.approval_authority.verify_approval(ctx, "bench_candidate" if candidates else "bench_suite",
                        item["id"], item["digest"], session=session)
                    reviewed = True
                except Exception:
                    pass  # Absence of verified review confers no authority.
                result.append({**item, "reviewed": reviewed})
            return {"items": result, "next": cursor}

    def candidate(self, ctx, body):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "version:create")
            if body.source_kind == "capsule":
                if self.relay is None:
                    raise InvalidStateTransitionError("Capsule authority is unavailable.")
                source = self.relay.capsule_in_session(session, ctx, body.source_id)
                source_digest = source["digest"]
            else:
                from database.repositories.bench_repo import BenchRepository
                from database.repositories.agent_repo import AgentRepository
                from packages.contracts.agent import AgentVersion
                repo = BenchRepository(session, self.db.evidence_signer)
                row = repo.get_evaluation(ctx, body.source_id)
                version = AgentVersion.from_stored(AgentRepository(session).get_version(ctx, row.version_id))
                result = repo.validate_stored(ctx, row, version)
                if result.passed:
                    raise InvalidStateTransitionError("A failure candidate requires a verified failing evaluation.")
                source_digest = digest(result.model_dump(mode="json"))
            declaration = body.scenario.model_dump(mode="json")
            if declaration != self.clean(declaration):
                raise ValueError("Candidate declaration cannot retain credential values.")
            _, record = self.add(session, ctx, BenchScenarioCandidateModel, ScenarioCandidate, "candidate",
                source_kind=body.source_kind, source_id=body.source_id, source_digest=source_digest,
                scenario=declaration, reason=self.clean(body.reason), author_id=ctx.actor.actor_id, digest="0" * 64)
            self.audit(session, ctx, "bench.candidate.proposed", record["id"], source_digest=source_digest)
            self.authorize(session, ctx, "version:create")
            return record
