# Conversation CRUD — actual local validation

11 October 2026, working tree `development`, base `5572565`.
No commit/push/merge, branch switch or changes to Home/App Shell/Chat layout.

## Changes

- Core: `modules/core/conversation_metadata.py`, conversation reads/admission,
  explicit own-conversation update/delete permissions and API PATCH/DELETE routes.
- Persistence/contracts: strict `packages/contracts/chat.py`, schema receipts,
  append-only `database/chat_protection.py`, hosted writer guards and additive
  `023_chat_conversation_metadata` migration.
- Frontend: History menu, `ConversationActionDialog`, scoped mutation hook, typed
  contracts/cache updates, local chat menu/dialog styles and id-ID/en-US strings.
  The shared Dialog primitive only gains an optional disabled-close state; its
  existing defaults remain unchanged.
- Tests: new CRUD integration/DB/component/browser cases, PostgreSQL restricted
  writer coverage, migration-head assertions updated to 023. Existing chat E2E
  submissions now wait for actual Send readiness instead of racing capability/
  consent loading. No timeout or security check is relaxed.

The detailed retention, endpoint bodies, duplicate behavior, authorization,
in-flight semantics and limitations are in [the contract report](chat-conversation-management.md).
Deletion restricts Chat access, preserves evidence and does not promise permanent
erasure. No individual message mutation was added.

## Executed checks

| Check | Actual result/evidence |
| --- | --- |
| Backend Ruff | PASS: `ruff check .` |
| Repository hygiene and pinned CI actions | PASS: `scripts/check_repository.py`, `actionlint`, `git diff --check` |
| Secret scan | PASS: Gitleaks on all changed/new source files, no suppressions; `.local/conversation-crud/gitleaks.json` |
| Frontend format/lint/typecheck/build | PASS; build log `.local/conversation-crud-build-final.log` |
| Frontend unit/component tests | 80 passed in the final complete run; 7-case CRUD file also passes independently |
| SQLite/API chat, model and consent contracts | 49 passed before four additional CRUD cases; latest 20-case CRUD file passes |
| CRUD plus schema compatibility | 26 passed; `.local/conversation-crud-targeted-final.xml` |
| Complete offline backend/security regression | 924 passed, 5 skipped, 1 outdated head assertion failed; `.local/conversation-crud-full-backend.xml` |
| Remediation of that full-run failure | Exact failed case updated to 023 and rerun: PASS; `.local/conversation-crud-backend-remediation.xml`. No fresh full-suite exit-zero is claimed |
| Home/App Shell E2E | 90 passed; `.local/conversation-crud-shell-home-e2e.log` |
| Chat/CRUD E2E | 28 passed; `.local/conversation-crud-chat-e2e-final.log` |
| Additional keyboard/focus E2E | 2 passed (one new unique case); `.local/conversation-crud-keyboard-e2e.log` |
| Final UI rerun after pending-dismissal refinement | 3 passed: mobile light rename/delete, inactive deletion/focus and keyboard menus; `.local/conversation-crud-final-ui-e2e.log` |
| PostgreSQL Chat contracts | 25 passed on real PostgreSQL 16.13 with restricted non-owner writer, including all new CRUD cases |
| Complete PostgreSQL regression | 112 passed, zero failures/errors/skips; `.local/conversation-crud-postgresql-final.xml`, 397.73 seconds |

Relevant commands use the existing scripts/toolchain: `npm run lint`,
`npm run typecheck`, `npm run build`, `npm test`, `npm run test:e2e`,
`npm run test:chat:e2e`, `ruff check .`, and
`pytest -m 'not postgresql' --backend-shard=1/1` / `pytest tests/postgresql`.
Local Node CLIs use the existing pinned Node 22.23.3 executable directly.

Follow-up launcher validation found TS2769 in the final pending-deletion test:
Testing Library's `getByRole` does not support an `exact` option. The test now
matches the button's complete accessible name using an anchored regular
expression. A fresh `npm run build` (including `tsc --noEmit`), all 80 frontend
tests, full frontend lint and the changed file's formatting check pass after this correction. The
earlier build result did not cover that final test revision.

Coverage includes title validation/control characters, unchanged-title prevention,
error/input retention, duplicate and stale mutations, owner/user/org/project
isolation, CSRF/origin, durable refresh/reopen, retained signed messages/runs/
budgets/audit, unknown reservations, concurrent duplicate claims, in-flight
rename/delete/settlement, SQL guards, privileged receipt rollback rejection,
additive populated upgrade and populated downgrade refusal. Browser tests use
real API/Core with the explicitly isolated fixture runtime, never fake product AI.
They also exercise actual CSRF rejection and a lost server acknowledgement.

## Visual and accessibility checks

Rename/delete dialogs were exercised at 1920, 1440, 1024, 768 and 390px in dark
and light modes. Each matrix case checks horizontal overflow and Axe WCAG
2A/2AA/2.1AA violations (none). Keyboard testing covers menu ArrowDown/End/Enter,
input focus, Tab containment, Escape, confirmation Cancel focus and restoration
to the menu trigger or surviving History heading. Active deletion returns Home;
other deletion leaves the active conversation untouched. English actions are
verified through the persisted Settings preference.

Actual screenshots, manually inspected on desktop and mobile, are under ignored
`.local/conversation-crud/rename-{width}-{theme}.png` and
`delete-{width}-{theme}.png`. Only menu/dialog additions affect presentation;
App Shell, Home and the conversation layout retain their existing design.

## Database test environment

Docker's local engine was unavailable. An isolated, loopback-only PostgreSQL
16.13 instance was provisioned under `.local/conversation-crud/postgres` using
[the Windows binaries linked by PostgreSQL](https://www.postgresql.org/download/windows/).
The official EDB archive SHA-256 is
`9b4c7a1bc31147b5b2ba59178d0eef86c16181d54a20177192b387dff20f00a9`.
No service installation or application database/configuration change was made.
The test server uses SCRAM, a random transient admin password and separate
migration-owner/restricted-writer roles per disposable test database.

Initial initdb inherited Asia/Bangkok. All 25 Chat cases passed, but existing
approval signatures in unrelated domain tests failed when PostgreSQL returned
their timestamps with a +07 offset. The temporary test instance was configured
to UTC, matching the CI container, and the entire 112-test PostgreSQL suite was
rerun. No approval code, signature validation or permissions were weakened.
The UTC-configured full rerun passed all 112 cases. The helper stopped its own PostgreSQL instance after execution. Production
Studio/Hermes/9Router processes are untouched.

CI configuration is unchanged and no new remote CI run was triggered: these are
local working-tree results, not a claim about a newly pushed commit.

No remaining Conversation CRUD blocker was found. Permanent erasure/retention
automation remains a separate capability, not a promise of the Delete action.
The running Studio process must be restarted to load the new API code; its
existing startup migration applies 023. Validation used disposable databases
and did not delete any customer conversation from the application database.
