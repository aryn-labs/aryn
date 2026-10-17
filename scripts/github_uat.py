"""Explicit local operator GitHub UAT. Never imported by application startup."""
import argparse
import asyncio
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import secrets
import stat
import uuid

from pydantic import SecretStr

from packages.contracts.tool import (GitHubUATPlan, GitHubIssueConnectionDefinition,
    GitHubIssueResultEvidence, GITHUB_API_ORIGIN, GITHUB_UAT_REPOSITORY, GITHUB_ISSUE_TOOL,
    GITHUB_ISSUE_INPUT, ToolDeclaration, github_issue_output)

VARIABLES = frozenset({"ARYN_GITHUB_UAT_TOKEN", "ARYN_GITHUB_UAT_REPOSITORY",
    "ARYN_GITHUB_UAT_ISSUE_NUMBER", "ARYN_GITHUB_UAT_ENABLE_LIVE"})
ENV_FILE = Path(__file__).resolve().parents[1] / ".env.github-uat"


class UATError(ValueError):
    """Fixed codes only; no configuration values or chained exceptions."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class UATConfig:
    plan: GitHubUATPlan
    token: SecretStr = field(repr=False)

    def validate(self):
        GitHubUATPlan.model_validate(self.plan.model_dump(mode="python", warnings=False))
        if (not isinstance(self.token, SecretStr)
                or not re.fullmatch(r"github_pat_[A-Za-z0-9_]{22,245}", self.token.get_secret_value())):
            raise UATError("uat_token_format_invalid")


def load_config(path, *, confirmed=False):
    """Read one bounded owner file; no dotenv expansion or ambient environment."""
    if confirmed is not True:
        raise UATError("uat_confirmation_required")
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        if Path(path).is_symlink():
            raise UATError("uat_config_invalid")
        with os.fdopen(os.open(path, flags), "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 2048:
                raise UATError("uat_config_invalid")
            raw = stream.read(2049)
        if len(raw) > 2048:
            raise UATError("uat_config_invalid")
        raw = raw.replace(b"\r\n", b"\n")
        if any(value < 32 and value != 10 for value in raw):
            raise UATError("uat_config_invalid")
        values = {}
        for line in raw.decode("ascii").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or key not in VARIABLES or key in values:
                raise UATError("uat_config_invalid")
            values[key] = value
        if values.get("ARYN_GITHUB_UAT_ENABLE_LIVE", "0") != "1":
            raise UATError("uat_live_gate_disabled")
        if values.get("ARYN_GITHUB_UAT_REPOSITORY") != GITHUB_UAT_REPOSITORY:
            raise UATError("uat_repository_invalid")
        number = values.get("ARYN_GITHUB_UAT_ISSUE_NUMBER", "")
        if not re.fullmatch(r"[1-9][0-9]{0,9}", number) or int(number) > 2147483647:
            raise UATError("uat_issue_number_invalid")
        token = values.get("ARYN_GITHUB_UAT_TOKEN", "")
        if not token:
            raise UATError("uat_token_missing")
        config = UATConfig(GitHubUATPlan(issue_number=int(number), enable_live=True,
            operator_confirmed=True, idempotency_key="github_uat_" + uuid.uuid4().hex), SecretStr(token))
        config.validate()
        return config
    except UATError:
        raise
    except Exception:
        raise UATError("uat_config_unavailable") from None


def _definition(context):
    return GitHubIssueConnectionDefinition(connection_id="github_uat", organization_id=context.organization_id,
        project_id=context.project_id, owner_id=context.actor.actor_id, endpoint=GITHUB_API_ORIGIN,
        repository_owner="aryn-labs", repository_name="aryn", route="/repos/aryn-labs/aryn/issues/{key}",
        declaration=ToolDeclaration(name=GITHUB_ISSUE_TOOL, input_schema=GITHUB_ISSUE_INPUT),
        output_schema=github_issue_output(context.organization_id, context.project_id, "aryn-labs", "aryn"),
        calls_per_minute=1)


def _build_core(config):
    from database.connection import DatabaseManager, create_db_engine
    from database.schema import Base
    from database.repositories.organization_repo import OrganizationRepository
    from modules.core.evidence import EvidenceSigner
    from modules.core.identity.binder import TrustedIdentityBinder
    from modules.core.permissions.engine import PermissionEngine
    from modules.core.workflows.coordinator import RunCoordinator
    from packages.contracts.core import Actor, SecurityContext
    from packages.runtime_adapters.github_uat import GitHubUATModelDouble
    from packages.model_adapters import ModelRouter
    from packages.contracts.model import ModelSpec, ModelProviderType
    # Explicit isolated state/keys: no application DB, identity environment,
    # persistent key files, provider configuration or runtime process is loaded.
    engine = create_db_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("BEGIN")
            Base.metadata.create_all(connection)
        db = DatabaseManager(engine, evidence_signer=EvidenceSigner(secrets.token_bytes(32)))
        db.protected_credentials = (config.token.get_secret_value(),)
        binder = TrustedIdentityBinder(secret_key=secrets.token_bytes(32))
        permissions = PermissionEngine(db_manager=db, identity_binder=binder)
        context = binder.bind_context(SecurityContext(actor=Actor(actor_id="github_uat_operator",
            organization_id="github_uat_org", roles=["admin"]), organization_id="github_uat_org", project_id="github_uat_project"))
        with db.session() as session:
            repo = OrganizationRepository(session)
            repo.create_organization(context.organization_id, "Operator GitHub UAT", "github-uat")
            repo.add_member(context.organization_id, context.actor.actor_id, "admin")
            repo.create_project(context, context.project_id, "Operator GitHub UAT", "github-uat")
        # Explicit operator-only model double; never a production catalog/default.
        offline_router = ModelRouter(catalog={"mock-fast": ModelSpec(provider=ModelProviderType.MOCK,
            model_id="mock-fast", display_name="Isolated GitHub operator UAT double", requires_api_key=False)})
        core = RunCoordinator(GitHubUATModelDouble(config.plan.issue_number), db_manager=db, model_router=offline_router,
            permission_engine=permissions, https_endpoints=(GITHUB_API_ORIGIN,))
        return db, context, core
    except BaseException:
        engine.dispose()
        raise


async def _verified_summary(db, context, core, result, approval):
    from database.repositories.audit_repo import AuditRepository
    from database.repositories.run_state_repo import RunStateRepository
    from database.schema import AuditEventModel
    from packages.contracts.bench import evidence_hash, strict_json_loads
    from packages.contracts.runtime import RunStatus
    if result.status != RunStatus.COMPLETED:
        stage = (result.execution_evidence or {}).get("failure_stage")
        if result.error_code == "tool_failed" and stage:
            code = {"authorization": "uat_permission_denied", "destination": "uat_destination_denied",
                "connect": "uat_network_unverified", "network": "uat_network_unverified",
                "tls": "uat_tls_unverified", "response_headers": "uat_response_invalid",
                "response_body": "uat_response_invalid", "response_validation": "uat_response_invalid"}.get(stage, "tool_failed")
            raise UATError(code)
        raise UATError(result.error_code or "uat_execution_failed")
    core.mcp_tools.current(context, GITHUB_ISSUE_TOOL, approval.binding_hash)
    if await core.get_managed_result(result.run_id, context) != result:
        raise UATError("uat_evidence_invalid")
    trace = await core.get_managed_trace(result.run_id, context)
    with db.session() as session:
        row = RunStateRepository(session).get_run(context, result.run_id)
        events = session.query(AuditEventModel).filter_by(resource_id=result.run_id,
            organization_id=context.organization_id, project_id=context.project_id).all()
        if not events or not all(AuditRepository(session).verify_authenticated_event(event) for event in events):
            raise UATError("uat_evidence_invalid")
        completed = [event for event in events if event.event_type == "core.run.evidence"]
        proofs = [strict_json_loads(event.redacted_payload_json)["github_provenance"] for event in events
            if event.event_type == "core.tool.result"]
        proof, = proofs
        proof = GitHubIssueResultEvidence.model_validate(proof).model_dump(mode="json")
        data = strict_json_loads(result.output)
        expected_action = [{"action_id": "issue_read", "action": "github.issue.read",
            "tool": GITHUB_ISSUE_TOOL, "capability": "github.issue.read"}]
        if (not trace.available or not result.execution_claim_verified or result.assignment_id is not None
                or row.execution_mode != "github_uat" or len(completed) != 1
                or not db.evidence_signer.verify("https_connection_approval", approval.payload(), approval.attestation)
                or proof["run_id"] != result.run_id or proof["trace_id"] != context.correlation_id
                or proof["organization_id"] != context.organization_id or proof["project_id"] != context.project_id
                or proof["call_id"] != "issue_read" or proof["tool_name"] != GITHUB_ISSUE_TOOL
                or proof["binding_hash"] != approval.binding_hash
                or proof["schema_hash"] != approval.connection.schema_hash
                or proof["endpoint_hash"] != evidence_hash(approval.connection.endpoint)
                or proof["repository_binding_hash"] != approval.connection.repository_binding_hash
                or result.execution_evidence["actions"] != expected_action
                or result.execution_evidence["resources"] != {"iterations": 2, "tool_call_attempts": 1}
                or data["repository"] != GITHUB_UAT_REPOSITORY or data["issue_number"] != proof["issue_number"]
                or proof["issue_number"] != result.effective_limits["github_operator_uat"]["issue_number"]
                or data["source"] != ("github_https" if approval.connection.endpoint == GITHUB_API_ORIGIN else "github_https_fixture")):
            raise UATError("uat_evidence_invalid")
        return {"status": "VERIFIED", "execution_profile": "human_operator_with_isolated_model_double",
            **data, "run_id": result.run_id, "trace_id": context.correlation_id,
            "binding_hash": proof["binding_hash"], "repository_binding_hash": proof["repository_binding_hash"],
            "invocation_hash": proof["invocation_hash"], "response_digest": proof["response_digest"],
            "http_status": proof["http_status"], "tls_verified": proof["tls_verified"],
            "network_requests": proof["network_requests"], "validation": proof["validation"],
            "signed_execution_verified": True, "core_claim_attestation": row.execution_attestation,
            "completion_attestation": completed[0].attestation, "audit_events_verified": len(events),
            "evidence_hash": evidence_hash(result.execution_evidence), "paid_inference": False}


def _failure(code):
    codes = {"uat_confirmation_required", "uat_config_invalid", "uat_config_unavailable", "uat_live_gate_disabled",
        "uat_repository_invalid", "uat_issue_number_invalid", "uat_token_missing", "uat_token_format_invalid",
        "uat_execution_failed", "uat_evidence_invalid", "uat_cleanup_failed", "uat_permission_denied",
        "uat_timeout", "uat_cancelled", "uat_destination_denied", "uat_network_unverified", "uat_tls_unverified",
        "uat_response_invalid", "github_unauthorized", "github_forbidden", "github_issue_not_found",
        "github_rate_limited", "github_service_error", "github_response_rejected", "tool_failed",
        "tool_permission_denied", "tool_input_invalid", "execution_limit_exceeded"}
    return {"status": "FAILED", "error_code": code if code in codes else "uat_failed", "retry": False}


async def run_uat(config):
    from modules.core.errors import protect_diagnostic_logging
    from modules.core.permissions.engine import PermissionDeniedError
    from packages.tool_adapters.https import HTTPSBoundaryError
    approval, db, report = None, None, None
    try:
        config.validate()
        protect_diagnostic_logging((config.token.get_secret_value(),))
        db, context, core = _build_core(config)
        async with asyncio.timeout(30):
            approval = await core.mcp_tools.register(context, _definition(context), config.token, ttl_seconds=60)
            result = await core.execute_github_uat(config.plan, context)
            report = await _verified_summary(db, context, core, result, approval)
    except UATError as error:
        report = _failure(error.code)
    except PermissionDeniedError:
        report = _failure("uat_permission_denied")
    except TimeoutError:
        report = _failure("uat_timeout")
    except HTTPSBoundaryError:
        report = _failure("uat_destination_denied")
    except OSError:
        report = _failure("uat_network_unverified")
    except Exception:
        # No traceback, request, config, upstream message or exception chain leaves
        # this trusted CLI boundary, even for unexpected bootstrap failures.
        report = _failure("uat_failed")
    finally:
        if db is not None:
            try:
                if approval is not None:
                    core.mcp_tools.revoke(context, approval.connection.connection_id)
                    if report is not None:
                        report["credential_revoked"] = True
            except Exception:
                report = _failure("uat_cleanup_failed")
            finally:
                db.engine.dispose()
    return report


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unknown argument values, which may be secrets.
        raise UATError("uat_config_invalid")


def main(argv=None):
    try:
        parser = _Parser(description="One Core-governed GitHub issue read; owner file opt-in also required.")
        parser.add_argument("--confirm-live-github-read", action="store_true", help="Explicitly authorize the one read for this invocation.")
        args = parser.parse_args(argv)
        config = load_config(ENV_FILE, confirmed=args.confirm_live_github_read)
        report = asyncio.run(run_uat(config))
    except UATError as error:
        report = _failure(error.code)
    except KeyboardInterrupt:
        report = _failure("uat_cancelled")
    except Exception:
        report = _failure("uat_failed")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
