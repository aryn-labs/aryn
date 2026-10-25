"""Authorized source connection lifecycle and bounded local source collection."""

from database.schema import EvidenceConnectionModel, EvidenceReferenceModel
from database.repositories.exceptions import InvalidStateTransitionError
from modules.core.history import HistoryUnverifiedError
from modules.core.records import digest
from packages.contracts.evidence import EvidenceConnection, EvidenceReference
from packages.tool_adapters.evidence import EvidenceBoundaryError


class EvidenceConnections:
    def evidence_binding(self, ctx, connection):
        if self.local_evidence is None:
            raise HistoryUnverifiedError("Trusted local evidence bindings are unavailable.")
        binding = self.local_evidence.binding(ctx, connection["binding_id"])
        if digest(binding) != connection["binding_hash"] or not connection["enabled"]:
            raise HistoryUnverifiedError("Local evidence binding changed or its grant was revoked.")
        return binding

    def register_connection(self, ctx, body):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "tool:register")
            if self.local_evidence is None:
                raise InvalidStateTransitionError("Local evidence bindings are not configured.")
            binding = self.local_evidence.binding(ctx, body.binding_id)
            for row in session.query(EvidenceConnectionModel).filter_by(organization_id=ctx.organization_id,
                    project_id=ctx.project_id).all():
                _, connection = self.get(session, EvidenceConnectionModel, ctx, row.id)
                if connection["binding_id"] == body.binding_id:
                    raise InvalidStateTransitionError("Local evidence binding is already registered.")
            binding_hash = digest(binding)
            _, connection = self.add(session, ctx, EvidenceConnectionModel, EvidenceConnection, "source_connection",
                binding_id=body.binding_id, binding_hash=binding_hash, name=self.clean(body.name),
                kind=binding["kind"], enabled=True, revision=1, file_keys=list(binding["files"]),
                configuration_hash=digest({"binding_hash": binding_hash, "enabled": True, "revision": 1}))
            self.audit(session, ctx, "brief.connection.registered", connection["id"], binding_hash=binding_hash)
            self.authorize(session, ctx, "tool:register")
            return connection

    def grant_connection(self, ctx, identifier, body):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "tool:register")
            row, connection = self.get(session, EvidenceConnectionModel, ctx, identifier, True)
            if connection["configuration_hash"] != body.expected_configuration_hash:
                raise InvalidStateTransitionError("Source connection configuration changed.")
            connection.update(enabled=body.enabled, revision=connection["revision"] + 1)
            connection["configuration_hash"] = digest({"binding_hash": connection["binding_hash"],
                "enabled": connection["enabled"], "revision": connection["revision"]})
            self.put(session, ctx, row, connection)
            self.audit(session, ctx, "brief.connection.grant_changed", identifier,
                enabled=connection["enabled"], configuration_hash=connection["configuration_hash"])
            self.authorize(session, ctx, "tool:register")
            return connection

    def collect(self, ctx, body):
        with self.db.session(write=True) as session:
            self.authorize(session, ctx, "version:create")
            _, connection = self.get(session, EvidenceConnectionModel, ctx, body.connection_id)
            self.evidence_binding(ctx, connection)
            if body.file_key not in connection["file_keys"]:
                raise InvalidStateTransitionError("Source selection is not in the reviewed connection.")
            revision = body.git_revision
            if connection["kind"] == "git" and revision is None:
                revision = self.local_evidence.revision(ctx, connection["binding_id"])
            if connection["kind"] == "file" and revision is not None:
                raise ValueError("File connections do not have a Git revision.")
            _, reference = self.add(session, ctx, EvidenceReferenceModel, EvidenceReference, "source_reference",
                connection_id=connection["id"], binding_hash=connection["binding_hash"],
                configuration_hash=connection["configuration_hash"], kind=connection["kind"],
                file_key=body.file_key, git_revision=revision)
            source = self.ingest_in_session(session, ctx, {"kind": connection["kind"], "id": reference["id"]},
                body.title, max_age_seconds=body.max_age_seconds)
            self.authorize(session, ctx, "version:create")
            return {"reference": reference, "source": source}

    def connection_origin(self, session, ctx, kind, identifier):
        try:
            _, reference = self.get(session, EvidenceReferenceModel, ctx, identifier)
            if reference["kind"] != kind:
                raise HistoryUnverifiedError("Source reference kind differs.")
            _, connection = self.get(session, EvidenceConnectionModel, ctx, reference["connection_id"])
            self.evidence_binding(ctx, connection)
            if (reference["binding_hash"] != connection["binding_hash"]
                    or reference["configuration_hash"] != connection["configuration_hash"]):
                raise HistoryUnverifiedError("Source connection authority changed since capture.")
            content = self.local_evidence.read(ctx, connection["binding_id"], reference["file_key"], reference["git_revision"])
            content.update(reference_id=identifier, connection_id=connection["id"], source_kind=kind,
                configuration_hash=connection["configuration_hash"])
            return content, reference["created_at"], "authorized_file" if kind == "file" else "verified_git_snapshot"
        except (EvidenceBoundaryError, OSError, UnicodeError, ValueError) as exc:
            raise HistoryUnverifiedError("Local source is missing, changed or outside its reviewed boundary.") from exc
