# Conversation rename and deletion

These changes extend the existing text-only Chat service. Home, App Shell,
the chat layout, turn admission and provider consent keep their existing behavior.
No endpoint changes individual messages or dispatches inference for metadata edits.

## Retention and governance audit

`chat_turns` reference both `chat_conversations` and `run_states` with foreign keys
without delete cascades. Signed turn evidence binds the input, scope, sequence,
idempotency claim and Core run ID. Core run claims/results hold execution
attestations. The actual usage ledger is `usage_budgets` plus each run's reservation,
measured usage and settlement state, rather than a separate chat billing table.
Immutable, authenticated `audit_events` retain admission/execution provenance.
Erasing turns or runs would break evidence verification and consumption accounting.

**Delete removes access through the Chat API, not stored evidence.** Core appends a signed, irreversible
conversation tombstone. History and Home's Continue Working exclude it. Read,
rename, follow-up and reuse of the original create key cannot reopen it. There is
no restore API. Authenticated duplicate DELETE requests receive the same current
acknowledgement and do not duplicate receipts/audit events. Ownership and current
permissions are rechecked even for duplicates. Foreign IDs return 404 without
disclosing the owner or content.

Conversation records, all messages, run prompts/results, signed evidence, budget
ledger entries, metadata changes, immutable audit and existing backups remain
retained. **No expiration period, permanent erasure or automated purge is added.**
Existing authorized Core/run/audit inspection can still expose retained inputs,
outputs and provenance under its existing RBAC. Deletion does not revoke that
governance visibility or erase previously transmitted provider data.
The UI explicitly discloses this before confirmation. A separate authorized
retention/erasure policy and evidence-preserving design are required for permanent
deletion; this action must not be described as that capability.

Delete and follow-up admission serialize on the same conversation row. A run
admitted before deletion may finish and incur measured charges; deletion is not
runtime cancellation. Core continues to settle usage normally. Unknown outcomes
retain reservations and are never automatically retried/refunded. Admissions
ordered after deletion are rejected. The browser cancels stale reads and removes
cached content after the server acknowledges deletion.

## Additive API contracts

Prefix: `/api/projects/{project_id}/chat/conversations/{conversation_id}`.

| Method | Strict body | Result |
| --- | --- | --- |
| PATCH | `title`, `expected_metadata_revision`, `idempotency_key` | Verified current conversation metadata |
| DELETE | `expected_metadata_revision`, `idempotency_key` | Verified current metadata with `deleted: true` |

Titles are strings trimmed to 1–120 characters; multiline, control and invisible
format characters are rejected. Unknown body fields, coerced revisions, negative
revisions and invalid request keys are rejected. Keys use the existing 16–128
alphanumeric/underscore/hyphen contract. A changed reuse is 409. Mutation revisions
are separate from message `revision`, preserving all multi-turn contracts. Stale
metadata revisions are 409; exact retries return the current verified projection.
A new DELETE key for an already deleted own conversation is also a no-op success.

Response fields: `id`, `organization_id`, `project_id`, `title`,
`metadata_revision`, `deleted`. Existing GET and history responses additionally
include `metadata_revision`, `can_rename` and `can_delete`. These actions are
derived by Core, not inferred from frontend roles. Admin/operator may manage their
own conversations with `chat:update`/`chat:delete`; viewers cannot mutate. Existing
human-session and `chat:read`/`run:read` checks also apply. Organization admins do
not gain access to another person's private conversations.

Both endpoints use the existing session, same-origin/CSRF middleware, trusted
identity binder, current RBAC and tenant/project scope. Metadata idempotency is
scoped by person/organization/project and bound to method, resource and body.
Core persists the receipt and audit in one governed transaction; acknowledgement
is returned only after the independent freshness commitment is finalized.

## Persistence and client behavior

Additive migration `023_chat_conversation_metadata` creates
`chat_conversation_changes`. It never rewrites existing conversations, messages,
runs, budgets or consent. SQLite UPDATE/DELETE/REPLACE and PostgreSQL
UPDATE/DELETE/TRUNCATE are guarded. Hosted deployment must revoke those privileges
from its non-owner writer; the existing readiness guard checks the new table too.
A populated downgrade is refused so tombstones cannot be discarded.

Each signed metadata receipt has an independent Core freshness head. Deleting or
replaying a receipt via privileged database corruption fails closed rather than
resurrecting the conversation. Existing conversations start at metadata revision
zero, without synthetic backfilled evidence. Unchanged turn signatures and run
claims remain the authority for transcript reads and context construction.

History's existing drawer adds accessible three-dot menus and rename/delete
dialogs in Indonesian and English. Confirmation initially focuses Cancel.
Rename preserves input after errors; unknown acknowledgements permit only the
exact original retry with its original key. Scoped TanStack Query caches for
History, Continue Working and active detail are canceled/updated/invalidated;
deleting the active chat navigates Home. Deleting another chat keeps the active
conversation and messages intact. Deleted pagination anchors remain usable solely
as scoped cursors, not readable conversation resources.

Validation results and environment limitations are recorded separately in
`chat-conversation-management-validation.md` after execution.
