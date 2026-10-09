# Studio architecture decisions

## Executable workflows and artifact review

Audit baseline: `ba2140bc396a6dbebef76d510d8288309eafa847`, development equal to remote and dependency CI 37883814142 completed-success. Supplied PRD v1.2 / Prompt 03 authorize this delivery; absent normative PDFs are not claimed reviewed. Current results and source/CI references are in [delivery evidence](studio-redesign-progress.md). Earlier decisions below retain their historical context.

Use strict typed graph contracts and server admission, with a shared draft revision CAS and immutable graph version/hash independent of positions. Start, Agent, Condition, Handoff, Review and End have bounded typed ports. Conditions use an allowlisted deterministic predicate. One selected path executes sequentially, with every path reaching human review before End. No expression interpreter, general code node or independent scheduler is introduced.

WorkflowExecutor reuses the existing RunCoordinator authority, owner fence, exact version claims, reservations, deadlines and measured settlement. Persist the typed TaskExecution vector inside the signed WorkflowRun checkpoint. The trusted claim callback captures the Core run ID in the same claim/reservation transaction before inference, without holding a transaction during inference. Trusted workflow/node references enter the signed Core assignment provenance, enabling actual Console/Operations reverse links. Indexed status mirrors are verified against signed payloads; startup recovery queries active runs rather than scanning completed history.

Store artifacts as bounded database blobs through existing Local SQLite / Hosted PostgreSQL configuration. Manifest signatures, independent protected commitments, length/digest and MIME/schema checks bind scope and lineage. Immutable artifact/version/review SQL guards extend existing restricted-writer prerequisites. Migration 018 is additive after 017/016/015 and refuses a populated downgrade before dropping any table. See [ER/state diagrams, role provisioning and threat review](workflow-execution-contracts.md).

Research and Content dispatch two distinct pinned governed agents. Website staging executes `static-document-v1`, an explicit renderer that escapes text into a fixed inert HTML skeleton. Its result is a real third bounded task. Each consumer verifies its actual predecessor artifact; a missing handoff fails without dispatch. Preview uses opaque `iframe sandbox=""` and restrictive CSP; no same-origin/script/resource privileges are granted. Downloads verify integrity and return generated attachment names, nosniff and no-store.

Human review persists waiting state and an immutable unique exact-hash decision with reviewer/reason/timestamp and atomic audit. Accept completes End; reject preserves artifact/history. Idempotent Start/review cannot execute or commit twice. The editor retains Start request identity in memory after a lost response so an explicit retry returns the existing run; a received result clears it for a deliberate new run. No automatic browser retry or prompt persistence is added. Restart and unresolved cancellation/timeout preserve outcome_unknown and held consumption, with no automatic retry. Existing operator reconciliation remains required; this delivery does not claim an unknown-effect repair API or provider monetary hard caps.

React Flow is an editable graph surface; the complete structured editor provides keyboard access to the same graph. Explicit save/freeze/validate are distinct. Dirty edits survive concurrent refetch/CAS conflict and have deliberate reload/restore plus route/project/document guards. Lists/detail are scoped and bounded. Record-reference continuation is resolved in the current scope on each request; it is not a bearer authorization token.

Preview accessibility is audited from its exact serialized DOM in an isolated test page with original CSP and all network blocked, because Chromium's disabled-script sandbox also blocks axe timers. The actual product frame is separately asserted opaque/sandboxed and visible. All tagged axe rules remain enabled; no production sandbox or accessibility rule is relaxed. Full WCAG conformance and external penetration certification are not inferred from these automated checks.

Residual product boundaries are deliberate: manual sequential execution, one terminal review, bounded text envelopes and one inert renderer. Brief/Relay, recurrence scheduler, general parallel DAG execution, public website publication and hosted production deployment remain outside this delivery.

## Historical Agent editing and manual operations


Audit source for the current delivery: `40df9d1f894b257df3a277c4623466d6d03541dc` (development equals remote; ARYN Quality 37837626257 success). Existing canonical format 3, signed Bench/regression/baseline, approval, activation history and captured execution remain authoritative.

Persist one shared scoped working copy per blueprint with generation conflict detection. Explicit candidate creation passes the saved exact definition to the existing Factory service within the same Core transaction; editor saves and dragging do not create versions. Discard is generation guarded. Published versions are inspected read-only and may seed a separate working copy, never be mutated. Layout positions/viewport are stored in a separate per-actor table, with their own generation and no prompt fields; they never enter AgentVersion canonical payloads. No editor data is stored in localStorage.

Reuse bounded resource reads for registries/history/audit, and add a scoped lifecycle projection that loads only a bounded selection and its actual governance dependencies. Keep legacy snapshot compatibility. An execution detail binds to the captured version, not the assignment's mutable current pointer. Tool grants and native scheduling remain unavailable; cost limits are policies, not provider hard-cap guarantees. Future workflow/artifact/Brief/Relay/scheduler contracts remain design-only.

Implementation source: `80bac7dfa59bd27a6ac1e7e5493f11285b625b2d`. Current source workflow: [ARYN Quality 37835952417](https://github.com/aryn-labs/aryn/actions/runs/37835952417); terminal completed/success, 14/14 jobs; evidence-only closure is verified separately before the final report. Subsequent evidence-only commits do not change this source.
Source baseline: `3a8ddb69b855ea37d1a33721c6c57a02f14ad881`. 9 October 2026.

Unparsed JSON is retained only in editor memory, participates in dirty state, blocks candidate/save even when its section is hidden, and survives section/form changes plus explicit reload/restore. RouterProvider/useBlocker guards in-app links and browser Back/Forward; beforeunload covers document departure, and project changes retain the explicit scope guard. Validation does not silently replace incomplete input with the previous valid canonical value. The complete definition remains the only persisted working-copy payload.

## Historical workspace decisions

The preceding workspace source/CI reference is historical. Current implementation source, exact-SHA CI and residuals are recorded in [delivery evidence](studio-redesign-progress.md).

## Workspace reads and authority

Keep the legacy signed snapshot contract for existing lifecycle pages. Overview and Projects consume bounded, scoped read models. Inventory counts describe database records; recorded publication/assignment labels are explicitly separate from verified governance eligibility. Verify evidence only for the bounded records presented as verified. Detail requests retain existing Core evidence verification. No read response grants publication or execution rights. Current Core membership/session is checked on reads and in every mutation transaction.

Cursor pagination orders by timestamp plus unique ID, binds organization/project/resource/filter/order, authenticates the cursor and limits pages to 100. Cache is isolated by organization and project; AbortSignal cancellation and selection reset prevent stale switch races. Add indexes only for measured/scoped read paths. No change to history signatures, runtime routes, approval rules, reservations or captured claims.

## Projects and divisions

Projects are existing authoritative Core objects; this delivery provides list/detail without inventing organization management. Division is a project-owned organizational grouping, not a role/membership store. A forward migration after 015 creates divisions without backfilling assignment history. Human organization admins manage division records through a narrow Core permission. Creation/edit is audited in the same transaction; edits require the expected generation. Assignment linkage remains existing immutable provenance and is not rewritten.

## Subsequent contracts

- Agent Builder decision is now implemented by AgentDraft/AgentEditor and migration 017: editable working copy with generation and explicit save, separate candidate creation and per-actor layout. Published payloads/exact-hash approvals remain unchanged; empty tool grants are enforced. Remaining contracts below are design only.
- WorkflowDefinition owns the editable typed graph; WorkflowVersion pins validated graph plus exact AgentVersions. WorkflowRun/TaskExecution own durable execution states and checkpoints under the existing Core owner/fence, reservation and idempotency authority. Unknown outcomes cannot be retried automatically. No general code execution nodes.
- Artifact has scoped immutable storage reference, digest, MIME/size/validation and run/task lineage. Deliverable adds hash-bound human review. Safe download authorizes Core scope; HTML preview is inert or separated/sandboxed. No host filesystem reference is exposed.
- Brief EvidenceBundle retains timestamped source references, digest verification and support/conflict/neutral relations. Empty or missing evidence abstains. Removed/tampered evidence cannot claim support.
- Relay Incident/Proposal use deterministic dedup and legal transitions, evidence references and exact-payload Core approval. Only an explicitly allowlisted disposable remediation adapter may execute. Verified health after action is required for recovery. Bench capsules use safe replay adapters.
- Automations persist recurrence/timezone/occurrence identity, missed/overlap policy, budget and owner in Core. A single Core scheduler authority admits work; Hermes native cron/jobs remain forbidden. Entitlement/payment/installer/provider/production work stays external.

Workflow/artifact/Brief/Relay/scheduler decisions introduce no empty services, migrations or enabled actions. Their implementation owners remain packages 03–05 in traceability. AgentEditor migration adds necessary editor state only, with no new authority.
