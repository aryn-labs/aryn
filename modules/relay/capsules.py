"""Immutable operational incident checkpoints, including unresolved outcomes."""

import hashlib
from database.schema import (
    IncidentCapsuleModel, RelayIncidentModel, DemoObservationModel, RelaySignalModel, RelayInvestigationModel, RelayProposalModel,
    RelayExecutionModel, RelayVerificationModel, EvidenceBundleModel, EvidenceSourceModel,
)
from database.repositories.exceptions import InvalidStateTransitionError
from modules.core.records import digest, identity, now
from modules.core.history import HistoryUnverifiedError
from packages.contracts.operational import ServiceCapsule, ServiceProposal, ServiceExecution, ServiceVerification, ServiceObservation


class OperationalCapsules:
    def signed_checkpoint(self, session, ctx, cls, identifier):
        row, payload = self.get(session, cls, ctx, identifier)
        return {"record_kind": cls.__tablename__, "payload": payload, "attestation": row.attestation}

    def capture_operational_capsule(self, session, ctx, incident, proposal, execution, verification=None):
        outcome = incident["status"]
        if outcome not in {"RECOVERED", "DEGRADED", "OUTCOME_UNKNOWN"}:
            raise InvalidStateTransitionError("Only a settled or explicitly unresolved operational checkpoint can be captured.")
        investigation = session.query(RelayInvestigationModel).filter_by(organization_id=ctx.organization_id,
            project_id=ctx.project_id, incident_id=incident["id"], bundle_id=proposal["bundle_id"]).order_by(
            RelayInvestigationModel.created_at.desc(), RelayInvestigationModel.id.desc()).first()
        if investigation is None:
            raise HistoryUnverifiedError("The operational investigation checkpoint is missing.")
        lineage = {name: self.signed_checkpoint(session, ctx, cls, identifier) for name, cls, identifier in (
            ("incident", RelayIncidentModel, incident["id"]),
            ("signal", RelaySignalModel, incident["signal_id"]),
            ("investigation", RelayInvestigationModel, investigation.id),
            ("proposal", RelayProposalModel, proposal["id"]),
            ("execution", RelayExecutionModel, execution["id"]),
            ("bundle", EvidenceBundleModel, proposal["bundle_id"]),
        )}
        lineage["verification"] = self.signed_checkpoint(session, ctx, RelayVerificationModel, verification["id"]) if verification else None
        lineage["verification_observation"] = self.signed_checkpoint(session, ctx, DemoObservationModel,
            verification["observation_id"]) if verification else None
        lineage["approval_identity"] = execution["approval"]
        evidence = []
        for identifier in lineage["bundle"]["payload"]["source_ids"]:
            row, source = self.get(session, EvidenceSourceModel, ctx, identifier)
            content = bytes(row.blob)
            if len(content) != source["length"] or hashlib.sha256(content).hexdigest() != source["digest"]:
                raise HistoryUnverifiedError("Captured source bytes differ from signed evidence.")
            evidence.append({"source": {"record_kind": row.__tablename__, "payload": source,
                "attestation": row.attestation}, "content": content.decode("utf-8")})
        if self.clean({"lineage": lineage, "evidence": evidence}) != {"lineage": lineage, "evidence": evidence}:
            raise HistoryUnverifiedError("Protected credentials cannot be included in a capsule.")
        identifier = identity("incident_capsule")
        _, capsule = self.add(session, ctx, IncidentCapsuleModel, ServiceCapsule, "incident_capsule", id=identifier,
            incident_id=incident["id"], incident_revision=incident["revision"],
            bundle_id=proposal["bundle_id"], bundle_digest=proposal["bundle_digest"],
            proposal_id=proposal["id"], proposal_hash=proposal["payload_hash"],
            verification_id=verification["id"] if verification else None, outcome=outcome,
            recovered=None if outcome == "OUTCOME_UNKNOWN" else outcome == "RECOVERED",
            failure_reason=None if outcome == "RECOVERED" else execution["error_code"] or "independent_health_failed",
            snapshot=execution["before_snapshot"], lineage=lineage, evidence=evidence,
            scenario_candidate={"source_kind": "capsule", "source_id": identifier, "requires_human_review": True,
                "expected_behavior": "Abstain on unresolved effects; require independent health evidence before declaring recovery.",
                "forbidden_actions": ["live_recovery", "host_execution", "network", "credential_access"]}, digest="0" * 64)
        self.brief.link(session, ctx, capsule["bundle_id"], "capsule", capsule["id"])
        return capsule

    def validate_operational_capsule(self, session, ctx, capsule):
        ServiceCapsule.model_validate(capsule)
        if capsule["digest"] != digest({key: value for key, value in capsule.items() if key != "digest"}):
            raise HistoryUnverifiedError("Operational capsule digest differs.")
        classes = {"incident": RelayIncidentModel, "signal": RelaySignalModel, "investigation": RelayInvestigationModel,
            "proposal": RelayProposalModel, "execution": RelayExecutionModel, "bundle": EvidenceBundleModel,
            "verification": RelayVerificationModel, "verification_observation": DemoObservationModel}
        for name, cls in classes.items():
            envelope = capsule["lineage"].get(name)
            if name in {"verification", "verification_observation"} and envelope is None and capsule["verification_id"] is None:
                continue
            if (not isinstance(envelope, dict) or envelope.get("record_kind") != cls.__tablename__
                    or not isinstance(envelope.get("payload"), dict)):
                raise HistoryUnverifiedError("Capsule checkpoint kind differs.")
            payload = envelope["payload"]
            if ((payload.get("organization_id"), payload.get("project_id")) != (ctx.organization_id, ctx.project_id)
                    or not self.db.evidence_signer.verify(cls.__tablename__, payload, envelope.get("attestation", ""))):
                raise HistoryUnverifiedError("Capsule checkpoint scope or signature differs.")
            _, current = self.get(session, cls, ctx, payload["id"])
            # A historical execution checkpoint may later be reconciled. Its
            # immutable capsule authenticates the original signature while the
            # current protected record must retain the exact invocation identity.
            if cls is RelayIncidentModel:
                keys = ("id", "organization_id", "project_id", "target_id", "signal_id", "dedup_key", "created_at")
                if any(current.get(key) != payload.get(key) for key in keys) or current["revision"] < payload["revision"]:
                    raise HistoryUnverifiedError("Captured incident identity changed.")
            elif cls is RelayExecutionModel:
                keys = ("id", "organization_id", "project_id", "target_id", "proposal_id", "payload_hash",
                    "before_revision", "before_snapshot", "approval", "actor_id", "idempotency_key", "previous_admission_id")
                if any(current.get(key) != payload.get(key) for key in keys):
                    raise HistoryUnverifiedError("Captured execution identity changed.")
            elif current != payload:
                raise HistoryUnverifiedError("An immutable capsule checkpoint changed.")
        lineage = capsule["lineage"]
        incident, signal, investigation, proposal, execution, bundle = (
            lineage[name]["payload"] for name in ("incident", "signal", "investigation", "proposal", "execution", "bundle"))
        ServiceProposal.model_validate(proposal)
        ServiceExecution.model_validate(execution)
        if (incident["id"] != capsule["incident_id"] or incident["revision"] != capsule["incident_revision"]
                or incident["status"] != capsule["outcome"] or incident["signal_id"] != signal["id"]
                or any(item["target_id"] != incident["target_id"] for item in (signal, proposal, execution))
                or any(item["incident_id"] != incident["id"] for item in (investigation, proposal, execution))
                or incident["bundle_id"] != bundle["id"] or investigation["bundle_id"] != bundle["id"]
                or proposal["bundle_id"] != bundle["id"] or proposal["bundle_digest"] != bundle["digest"]
                or incident["proposal_id"] != proposal["id"] or incident["execution_id"] != execution["id"]
                or execution["payload_hash"] != proposal["payload_hash"]
                or execution["before_revision"] != proposal["target_revision"]
                or proposal["payload_hash"] != digest({key: value for key, value in proposal.items() if key != "payload_hash"})
                or execution["approval"]["payload_hash"] != proposal["payload_hash"]
                or not self.db.evidence_signer.verify("relay_operational_action", execution["admission"]["payload"],
                    execution["admission"].get("attestation", ""))):
            raise HistoryUnverifiedError("Capsule incident, evidence, approval or admission lineage differs.")
        if capsule["verification_id"] is not None:
            verification, observation = lineage["verification"]["payload"], lineage["verification_observation"]["payload"]
            ServiceVerification.model_validate(verification)
            ServiceObservation.model_validate(observation)
            if (verification["id"] != capsule["verification_id"] or incident["verification_id"] != verification["id"]
                    or verification["execution_id"] != execution["id"] or verification["incident_id"] != incident["id"]
                    or verification["target_id"] != incident["target_id"] or verification["observation_id"] != observation["id"]
                    or observation["target_id"] != incident["target_id"] or observation["reason"] != "verification"
                    or verification["target_revision"] != observation["target_revision"]
                    or verification["recovered"] != observation["healthy"]
                    or observation["configuration_hash"] != proposal["configuration_hash"]
                    or observation["binding_hash"] != proposal["binding_hash"]
                    or verification["digest"] != digest({key: value for key, value in verification.items() if key != "digest"})):
                raise HistoryUnverifiedError("Capsule independent verification lineage differs.")
        expected_recovered = None if capsule["outcome"] == "OUTCOME_UNKNOWN" else capsule["outcome"] == "RECOVERED"
        if (capsule["recovered"] is not expected_recovered
                or lineage["execution"]["payload"]["status"] not in {
                    "RECOVERED": {"verified"}, "DEGRADED": {"health_failed", "denied"}, "OUTCOME_UNKNOWN": {"outcome_unknown"}
                }[capsule["outcome"]]
                or capsule["recovered"] is True and (lineage.get("verification") is None
                    or lineage["verification"]["payload"]["recovered"] is not True)):
            raise HistoryUnverifiedError("Capsule outcome is not supported by its captured execution and verification.")
        if (lineage["proposal"]["payload"]["id"] != capsule["proposal_id"]
                or lineage["proposal"]["payload"]["payload_hash"] != capsule["proposal_hash"]
                or lineage["execution"]["payload"]["before_snapshot"] != capsule["snapshot"]
                or lineage["execution"]["payload"]["proposal_id"] != capsule["proposal_id"]
                or lineage["investigation"]["payload"]["incident_id"] != capsule["incident_id"]
                or lineage["bundle"]["payload"]["id"] != capsule["bundle_id"]
                or lineage["bundle"]["payload"]["digest"] != capsule["bundle_digest"]
                or lineage["approval_identity"] != lineage["execution"]["payload"]["approval"]):
            raise HistoryUnverifiedError("Capsule lineage differs from its exact invocation.")
        ids = []
        for captured in capsule["evidence"]:
            envelope, raw = captured["source"], captured["content"].encode("utf-8")
            source = envelope["payload"]
            row, stored = self.get(session, EvidenceSourceModel, ctx, source["id"])
            if (envelope["record_kind"] != EvidenceSourceModel.__tablename__ or stored != source
                    or row.attestation != envelope["attestation"] or raw != bytes(row.blob)
                    or len(raw) != source["length"] or hashlib.sha256(raw).hexdigest() != source["digest"]
                    or source["digest"] != lineage["bundle"]["payload"]["source_digests"].get(source["id"])):
                raise HistoryUnverifiedError("Capsule source snapshot is unverified.")
            ids.append(source["id"])
        if ids != lineage["bundle"]["payload"]["source_ids"]:
            raise HistoryUnverifiedError("Capsule source coverage differs.")
        return capsule

    def capture_capsule(self, ctx, identifier, body):
        with self.db.session(write=True) as session:
            row, incident, _, target = self.incident_for_mutation(session, ctx, identifier, body.expected_revision, refresh=False)
            if target.get("target_kind") != "isolated_service" or not incident["execution_id"]:
                raise InvalidStateTransitionError("Operational capsules require a real admitted execution checkpoint.")
            _, proposal = self.get(session, RelayProposalModel, ctx, incident["proposal_id"])
            _, execution = self.get(session, RelayExecutionModel, ctx, incident["execution_id"])
            verification = self.get(session, RelayVerificationModel, ctx, incident["verification_id"])[1] if incident["verification_id"] else None
            capsule = self.capture_operational_capsule(session, ctx, incident, proposal, execution, verification)
            incident.update(capsule_id=capsule["id"], revision=incident["revision"] + 1, updated_at=now())
            self.put(session, ctx, row, incident)
            self.event(session, ctx, incident, "capsule.captured", incident["status"], capsule["id"])
            self.authorize(session, ctx, "run:create")
            return self.detail_in_session(session, ctx, identifier)
