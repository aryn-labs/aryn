# Studio architecture decisions

Source baseline: `3a8ddb69b855ea37d1a33721c6c57a02f14ad881`. 9 October 2026.

## Workspace reads and authority

Keep the legacy signed snapshot contract for existing lifecycle pages. Overview and Projects consume bounded, scoped read models. Inventory counts describe database records; recorded publication/assignment labels are explicitly separate from verified governance eligibility. Verify evidence only for the bounded records presented as verified. Detail requests retain existing Core evidence verification. No read response grants publication or execution rights. Current Core membership/session is checked on reads and in every mutation transaction.

Cursor pagination orders by timestamp plus unique ID, binds organization/project/resource/filter/order, authenticates the cursor and limits pages to 100. Cache is isolated by organization and project; AbortSignal cancellation and selection reset prevent stale switch races. Add indexes only for measured/scoped read paths. No change to history signatures, runtime routes, approval rules, reservations or captured claims.

## Projects and divisions

Projects are existing authoritative Core objects; this delivery provides list/detail without inventing organization management. Division is a project-owned organizational grouping, not a role/membership store. A forward migration after 015 creates divisions without backfilling assignment history. Human organization admins manage division records through a narrow Core permission. Creation/edit is audited in the same transaction; edits require the expected generation. Assignment linkage remains existing immutable provenance and is not rewritten.

## Future contracts (design only)

- Agent Builder: editable working copy with generation and explicit save creates a new immutable canonical AgentVersion. Published payloads and exact-hash approvals remain unchanged. Canvas positions/viewport belong in separate project/user layout metadata excluded from signed canonical hashes. Tool grants remain empty.
- WorkflowDefinition owns the editable typed graph; WorkflowVersion pins validated graph plus exact AgentVersions. WorkflowRun/TaskExecution own durable execution states and checkpoints under the existing Core owner/fence, reservation and idempotency authority. Unknown outcomes cannot be retried automatically. No general code execution nodes.
- Artifact has scoped immutable storage reference, digest, MIME/size/validation and run/task lineage. Deliverable adds hash-bound human review. Safe download authorizes Core scope; HTML preview is inert or separated/sandboxed. No host filesystem reference is exposed.
- Brief EvidenceBundle retains timestamped source references, digest verification and support/conflict/neutral relations. Empty or missing evidence abstains. Removed/tampered evidence cannot claim support.
- Relay Incident/Proposal use deterministic dedup and legal transitions, evidence references and exact-payload Core approval. Only an explicitly allowlisted disposable remediation adapter may execute. Verified health after action is required for recovery. Bench capsules use safe replay adapters.
- Automations persist recurrence/timezone/occurrence identity, missed/overlap policy, budget and owner in Core. A single Core scheduler authority admits work; Hermes native cron/jobs remain forbidden. Entitlement/payment/installer/provider/production work stays external.

These future decisions introduce no empty services, migrations or enabled actions. Their implementation owners are packages 02–05 in traceability.
