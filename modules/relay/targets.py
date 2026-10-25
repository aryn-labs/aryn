"""Registered operational targets governed by the existing Relay/Core records."""

import datetime
import time
from database.schema import DemoFixtureModel, RelayExecutionModel, RelayIncidentModel, RelayProposalModel
from database.repositories.exceptions import InvalidStateTransitionError
from modules.core.records import digest, now
from modules.core.workflows.ownership import ExecutionOwnershipError
from packages.contracts.operational import ServiceTarget, ServiceState, service_target


class OperationalTargetOperations:
    def target_binding(self, ctx, target):
        if self.targets is None:
            raise InvalidStateTransitionError("Operational bindings are not configured.")
        binding = self.targets.binding(ctx, target["binding_id"])
        if digest(binding) != target["binding_hash"]:
            raise InvalidStateTransitionError("Trusted target binding changed; review and re-register.")
        return binding

    def refresh_target(self, session, ctx, row, target):
        if not service_target(target):
            return target
        self.target_binding(ctx, target)
        probe = self.targets.observe(ctx, target["binding_id"])
        session.info.setdefault("operational_measurements", {})[target["binding_hash"]] = (time.monotonic(), probe)
        state = probe["controller"]
        if state["instance"] != target["instance"]:
            raise InvalidStateTransitionError("Target process identity changed; existing authority is invalid.")
        target.update(revision=state["generation"], running=state["running"],
            blocking_fault=state["blocking_fault"], last_execution_id=state["last_execution_id"],
            probe=probe, updated_at=now())
        self.put(session, ctx, row, target)
        return target

    def register_target(self, ctx, body):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "tool:register")
            if self.targets is None:
                raise InvalidStateTransitionError("Operational bindings are not configured.")
            binding = self.targets.binding(ctx, body.binding_id)
            probe = self.targets.observe(ctx, body.binding_id)
            # One durable identity per trusted binding. Registration never resets
            # existing claims, grants or target history.
            for existing in session.query(DemoFixtureModel).filter_by(
                    organization_id=ctx.organization_id, project_id=ctx.project_id).all():
                _, record = self.get(session, DemoFixtureModel, ctx, existing.id)
                if service_target(record) and (record["binding_id"] == body.binding_id
                        or record["instance"] == probe["controller"]["instance"]):
                    raise InvalidStateTransitionError("Operational binding or physical process instance is already registered.")
            state = probe["controller"]
            configuration = {"binding_hash": digest(binding), "enabled": True,
                "revision": 1, "allowed_actions": ["restart_service"], "max_actions_per_hour": 6,
                "timeout_seconds": 15}
            _, target = self.add(session, ctx, DemoFixtureModel, ServiceTarget, "target",
                name=self.clean(body.name), revision=state["generation"], running=state["running"],
                blocking_fault=state["blocking_fault"], updated_at=now(),
                last_execution_id=state["last_execution_id"], binding_id=body.binding_id,
                binding_hash=digest(binding), instance=state["instance"], enabled=True,
                configuration_hash=digest(configuration), configuration_revision=1, probe=probe)
            observed, source = self.observation(session, ctx, target, "created")
            self.audit(session, ctx, "relay.target.registered", target["id"],
                binding_hash=target["binding_hash"], configuration_hash=target["configuration_hash"])
            self.authorize(session, ctx, "tool:register")
            return {"target": target, "observation": observed, "source": source}

    def grant_target(self, ctx, identifier, body):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "tool:register")
            row, target = self.get(session, DemoFixtureModel, ctx, identifier, True)
            if not service_target(target) or body.expected_configuration_hash != target["configuration_hash"]:
                raise InvalidStateTransitionError("Target configuration changed.")
            self.target_binding(ctx, target)
            target.update(enabled=body.enabled, configuration_revision=target["configuration_revision"] + 1)
            target["configuration_hash"] = digest({"binding_hash": target["binding_hash"],
                "enabled": target["enabled"], "revision": target["configuration_revision"],
                "allowed_actions": ["restart_service"], "max_actions_per_hour": 6, "timeout_seconds": 15})
            self.put(session, ctx, row, target)
            self.audit(session, ctx, "relay.target.grant_changed", identifier,
                configuration_hash=target["configuration_hash"], enabled=target["enabled"])
            self.authorize(session, ctx, "tool:register")
            return target

    def observe_target(self, ctx, identifier):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "run:create")
            row, target = self.get(session, DemoFixtureModel, ctx, identifier, True)
            if not service_target(target):
                raise InvalidStateTransitionError("Use the explicit fixture interface for database simulations.")
            self.refresh_target(session, ctx, row, target)
            observed, source = self.observation(session, ctx, target, "collection")
            self.authorize(session, ctx, "run:create")
            return {"target": target, "observation": observed, "source": source}

    @staticmethod
    def state_snapshot(target):
        if not service_target(target):
            return {key: target[key] for key in ("running", "blocking_fault")}
        state = target["probe"]["controller"]
        return ServiceState(running=state["running"], blocking_fault=state["blocking_fault"],
            instance=state["instance"], generation=state["generation"], child_instance=state["child_instance"],
            last_execution_id=state["last_execution_id"], probe_digest=digest(target["probe"])).model_dump()

    def validate_service_proposal(self, session, ctx, target, proposal, claim_id=None):
        binding = self.target_binding(ctx, target)
        if (not target["enabled"] or proposal["configuration_hash"] != target["configuration_hash"]
                or proposal["binding_hash"] != target["binding_hash"]
                or proposal["instance"] != target["instance"] or time.time() >= proposal["expires_at"]
                or proposal["action"] != "restart_service" or target["running"]
                or proposal.get("execution_profile") != binding["profile"]):
            raise InvalidStateTransitionError("Operational grant, expiry, identity or stopped-process precondition differs.")
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        if "last_admission_id" not in target or claim_id and target["last_admission_id"] != claim_id:
            raise InvalidStateTransitionError("The protected target admission anchor differs; execution is blocked.")
        identifier, seen, count = target["last_admission_id"], set(), 0
        while identifier:
            if identifier in seen or len(seen) > target["max_actions_per_hour"]:
                raise InvalidStateTransitionError("Operational admission lineage is cyclic or exceeds its bound.")
            seen.add(identifier)
            _, claim = self.get(session, RelayExecutionModel, ctx, identifier)
            if claim["target_id"] != target["id"]:
                raise InvalidStateTransitionError("Operational admission lineage changed target.")
            if identifier != claim_id and claim["status"] in {"running", "action_completed", "outcome_unknown"}:
                raise InvalidStateTransitionError("An unresolved target execution prevents another effect.")
            if datetime.datetime.fromisoformat(claim["created_at"]) < cutoff:
                break
            count += identifier != claim_id
            if count >= target["max_actions_per_hour"]:
                raise InvalidStateTransitionError("Operational action quota exhausted.")
            identifier = claim.get("previous_admission_id")

    def admit_service(self, session, ctx, effect, execution, target_row, target, proposal):
        deadline = min(time.time() + target["timeout_seconds"], proposal["expires_at"],
            target["probe"]["controller"]["expires_at"])
        payload = {"organization_id": ctx.organization_id, "project_id": ctx.project_id,
            "actor_id": ctx.actor.actor_id, "owner_id": self.core.authority.owner_id,
            "execution_id": execution["id"], "proposal_id": proposal["id"], "previous_admission_id": target["last_admission_id"],
            "payload_hash": proposal["payload_hash"], "approval_id": execution["approval"]["approval_id"],
            "target_id": target["id"], "binding_hash": target["binding_hash"],
            "configuration_hash": target["configuration_hash"], "instance": target["instance"],
            "generation": target["revision"], "action": "restart_service", "deadline_at": deadline}
        execution.update(deadline_at=deadline, previous_admission_id=target["last_admission_id"], admission={"payload": payload,
            "attestation": self.db.evidence_signer.sign("relay_operational_action", payload)})
        target["last_admission_id"] = execution["id"]
        self.put(session, ctx, target_row, target)
        self.put(session, ctx, effect, execution)

    def apply_service(self, ctx, execution_id):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "run:create")
            from packages.contracts.core import ActorType
            from modules.core.permissions.engine import PermissionDeniedError
            if ctx.actor.actor_type != ActorType.USER:
                raise PermissionDeniedError("An agent cannot inherit operational control-plane authority.")
            _, execution = self.get(session, RelayExecutionModel, ctx, execution_id)
            target_row, target = self.get(session, DemoFixtureModel, ctx, execution["target_id"], True)
            _, incident = self.get(session, RelayIncidentModel, ctx, execution["incident_id"], True)
            effect, execution = self.get(session, RelayExecutionModel, ctx, execution_id, True)
            self.refresh_target(session, ctx, target_row, target)
            _, proposal = self.get(session, RelayProposalModel, ctx, execution["proposal_id"])

            def reauthorize():
                self.core._fence()
                self.authorize(session, ctx, "run:create")
                if (execution["owner_id"] != self.core.authority.owner_id or execution["status"] != "running"
                        or incident["status"] != "EXECUTING" or incident["execution_id"] != execution_id
                        or incident["proposal_id"] != proposal["id"]
                        or target["revision"] != execution["before_revision"]
                        or time.time() >= execution["deadline_at"]):
                    raise ExecutionOwnershipError("Operational claim is no longer dispatchable.")
                self.validate_service_proposal(session, ctx, target, proposal, execution_id)
                self.grounding(session, ctx, proposal["bundle_id"], target)
                approval = self.approvals.verify_approval(ctx, "relay_action", proposal["id"],
                    proposal["payload_hash"], session=session)
                if approval.approval_id != execution["approval"]["approval_id"]:
                    raise InvalidStateTransitionError("Original human receipt differs.")
                expected = {"organization_id": ctx.organization_id, "project_id": ctx.project_id,
                    "actor_id": ctx.actor.actor_id, "owner_id": self.core.authority.owner_id,
                    "execution_id": execution_id, "proposal_id": proposal["id"], "previous_admission_id": execution["previous_admission_id"],
                    "payload_hash": proposal["payload_hash"], "approval_id": approval.approval_id,
                    "target_id": target["id"], "binding_hash": target["binding_hash"],
                    "configuration_hash": target["configuration_hash"], "instance": target["instance"],
                    "generation": execution["before_revision"], "action": "restart_service",
                    "deadline_at": execution["deadline_at"]}
                if execution["admission"]["payload"] != expected:
                    raise InvalidStateTransitionError("Core admission differs from the durable exact claim.")

            receipt = self.targets.dispatch(ctx, target["binding_id"], execution["admission"],
                self.db.evidence_signer.verify, reauthorize)
            execution.update(status="action_completed", action_receipt=receipt,
                after_revision=receipt["output"]["generation"])
            self.put(session, ctx, effect, execution)
            self.audit(session, ctx, "relay.operational.action_completed", execution_id,
                receipt_hash=digest(receipt), target_id=target["id"])

    @staticmethod
    def service_health(target, execution, *, allow_unexecuted=False):
        state, before = target["probe"]["controller"], execution["before_snapshot"]
        if state["instance"] != before["instance"]:
            raise InvalidStateTransitionError("Independent verification found a different service instance.")
        if (allow_unexecuted and state["generation"] == before["generation"]
                and state["last_execution_id"] == before["last_execution_id"] and not target["probe"]["healthy"]):
            return False
        if (state["generation"] != before["generation"] + 1
                or state["last_execution_id"] != execution["id"] or state["child_instance"] != execution["id"]):
            raise InvalidStateTransitionError("Independent verification cannot attribute an unrelated effect.")
        return target["probe"]["healthy"]
