# ARYN Studio — Home, Chat and personal settings

Local `development` working tree, 11 October 2026. Existing App Shell retained.
No commit, push, merge or main change. Real multi-turn AI works; full acceptance
is still limited by PostgreSQL environment and gateway evidence, documented in
[actual validation](../apps/web/VALIDATION.md).

## Presentation and state

Home uses semantic surfaces (`#0A1119`, `#15212B`, `#192632`, accent `#62DCCB`)
with corresponding light tokens. Its content maximum is 1320px, desktop padding
28px and section spacing 24px. Local-time greeting replaces repeated project
headings. The reusable composer contains input, actual model choice and Send;
it has one focus indicator, bounded six-line growth, no manual resize and correct
Enter/Shift+Enter/IME behavior. Short disabled reasons can be expanded.

New, Active and Important Issues derive from actual scoped inventories, own chat
history and effective permissions. Unknown inventories are never an empty project.
Attention is capped at three actionable inspection links; work and activity at four.
Connect Apps is honestly unavailable. Agent/Workflow quick actions open explicit
review/handoff only. Chat never creates, publishes, approves, grants, assigns or
executes an agent from model text. No production sample data is supplied.

Chat retains the shell and uses an 820px reading column, right user bubbles at
up to 70%, plain left assistant output, line-height 1.6, pinned header/input,
message-only scrolling and optional history drawer. Raw HTML, remote images and
unsafe URLs are blocked in Markdown. Copy is nonintrusive. Auto-scroll occurs
only when the reader was already near the bottom. Persisted status drives loading
and error presentation; neither streaming nor Stop is claimed without a contract.

UI translations use i18next/react-i18next, default id-ID and alternative en-US.
Settings is the only language control. The preference is stored per authenticated
person and organization; endpoint/cache authorization remains project-scoped.
Dates follow locale; customer names/messages and brand names are not translated.
The server system policy does not force model response language to the UI locale.

## API contracts

All routes share `/api/projects/{project_id}/chat`, existing authenticated sessions,
same-origin cookies, CSRF for mutations, strict bodies and sanitized errors.

| Method | Suffix | Result |
| --- | --- | --- |
| GET | `/capability` | Exact listed model candidates/readiness, effective permission and supported features |
| GET | `/conversations?before={id}` | Own-user scoped history, maximum 30 and next cursor |
| GET | `/conversations/{id}` | Verified persisted transcript, revision, model and Core state |
| POST | `/conversations` | 202 acknowledgement of admitted first turn with persistent ID |
| POST | `/conversations/{id}/messages` | 202 acknowledgement of admitted follow-up |
| GET | `/provider-consent` | Current model/provider-policy projections and verified personal consent |
| POST | `/provider-consent` | Grant current listed model's exact transfer policy; signed Core receipt |
| DELETE | `/provider-consent/{provider_id}` | Revoke own scoped provider consent and record audit evidence |
| GET | `/preferences` | Own organization/person locale, default id-ID |
| PATCH | `/preferences` | Persist locale enum id-ID or en-US |

Turn body: trimmed `message` 1–4000 characters, exact `model`, `idempotency_key`
16–128 characters and integer `expected_revision`. Legacy `allow_remote_model`
remains a strict boolean for wire compatibility only; it never grants authority.
System messages, actor IDs, roles, runtime sessions, grants, tools and unknown
fields are rejected. Consent body contains only `model` and the server's 64-hex
`policy`. Preference body contains only the supported `locale` enum.

Human read requires chat:read/run:read; send/grant requires chat:create/run:create
and current organization/project membership. History and receipts are actor-bound.
Every async boundary revalidates authority. Session response schemas verify scope;
queries include person, organization and project, consume AbortSignal and remount
private mutation state on scope changes. An immediate in-flight latch prevents
same-render duplicate sends. Unknown transport retry preserves the exact original
request/key; no automatic fresh-key resend or model substitution occurs.

## Core, persistence and consent

**UI → ARYN API → Core Conversations/RunCoordinator → Hermes Runtime Adapter
→ confined native Hermes → configured 9Router/model.** The browser never calls
provider/Hermes directly and never receives gateway credentials.

Core persists a signed ordered transcript linked to attested runs. System policy
is server-owned and separate from the bounded transcript sent as user data.
Native session identity derives from scoped server idempotency; client session
administration and host tools are unavailable. Core admission reserves budget,
audits exact model and settles measured usage. Prior answers must pass signed
history/run verification before becoming follow-up context. Revision serializes
turns; identical duplicates return stored acknowledgement, altered reuse fails.
Account/project rate limit is 12 turns/minute; context is bounded to 16KB with
existing token/turn/budget policy. Unknown outcomes retain reservations, are not
silently retried and prevent unsafe continuation.

Unknown listed candidates can be verified on explicit send by a bounded, metered
Core readiness probe. Valid consent is required BEFORE the probe, not merely
before sending user text. A completed exact-model attestation establishes readiness
for 60 seconds. Opening Home, Settings or history never dispatches inference.

First-use consent discloses transcript transfer, potential provider charges and
metered checks, with no enabled tools. Core stores actor/org/project/provider/policy,
grant/revoke times and a signature with an independent freshness head. Tampering,
deleting or replaying an older signed receipt fails closed. Declining preserves
input and dispatches nothing. Follow-ups and new chats reuse a still-valid receipt;
Settings → Models & Providers can inspect/revoke it. Gateway/route/policy changes
require reconsent. Backend validation runs at admission and execution.

Migration `021_chat_conversations` adds conversations and signed turns.
Additive `022_chat_preferences` adds provider receipts and personal preferences.
Populated-data downgrades are refused; no existing domain record is rewritten.
SQLite live upgrade and integration tests pass. PostgreSQL 022 execution is not
yet verified because the local Docker engine fails; tests collect successfully.
Database backups contain private messages and remain subject to existing storage
controls. This minimal service adds no deletion/retention automation.

## Actual model evidence and limitations

Select **ds/deepseek-flash** in Studio. Existing 9Router route, gateway key and
provider credentials are retained. The user's previous ds/deepseek-v4-flash
selection returned a different model identity and was correctly rejected. The
explicit official deepseek-flash selection is not a silent fallback.

Real production conversation `chat_c2c341edf7484ce1abb6ce5e42be85bf` contains three
completed answers: rainbow explanation, contextual red-band follow-up, and a
third question after refresh. Core has exact requested/actual ds/deepseek-flash,
Hermes/9Router provenance and measured usage. Signed first-use consent was reused.
No isolated runtime or browser response replacement was installed for this proof.
See `.local/chat-finalization/live-v1-core-proof.json`, `live-v1-final.log` and
`live-v1-resume.log`. The first helper's third-send wait failed before submission;
the corrected helper resumed the SAME conversation and proved the third response.

Configured provider is 9Router; underlying actual_provider remains null because
current trusted receipts do not report it. Do not infer it from model names.
Current discovery also cannot attest local-only inference. Unknown routes require
consent, even when the gateway itself is loopback. Trusted routing provenance is
needed to exempt truly local models and detect material downstream provider
remapping behind an unchanged namespace. Streaming/cancellation also need explicit
runtime contracts. No hidden tools, autonomous execution or fallback is enabled.

## Changes and validation inventory

Main frontend changes: `src/features/home/` (greeting/composer/adaptive lists),
`src/features/chat/` (workspace/messages/history/consent/hooks/typed API),
`src/features/settings/` (personal settings), `src/i18n/`, shell presentation/
translations, existing providers/router/client and `src/styles/tokens.css`.
Main backend changes: `modules/core/conversations.py`, `modules/core/chat_settings.py`,
`services/api/conversations.py`, Studio registration, `packages/contracts/chat.py`,
`database/schema.py` and additive migrations 021/022. Existing runtime/gateway
boundary refinements in this working tree are preserved. No domain UI is rebuilt.

Tests: Home/component/send/locale tests, shell/home browser contracts,
`integration-e2e/chat.spec.ts`, `tests/chat_browser_server.py`, conversation/model/
settings integration negatives and `tests/postgresql/test_chat_conversation_persistence.py`.
Existing PostgreSQL tests only update the expected additive migration head to 022.
The chat PostgreSQL filename differs from integration to avoid pytest collection
name collision. CI/dependency files include `.node-version`, package/lock,
quality.yml, Dependabot and removal of redundant `apps/web/.gitkeep`.

Some pending gateway/runtime/domain-test changes predate this finalization and
were retained. Complete real paths, including those inherited changes, are in
ignored `.local/chat-finalization/changed-files.txt`; validation does not claim
all pending edits originated in this phase.

Run build before both browser suites; Home uses Vite production preview on 5175,
chat uses real API/Core with a disposable database on 8871 and explicit isolated
runtime. Test outputs are separate. Do not interpret fixtures as live AI proof.
Commands and actual results: [validation report](../apps/web/VALIDATION.md).
