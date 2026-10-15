# Core Execution Hardening

## Stage 2 Milestone A — governed local MCP, 15 October 2026

Baseline: `development`, `1e4ae73261f7aa6a1b4ba264f84028682093c4a0`, clean
working tree before this work. The Stage 1 CI result belongs to that committed
baseline; it does not verify subsequent Stage 2 changes. Private PRD,
architecture, technology ADR and security documents remain unavailable: the
sibling documentation checkout contains an index, not those normative sources.

### Audit and ownership

| Component | Audited status before change | Reused / extension | Gap / security boundary |
|---|---|---|---|
| Capability projection | EXISTING & USABLE | `Capabilities.read` | Projection alone never grants a tool |
| Version / assignment | EXISTING & USABLE | Immutable `AgentVersion.metadata`, canonical payload hash and active assignment | Bind exact MCP approval hash without changing historical formats |
| Core authorization | EXISTING & USABLE | `RunCoordinator._claim`, `_tool_authority`, current effective permissions | Human `tool:register` added only for organization admins; run actors retain `run:create` |
| Tool dispatcher | PARTIAL | `_execute_governed_turns` | Former fixture-only path now dispatches one explicitly approved MCP alias |
| MCP registration / transport | MISSING | New responsibility owners `modules/core/tools.py`, `packages/tool_adapters/mcp.py`, `packages/contracts/tool.py` | Session-scoped approvals, strict local HTTP profile; no public registration API |
| Credentials / OAuth | MISSING for connectors | In-memory `SecretStr` supplied by trusted composition | No vault, plaintext persistence, OAuth login or restoration; restart denies old bindings |
| HTTP API connector | MISSING | Existing model transport is a confinement pattern only | No arbitrary URL tool and no generic API adapter added |
| Webhook | EXISTING & USABLE, limited | Existing `WebhookIngress` / automation owner | Bearer credential hash, TLS, exact approved config, deduplication, expiry, rate limit, rotation/revocation; provider-specific signature adapters absent |
| Network egress | PARTIAL | Exact endpoint guard in MCP adapter | Only explicitly allowlisted `127.0.0.1:<port>/mcp`; external TLS, DNS and redirects denied |
| Evidence / persistence | EXISTING & USABLE | Signed Core audit, execution record, effective-limits JSON | No migration or second evidence store |
| Bench | EXISTING & USABLE | Existing runner / graders / suite registry | Separate strict `read_only_mcp_fixture` profile preserves fixture and Research Safety contracts |
| Limits / recovery | EXISTING & USABLE | Core budget, owner fence, claim idempotency, deadlines and cancellation | Adapter additionally bounds protocol requests, bytes, attempts and tool calls |

### Registration and execution contract

Trusted backend composition supplies an explicit `mcp_endpoints` allowlist to the
existing coordinator. The default is empty. `core.mcp_tools.register` requires a
current authenticated human organization admin in the exact project, matching
owner, enabled server and owner-classified `READ_ONLY` risk. Other risk classes
are rejected; MCP annotations are not authorization. Discovery uses the official
SDK and verifies server name/version, protocol and exact input/output schemas.
Server descriptions are never copied into model instructions.

The approval is Core-signed and binds server, endpoint, scope, owner, tool alias,
remote tool, schemas, policy limits, an approval nonce and a keyed credential
identity. Raw credentials are not included. Registration replacement requires
revocation; atomic registration prevents competing aliases retaining authority
for the same server. Rotation/re-registration changes the binding, so existing
published versions cannot silently acquire the replacement connection.

`AgentVersion.metadata.mcp_bindings` maps its single MCP grant to that exact
approval hash. Existing version serialization and historical signatures are
unchanged. Factory evaluates, approves, publishes and assigns through existing
Core/Bench gates. No draft automatically receives a grant. Per-call Core checks
revalidate the actor, owner, immutable version, active assignment, claim, budget,
deadline and binding, including after discovery immediately before `tools/call`
and after the response. Authorization is repeated at the physical HTTP dispatch
boundary as well, so revocation while the SDK queues a call prevents transmission.
The server does not choose ARYN scope or permissions.

`Agent proposal → Core policy/grant check → signed invocation → official MCP
ClientSession → approved fixture endpoint → validated structured result → Core
audit/provenance → bounded model continuation → schema-validated final output`.

Hermes receives only the Core-authored alias/input declaration and validated
result data. It receives neither endpoint nor credential. Native toolsets remain
disabled, native execution remains prohibited, and each Hermes turn still has
`max_iterations=1`; Core owns the multi-turn loop and exact model identity. The
model capability probe remains the existing fixture-only probe, not a second MCP
probe or a live-provider attestation.

### Transport, dependency and limits

Pinned official `mcp==1.30.0` (MIT, maintained 1.x line) is used rather than a
handwritten protocol. Protocol is exactly `2025-11-25`. This release reuses the
existing httpx stack; adopting the separate newer httpx2 stack is outside this
slice. Its wheel SHA-256 was checked against PyPI:
`666edb5009503e1047c9d60346a756f94b261f05cc2625f23d41c728ffc484d0`.
Lock additions: mcp, httpx-sse and pydantic-settings (MIT), python-dotenv and
sse-starlette (BSD-3-Clause), python-multipart (Apache-2.0), Windows pywin32 (PSF).
No pre-existing locked package version was changed. SDK imports are lazy and
remain outside the native Hermes process.

The supported transport profile is authenticated **stateless JSON Streamable
HTTP over approved literal loopback only**. No stdio/process launch, OAuth
discovery, SSE, redirects, proxy/environment credentials or retry is enabled.
The SDK handles JSON-RPC; the httpx guard enforces exact destination/method,
protocol method allowlist, at most eight physical HTTP requests per session and
at most one `tools/call`. Repeated dispatch is rejected before networking.
Default response limit is 16,384 bytes, configurable up to 32,768; both declared
and streamed sizes are bounded, compression and non-JSON responses rejected.
Per-session timeout is at most five seconds and cannot exceed the Core deadline.
Per-connection read attempts are at most twelve per minute (failure consumes an
attempt). Approval lifetime is at most 300 seconds; availability observation
older than 60 seconds denies admission. A session has at most 128 retained
invocation identities, then denies further calls. These bounds are local MCP
bounds, not claims about external model billing.

Input/output use existing strict JSON/schema validators, including refusal of
external schema references. Output must contain exact organization/project
constants and match both MCP structured content and its single text JSON
representation. Remote errors, malformed/oversized results, schema/server drift,
credential-bearing output and foreign scope fail closed. Timeout/cancellation
preserve existing `outcome_unknown` and reservation semantics; unknown effects
are never automatically retried. Actual protocol request ID, request count,
binding/schema/endpoint/input/output digests, scoped server identity, bytes and
measured duration enter signed Core audit. No token or cost estimate is fabricated.

Approval observation and expiry use a single captured clock value, avoiding a
sub-millisecond lifetime overflow on high-resolution Linux clocks. The positive
protocol test advances the clock on every read to verify this on Windows too.
The timeout test measures the adapter boundary under its normal three-second
policy, separately from Core claim/settlement database work, while retaining the
five-second adapter maximum, unknown-state reservation and no-retry assertions.

### Scope and follow-up gates

`tests/mcp_fixture.py` owns a disposable official-SDK server and synthetic data;
`tests/integration/test_mcp_tools.py` owns actual protocol/Core/Factory/Bench
acceptance and negative cases. These two test modules and the three responsibility
owners above are the only new source files. Existing native Hermes and PostgreSQL
tests are extended. Model responses and their token usage are explicitly test
doubles, never proof of live provider support. See the verification results below
for actual commands; external MCP connectivity and live model inference are separate
unverified gates.

Milestone B proposal (approval required before implementation): explicit fixed
HTTPS resource/method adapters, DNS/IP destination enforcement, redirect refusal,
bounded requests/responses, encrypted scoped server-side credential lifecycle and
connection revision/revocation. Reuse existing webhook admission, queues, owner,
deduplication and audit; add provider-specific signature validation only to that
ingress. Provider sequence/watermark ordering is not supplied by current bearer
ingress and needs a connector-specific contract. Local Windows credential storage
and Hosted encrypted secret storage require separate approved lifecycle designs;
neither is implicitly provided by the current in-memory test connection.
MCP events, automation tool grants and workflow restrictions remain
unchanged. No generic HTTP tool, second scheduler, vault or OAuth placeholder is
introduced by Milestone A.

Milestone C proposed order: GitHub selected-repository read-only GitHub App;
Telegram authenticated inbound updates with explicit user/chat-project mapping;
Google Workspace user-consented read-only retrieval after OAuth state, callback,
vault and revocation controls; WhatsApp official Business Platform only, after
webhook verification and consent policy. Sending messages/email, writes, merges
and production account access require separate policy and approval. Each connector
needs its own scopes, resource allowlist, tests and external-access approval.
Official references: [GitHub permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app),
[Telegram webhooks](https://core.telegram.org/bots/api#setwebhook),
[Google OAuth](https://developers.google.com/identity/protocols/oauth2/web-server).
Meta's official documentation returned HTTP 429/inaccessible during this audit;
WhatsApp scope/API details remain a follow-up, not an audited integration claim.

Residual limits: ephemeral approvals/rate counters and in-memory secret handling;
no persisted connector inventory or encrypted connector vault; local stateless
JSON only, one MCP grant per version; no external MCP, OAuth, API connector,
messaging, frontend feature, migration or live inference in the implementation
scope. Delivery requires separate owner authorization.
The existing Stage 1 provider provenance/retry blocker is not removed by offline
MCP verification.

### Offline verification and delivery state

Environment: Windows, Python 3.12.12, official MCP 1.30.0, httpx 0.28.1,
cached Node 22.23.3, disposable loopback/tmpfs PostgreSQL 16.13. Native Hermes
is the installed interpreter under an isolated HOME/config with model HTTP
doubles and outbound sockets denied. The fixture uses the actual SDK server,
client, JSON-RPC initialization/discovery/call and real loopback HTTP; model
responses and their token counts are explicitly synthetic doubles.

| Actual command / check | Observed result |
|---|---|
| `uv run --frozen pytest tests/integration/test_mcp_tools.py -q --tb=short` | 63 passed before the last single-clock correction; positive protocol test repeated after that correction: 1 passed. All 63 are also passed on final source in the complete backend run below |
| `uv run --frozen --extra dev pytest -m 'not postgresql' --backend-shard=N/4 -q --tb=short --durations=8 -o faulthandler_timeout=120`, N=1,2,3 then 4 alone | Final source: 1266 passed, 5 skipped, zero failures/errors; 1271 exact test identities covered once |
| Final backend partitions 1/4, 2/4, 3/4, 4/4 | 316+2 skip / 317+1 skip / 316+2 skip / 317; 482.65s / 467.71s / 512.49s / 335.70s |
| Final-source JUnit subsets | MCP 63 passed; existing governed execution/probe 103 passed; native Hermes boundary 1 passed in 13.23s |
| `uv run --frozen pytest tests/postgresql -q --tb=short` | 142 passed. This complete run preceded the final MCP dispatch-fence/single-clock corrections; it is not labelled a complete final-source PostgreSQL run |
| `uv run --frozen pytest tests/postgresql/test_hosted_persistence.py -k 'mcp or governed or capability_probe or model' -q --tb=short` | Final corrected source: 8 passed, 24 deselected, 65.81s; restricted writer, actual MCP protocol, signed settlement/replay and duplicate/stop fencing |
| `npm run format:check`, `npm run lint`, `npm test -- --reporter=json --outputFile=../../.local/mcp-verification-20261015/frontend.json`, `npm run typecheck`, `npm run build` | Passed; 125 frontend tests, zero failure/pending; no frontend source changes |
| `uv run --frozen ruff check .`, `uv lock --check --offline`, `python scripts/check_repository.py`, actionlint, `git diff --check` | Passed |
| `pip-audit --skip-editable --format json` and `scripts/check_dependency_audit.py` | No known vulnerabilities; complete inventory of 87 distributions verified |
| `npm audit --audit-level=high --json` | Zero advisories at every severity |
| Redacted Gitleaks directory scan over all 21 changed/new source files | No leaks; includes the five untracked modules/tests, not merely `git diff` |

The five skips are three unauthorized live model tests and two live local-runtime
health/capability checks without the required API server credential. No live
request was authorized or executed. The earlier timeout assertion incorrectly
included Core database work; its failed report is retained and is not counted
as passing. Superseded batches were interrupted after source corrections, then
all four final partitions were run against the same 19-file source/contract/
test/lock snapshot. Documentation is outside that code snapshot.

Final artifacts: `.local/mcp-verification-20261015/backend-verified-[1-4].xml`,
`backend-verified-selection.json`, `source-verified-sha256.json`,
`verification-summary.json`, `postgres-clock-verified.xml`, frontend/audit JSON.
Exact JUnit identity sets match each disjoint partition and the complete manifest.
Source aggregate SHA-256:
`30be842d253ce90a936318ef2df873ef19f94535f2f93115d432add44a9bfdb1`.
The disposable PostgreSQL container was removed after verification.

Contract changes are additive: private `ToolTurnRequest.tool_declarations`;
human-admin-only `tool:register`; strict MCP approval/invocation/provenance
contracts; `read_only_mcp_fixture` Bench profile/suite; version metadata and
captured-limit MCP binding maps. Existing run/audit envelopes, historical version
formats and model capability receipts are unchanged. No public endpoint,
database table/migration, frontend feature, fallback or native toolset is added.

**Milestone A COMPLETE — OFFLINE VERIFIED**, limited to the approved local
stateless JSON read-only profile. External MCP connectivity and live provider
tool-calling remain **NOT VERIFIED**. Secure API/Webhook connectivity is
**PARTIAL** (existing webhook only), third-party connectors are **NOT STARTED**,
and Stage 2 overall remains **PARTIAL**. At completion of the local verification
above, Linux/remote CI had not been run and the change was uncommitted. Branch
and HEAD were still the baseline; 16 existing files were modified and five
necessary responsibility/test modules added. No commit, push, merge, deployment,
real credential change or external account access had occurred. Subsequent
authorized delivery must be verified against its exact commit SHA.

## Provider preflight follow-up — 15 October 2026

Baseline rechecked: `development`, HEAD
`4994a6cc49f95deec0e2fe5b8608b0ca6e32a489`, previous 21-file local diff retained.
See [the installed 9Router routing/retry/provenance audit](9router-gateway.md#provider-preflight-and-delivery-audit--15-october-2026).
Live capability remains blocked on trustworthy gateway provenance, current
metadata access and upstream resource bounds; no inference or commit is authorized.

Final regression exposed an existing preview evidence presentation defect:
`factory.preview.dispatched` and `core.run.outcome_unknown` can have identical
clock timestamps. `AgentPreviewService.read` previously broke ties using random
audit UUIDs, allowing a dispatched event to appear after the terminal event.
The actual synthetic fixture database reproduced that timestamp tie. The minimal
fix changes only the verified preview timeline projection: timestamp first,
accepted/dispatched/stopping/terminal phase for ties, then event ID. Sequence
numbers are contiguous presentation indices. Stored audit envelopes, timestamps,
signatures, Core run state, permissions and execution authority are unchanged.

Only `modules/core/agent_preview.py` and the existing
`tests/integration/test_agent_canvas.py` required an additional source/test change.
Four deterministic cases use identical signed timestamps and descending UUIDs
for completed/failed/unknown/cancelled outcomes. Existing scope, tampering and
terminal-state assertions remain intact. The focused canvas suite passed 22
tests. A concurrent native Hermes test also failed before any pass marker;
it subsequently passed when run alone in 19.96 seconds. The initial subprocess
had no traceback or pass markers and was terminated under the unchanged
35-second test deadline during overlapping backend/frontend/PostgreSQL work.
Scheduling/resource contention remains the observed environmental limitation,
not a reason to weaken the deadline or assertions. Final backend regression is
repeated without overlapping frontend or PostgreSQL commands.

Actual follow-up verification artifacts:
`.local/ai-engine-verification/provider-preflight-20261015/`. Python 3.12.12
matches `.python-version`. The default PATH had Node 22.14.0; frontend validation
was repeated using the already cached Node 22.23.3 pinned by `.node-version`, with
PATH changed only inside the child verification shell. No installation or user
configuration change was needed.

| Actual command / verification | Result on current source |
|---|---|
| `pytest -m 'not postgresql' --backend-shard=1/4 -q --tb=short`, then `2/4`, `3/4`, `4/4`; `ARYN_RUN_LIVE_MODEL_TESTS=0` | 1203 passed, 5 skipped; all 1208 exact test identities covered once by JUnit/manifest union; no failure/error in the final union |
| Final partitions 1/4, 2/4, 3/4 | 300+2 skip, 301+1 skip, 300+2 skip; 590.18s, 581.98s, 557.11s |
| Final entire partition 4/4, run alone | 302 passed, 352.80s; includes native Hermes without altered deadlines/assertions |
| `pytest tests/integration/test_agent_canvas.py -q --tb=short` | 22 passed, including equal-timestamp phase ordering and existing tampering/scope checks |
| `pytest tests/integration/test_hermes_9router_binding.py -q --tb=short`, run alone | 1 passed, 19.96s; HTTP/model doubles and outbound denied, not live inference |
| `pytest tests/postgresql/test_hosted_persistence.py -k 'governed or capability_probe or model' -q --tb=short` | final source: 6 passed, 24 deselected, 44.62s; restricted writer in disposable loopback/tmpfs PostgreSQL 16.13 |
| `npm test -- --reporter=dot`, `npm run build`, `npm run lint`, `npm run format:check` | passed under cached Node 22.23.3; existing React render and dependency/chunk warnings remain |
| `npm test -- --reporter=json --outputFile=../../.local/ai-engine-verification/provider-preflight-20261015/frontend-results.json` | pinned Node: 125 passed, 0 failed/pending; authoritative run JSON retained separately from static test collection |
| Ruff, repository hygiene, `git diff --check`, redacted Gitleaks diff scan | passed on the final working tree |

Final backend reports are `backend-verified-1`, `backend-verified-2`,
`backend-verified-3`, `backend-serial-4`. The earlier four-part run had the actual
preview defect and native process deadline failure. After the preview fix, the
concurrent fourth partition still hit the native deadline; its failed report is
retained separately and is not counted as passing. The entire fourth partition
was then run alone and passed. Same-source coverage is verified from actual JUnit
identities, not a sum of unrelated focused runs. All 21 changed source/test files
match the saved SHA-256 snapshot; documentation is excluded from that code hash.
The final union contains all 103 governed-tool tests, 78 discovery/naming/transport
tests, 22 canvas tests, the native boundary test, permissions/idempotency and Bench
regression. Five skips are three unapproved live-model tests and two runtime
session-key checks. No live/provider test is reclassified as a mocked PASS.

The working tree now has 23 modified tracked files: the previous 21 are retained,
plus the existing preview owner/test. There is no new source file, API endpoint,
dependency, database migration or governance authority. Task PostgreSQL containers
were stopped after exact ID/label verification. HEAD is unchanged. Remote Linux,
remote CI, browser E2E and paid/live inference were not executed in this follow-up.
Private normative documents are still absent: the adjacent `aryn-docs` checkout
contains only `README.md` and `DOCUMENT_INDEX.md`.

Offline implementation is COMPLETE for the tested local scope. Live verification
is BLOCKED by the browser access policy and gateway provenance/resource contract.
Remote CI execution is BLOCKED pending explicit commit/push authorization; local
checks are prepared, but no new exact commit exists for remote verification.
Roadmap Stage 1 remains PARTIAL. No inference, commit, push, merge or deployment
is performed by this report or implied by implementation approval.

## Multi-provider hardening — 15 October 2026

Repository audit started on `development` at
`4994a6cc49f95deec0e2fe5b8608b0ca6e32a489`, with the previous 14-file capability
probe extension already present and uncommitted. Those changes were retained.
The private normative `aryn-docs` documents were unavailable; repository rules,
source contracts and local test evidence were used without inventing requirements.

Reused owners: `NineRouterGateway` for catalog/capability receipts, `ModelRouter`
for explicit selection, the confined Hermes transport, Core probe/claims/budgets,
Agent Factory versions and the existing Bench suite. No second router, execution
authority, provider service, endpoint, table, migration or dependency was added.
No inference or credential/configuration change was performed. HEAD is unchanged;
there is no commit/push or remote-CI claim for the local diff.

This increment modifies these existing owners:

- `packages/model_adapters/gateway.py`: presentation labels, collision handling,
  separate provider metadata states, current provider/configuration-bound evidence.
- `packages/contracts/model.py`: exact reported-model requirement for live receipt eligibility.
- `packages/contracts/runtime.py`, `packages/runtime_adapters/hermes/adapter.py`,
  `services/runtime/gateway_transport.py`, `modules/core/errors.py`: strict response
  identity and bounded provider error codes without bodies, fallback or retry.
- `modules/core/workflows/coordinator.py`: independently reject a reported model
  that differs from the exact claimed model before any governed tool effect.
- `apps/web/src/features/chat/components/ModelPicker.tsx` and its existing
  `features/chat/tests/chat.test.tsx`: catalog label for a fixed selection; option
  values and emitted selections retain IDs, including historical-ID fallback.
- `tests/security/test_9router_discovery.py`, `test_uat_model_availability.py`, `test_9router_exact_model.py`,
  `test_governed_tools.py` and `tests/integration/test_chat_model_verification.py`:
  multi-provider doubles, naming/status/error/security and history compatibility.
- This document and `docs/9router-gateway.md`: architecture/contract changes,
  test evidence and conditional live proposal.

The earlier probe changes in Core permissions/coordinator, native wrapper,
native/HTTP integration and PostgreSQL tests remain present. In total the working
tree contains 21 modified tracked files and no added source files.

The only previous namespace test changed its acceptance expectation from allowing
an unprefixed model to rejecting it; the assertion is stricter. Positive capability
attestation fixtures now include provider/configuration evidence, while new
negative cases reject its absence. No security assertion was removed or weakened.

See [discovery, exact identity compatibility and the live candidate proposal](9router-gateway.md#multi-provider-discovery-and-presentation--15-october-2026).

Verification artifacts for this increment are under the ignored directory
`.local/ai-engine-verification/model-discovery-20261015/`. Commands use
`.venv/Scripts/python.exe -m pytest` and explicitly disable live model tests.

| Actual command / selection | Result |
|---|---|
| `ARYN_RUN_LIVE_MODEL_TESTS=0; pytest -m 'not postgresql' --backend-shard=1/4 -q --tb=short` (repeated with `2/4`, `3/4`, `4/4`, separate basetemp/JUnit/log paths) | final source: 1199 passed, 5 skipped, 0 failures/errors; union of saved manifest and actual JUnit test identities exactly covers 1204 tests without overlap |
| `pytest tests/security/test_uat_model_availability.py tests/security/test_9router_exact_model.py tests/security/test_governed_tools.py -q --tb=short` | 149 passed before the last Core/projection guards |
| `pytest tests/security/test_uat_model_availability.py tests/security/test_9router_exact_model.py tests/security/test_governed_tools.py tests/integration/test_chat_model_verification.py tests/security/test_runtime_provenance_verification.py tests/integration/test_hermes_9router_binding.py tests/unit/test_model_router.py -q --tb=short` | 177 passed before the last Core/projection guards; includes actual installed Hermes with outbound blocked and HTTP doubles |
| `pytest tests/security/test_governed_tools.py -q --tb=short` | 103 passed after the Core reported-model guard |
| `pytest tests/security/test_9router_discovery.py tests/security/test_uat_model_availability.py tests/security/test_9router_exact_model.py -q --tb=short` | 78 passed after the sensitive-metadata projection fix |
| `pytest tests/security/test_9router_exact_model.py tests/security/test_governed_tools.py -k provider_error -q --tb=short` | 10 passed; rate limit, quota, explicit credit and unavailable are separate observations |
| `pytest tests/integration/test_chat_model_verification.py -q --tb=short` | 10 passed; rename does not alter stored IDs, request hashes, claims or historical responses |
| `pytest tests/postgresql/test_hosted_persistence.py -k 'governed or capability_probe or model' -q --tb=short` | 6 passed, 24 deselected, repeated after final Core guard; disposable cached PostgreSQL 16.13, restricted application writer |
| `npm test -- --reporter=dot` in `apps/web` | 125 passed in 16 files |
| `npm run build`, `npm run lint`, `npm run format:check` in `apps/web` | passed after formatting the new test; existing dependency/chunk build warnings remain |
| `python -m ruff check .`, `python scripts/check_repository.py`, `git diff --check`, redacted Gitleaks stdin scan of `git diff --no-ext-diff` | passed |

Initial test setup needed the parent artifact directory created before basetemp.
The first history test incorrectly referenced a nonexistent persistence field;
it was corrected to assert actual `RunStateModel.model`, `actual_model`, hash and
signature fields. The original sanitization test exposed label propagation of a
credential-shaped fixture; its assertion was preserved and the projection fixed,
with five nested-sensitive-field cases added. Initial formatting failed, then
passed after Prettier formatted the test. Two incomplete unsharded backend runs
were stopped by exact process/command verification (one had the sanitization
failure); neither is represented as a full-suite PASS. Final regression uses the
repository's existing four Windows partitions with separate basetemp, JUnit and
saved collection manifests; no assertion or test identity is excluded to pass.

No native Hermes source/configuration was edited. Installed source revision is
`3637c512fc3211bdccb61b7140d09ac1018508ba`. Offline model/HTTP doubles establish
boundary behavior only, never actual provider readiness or capability.
Task PostgreSQL containers were stopped only after exact ID/label checks.
Remote CI and Linux execution were not run for this uncommitted working tree.

Final Windows partition results: 1/4 = 299 passed, 2 skipped (501.11s);
2/4 = 300 passed, 1 skipped (513.98s); 3/4 = 299 passed, 2 skipped (493.58s);
4/4 = 301 passed (517.07s). Each partition selects 301 tests; PostgreSQL and
other partitions are deselected for that invocation, not omitted from aggregate
offline coverage. Five skips are three live-model tests lacking explicit owner
authorization and two runtime checks without `API_SERVER_KEY`. Separate native
Hermes boundary verification ran successfully with isolated credentials/doubles.

**Implementation status: COMPLETE for this offline hardening scope. Live
verification status: NOT VERIFIED. Overall Roadmap Stage 1 remains PARTIAL.**
Current provider metadata refresh was blocked by the browser origin permission
gate; it was not bypassed. The live proposal lists earlier observed routes across
three gateway providers, each with unknown availability/capability/cost. Actual
external routing, retry counts, exact reported model and provider configuration
revision must be established before authoritative live capability can be issued.
No inference, user credential/configuration change, commit, push, merge or
deployment occurred. All previous local work remains present, HEAD unchanged.

## Capability verification extension — 15 October 2026

Audit baseline: clean `development`, HEAD `4994a6cc49f95deec0e2fe5b8608b0ca6e32a489`.
The owner authorized code and isolated offline tests only. No provider inference,
credential/configuration change, commit, push or deployment is authorized by this
extension. Existing claim ownership, signed limits, reservation/settlement,
permission checks, output validation and audit remain the execution authority.

The explicit `tool_calling` mode of `verify_model` claims `tool_probe` in the
existing run store. Its fixed synthetic grant is independent of agent drafts or
published versions. Human admin/operator `model:verify` permission is checked
before admission and every tool/continuation handoff. Normal agent admission
cannot claim this mode through direct execution. The probe requires a structured
single fixture proposal, validated arguments/call ID, Core execution and a
schema-valid final continuation within two turns, one tool call and 4096 total
tokens (further reduced by Core/org/project limits). A text answer alone fails.

Terminal evidence uses the existing signed `core.run.evidence` envelope and an
internal `model_capability_probe` receipt. It binds the observed transcript digest,
output digest, authoritative run ID, provider/model and routing configuration;
usage remains the actual measured cumulative usage. Unknown effects retain their
reservation and cannot be retried by replay. Core Stop fences probe handoffs
without inventing provider cancellation.

Live registry eligibility requires real runtime/transport provenance and a
matching provider configuration revision; isolated doubles and incomplete
provenance never attest live support. Registry entries expire after 60 seconds
from original completion, including on replay. Full details and the explicit
remaining gateway metadata limitation are in [the gateway contract](9router-gateway.md).
No schema migration, new service, public endpoint, dependency, frontend change or
parallel evaluation engine is introduced.

Offline validation on 15 October 2026 (installed native Hermes source remains
`3637c512fc3211bdccb61b7140d09ac1018508ba`):

| Command / selection | Actual result |
|---|---|
| `pytest tests/security/test_governed_tools.py tests/integration/test_hermes_9router_binding.py tests/integration/test_chat_model_verification.py tests/security/test_runtime_provenance_verification.py -q` | 98 passed; isolated model/HTTP doubles, actual native engine boundary with outbound sockets blocked |
| `pytest -m 'not postgresql' -q` with `ARYN_RUN_LIVE_MODEL_TESTS=0` | 1152 passed, 5 skipped, 137 deselected; 1169.42 seconds |
| Final `test_governed_tools.py -k 'capability_probe or capability_receipt or http_probe or expired_capability'` | 45 passed; 13.72 seconds |
| PostgreSQL `test_hosted_persistence.py -k 'governed or capability_probe'` | 5 passed before final settlement guard |
| Final PostgreSQL `test_hosted_persistence.py -k capability_probe` | 3 passed; 7.62 seconds, including revocation at settlement |
| Ruff, `scripts/check_repository.py`, `git diff --check`, redacted diff Gitleaks scan | passed |

Each invocation used a separate basetemp/JUnit path under the ignored
`.local/ai-engine-verification/capability-probe-20261015/` directory. The broad
suite was collected before the final in-transaction permission and transport-scope
guards; the final focused and PostgreSQL selections verify those final branches.
The five skips are three unapproved live-model tests and two runtime checks
without a session key. Initial probe budget-fixture setup was corrected to create
the authority budget rows; the denial assertions were retained. One initial
focused command referenced an absent test path and collected no tests; the
subsequent command above uses existing files.

PostgreSQL verification used the cached CI-pinned 16.13 image, loopback-only
disposable containers with tmpfs and no host mounts, migration owner separated
from restricted application writer. Only task-owned containers were stopped
after ID/label verification. No production data was used. Live inference and
remote CI verification of this uncommitted extension remain unavailable; no
real model/provider has been newly attested. The owner must separately approve
the selected model, synthetic payload, possible charges and maximum dispatches
before a live probe.

Changed existing owners (14 tracked files, no new source files):

- `modules/core/workflows/coordinator.py` and `modules/core/permissions/engine.py`: explicit human probe permission, fixed claim, shared governed loop, final transactional reauthorization and signed receipt.
- `packages/contracts/model.py` and `packages/contracts/runtime.py`: typed probe binding/evidence and bounded private turn mode; default text contracts remain compatible.
- `packages/model_adapters/gateway.py` and `packages/runtime_adapters/hermes/adapter.py`: verify scoped expiring receipts, invalidate changed configurations and isolate transport doubles.
- `services/runtime/gateway_transport.py` and `services/runtime/hermes_9router.py`: capture actual provenance/revision and label injected model transports without enabling native execution.
- `tests/security/test_governed_tools.py`, `tests/hermes_gateway_check.py`, `tests/integration/test_hermes_9router_binding.py`, `tests/postgresql/test_hosted_persistence.py`: offline positive/negative, native-boundary and restricted-writer coverage.
- `docs/9router-gateway.md` and this document: probe contract, remaining provenance limitation and actual validation evidence.

Original/current HEAD remains `4994a6cc49f95deec0e2fe5b8608b0ca6e32a489` on
`development`; delivery leaves those 14 files modified and uncommitted. Stage 1
remains **PARTIAL** pending separately approved live observation and any missing
gateway/provider provenance. No model substitution or automatic promotion is
performed when evidence is unknown.

## Governed fixture execution — 13 October 2026

Audit baseline: `development`, clean working tree, HEAD
`9e66f05d177911c14f1fcd7bb4d58a841d3dd58d`. The adjacent `aryn-docs` contains
only its index/scaffold; private PRD/ARCH/TECH/SEC documents are unavailable.
Existing Core claims, reservations, process owner, assignment/publication
authority, immutable versions, signed audit and Bench remain the owners.

`RunCoordinator` now mediates bounded agent turns. Assigned execution captures
the existing version's grants/output contract in signed effective limits. Only
`aryn_fixture_lookup` / `aryn.fixture.read` is registered: it reads the constant
`aryn-core` verification fixture. It has strict input/output schemas, a read-only
risk class and an expiring Core context, with no host/file/network/secret handle.
It is an isolated verification tool, not a production data integration.

Hermes receives its allowlisted function schema but never executes the function.
`ExactGatewayTransport` validates the actual provider response, captures the
proposal and measured usage, then ends the single native turn with an inert
internal marker. `GovernedAgent` converts that receipt into a pending proposal;
the marker never becomes final Core output. Hermes' request worker swallows
exceptions in its own thread, so exception-based suspension is not supported.
The native compatibility test verifies this adapter protocol on the installed
engine with HTTP doubles and outbound sockets blocked. No upstream files change.

Core verifies current identity/membership, owner fence, signed claim, pinned
version/publication, active assignment, reservation, budget and deadline before
each dispatch and tool result handoff. Unknown/ungranted tools, invalid inputs,
duplicate call IDs and resource breaches fail closed. Limits are at most three
model turns and two tool attempts, further reduced by version/Core/project/org
turn policy. Every turn still has one physical gateway dispatch and no fallback
or retry. Cumulative measured usage is settled once; timeout, cancellation or
lost authority retains uncertain reservation without replay. Provider input
admission remains estimated and cost enforcement remains postflight when
measured evidence exists; these are not hard provider billing guarantees.

Tool decisions, result digests, durations, iteration usage and model identities
use existing signed audit schema 2. Final action evidence is persisted in a
`core.run.evidence` audit envelope and verified on read; missing/tampered completed
governed evidence is rejected. That receipt also binds terminal status and the
stored sanitized output digest; edited output or status cannot reuse a valid
action receipt. Raw tool inputs/results are not global audit data.
Runtime-supplied tool execution evidence is rejected. Core trace reads can project
verified persisted actions. In-flight unknown runs retain their individual audit
observations but do not claim a complete action trace.
Explicit Core Stop fences subsequent governed tool/turn admission immediately,
records `outcome_unknown` and retains reservation while provider cancellation is
unconfirmed. A late, measured model result can be audited by the current owner
but cannot execute a tool or complete the stopped run.

Core completion and Bench share the existing strict output validator: duplicate
keys/non-finite JSON, extra properties in strict schemas and schema violations
are rejected. Assigned output failures have `failed` / `invalid_output`; no
automatic correction inference occurs. Bench keeps invalid observations for its
graders and never promotes failures. Existing agent canonical defaults/hashes
are unchanged, draft preview grants remain disabled, and default text request
fingerprints retain their earlier representation.

Contract additions: typed model capability evidence; default-denied runtime
governed-turn capability; private authenticated loopback `POST /aryn/turn`;
`ToolTurnRequest`, `ToolTurnResult`, `ToolCall`, `ToolExecutionContext`;
bounded `RunRequest.max_iterations/max_tool_calls`; Bench tool-selection grader
and fixture isolation mode. No public API endpoint, frontend change, database
migration, scheduler, dependency or second execution authority is added.
The existing version-creation API admits only an explicit single
`aryn_fixture_lookup` grant. Draft canvas/preview remain text-only; assignment
still requires verified Bench, human exact-hash approval and publication.

Delivery remains **PARTIAL** until a selected real model has trustworthy tool
capability evidence. No live inference or real-provider tool support is claimed.
Remote CI was not available at the initial pre-commit delivery; earlier CI
results are historical. Development delivery must verify the exact pushed SHA.
Local verification uses an isolated installed Hermes
engine with HTTP doubles, SQLite fixture stores, and the cached CI PostgreSQL
16.13 image in a task-owned loopback container with in-memory data and no host
mounts. PostgreSQL product operations use the existing restricted non-owner
writer harness. Final terminal results are recorded after the checks complete.
Installed Hermes source actually tested: `3637c512fc3211bdccb61b7140d09ac1018508ba`;
its pyproject version is `0.0.0`, so the source revision is the compatibility
reference, not a guessed upstream semantic version.

Changed ownership files:

- `packages/contracts/model.py`: independent typed model capability evidence.
- `packages/contracts/runtime.py`: bounded tool-turn/context contracts and default-denied runtime capability.
- `packages/contracts/bench.py`: share the existing strict output validator; add fixture isolation and tool selection specification.
- `packages/model_adapters/gateway.py`: fresh explicit capability evidence; text probes do not prove tools/structured output.
- `packages/runtime_adapters/hermes/adapter.py`: private tool-turn transport and capability metadata on existing toolsets discovery.
- `services/runtime/gateway_transport.py`: validate/capture real proposals without native dispatch or retries.
- `services/runtime/hermes_9router.py`: confined proposal/continuation route using the existing AIAgent and native worker.
- `modules/core/workflows/coordinator.py`: existing claim/limits/permission/settlement authority mediates every step and verifies persisted evidence.
- `modules/core/capabilities.py`: advertise the bounded fixture boundary with prerequisites; grant nothing.
- `modules/bench/runner.py`: evaluation uses the same Core version claim and intersects grants.
- `modules/bench/graders.py`: reuse output validation and evaluate exact observed tool selection.
- `modules/bench/scenarios.py`: register fixture scenarios without modifying Research Safety.
- `services/api/studio.py`: permit only the registered fixture in existing version creation; no new public route.
- `tests/hermes_gateway_check.py`, `tests/integration/test_hermes_9router_binding.py`: installed-engine proposal/continuation and native confinement checks.
- `tests/postgresql/test_hosted_persistence.py`: restricted-writer governed evidence/settlement and concurrent duplicate checks.
- `docs/9router-gateway.md`, `docs/bench-engine.md`, this document: document actual contract changes and trust limits.
- New `packages/tool_adapters/fixture.py`: the previously empty adapter package had no matching executor; this owns only strict deterministic fixture IO.
- New `tests/security/test_governed_tools.py`: labeled model double and positive/negative Core/Factory/Bench/API tests for that new boundary.

Local verification commands use `.venv\Scripts\python.exe -m pytest`, unique
workspace `--basetemp=.local/ai-engine-verification/...` directories and the
existing test harness. The Windows sandbox blocks evidence hard-link creation;
these offline tests therefore ran with tool-approved filesystem/process access,
without replacing or weakening the signer. The initial sandbox attempts had
fixture setup errors; they are not passing evidence.

| Check actually run | Terminal result |
| --- | --- |
| Baseline authority/Hermes/provenance/Bench security selection | 139 passed |
| Gateway/native-Hermes/Core/Bench focused selection | 170 passed |
| Existing Factory/API/Core/immutable-version regression selection | 130 passed |
| Final governed-tool/authority/idempotency/execution selection | 88 passed |
| Final `tests/security/test_governed_tools.py` after output/status sealing | 45 passed; 100.55 seconds |
| Final adapter/stop/revocation selection | 10 passed |
| Installed native Hermes boundary, proposal and continuation after transport correction | passed; HTTP doubles, no live provider |
| `pytest -m postgresql` against disposable PostgreSQL 16.13 | 136 passed; restricted writer |
| Final PostgreSQL `test_hosted_persistence.py -k governed` | 3 passed, including the additional stop test |
| PostgreSQL governed rerun after output/status sealing | 3 passed; 23.75 seconds |
| Initial full `pytest -m 'not postgresql'` | 1086 passed / 5 skipped / 3 failed; snapshot and extra discovery requests repaired |
| Full regression rerun | 1106 passed / 5 skipped / 136 PostgreSQL tests deselected; 1220.26 seconds |
| `python -m ruff check .`, `python scripts/check_repository.py`, `git diff --check` | passed |

The full regression failures were addressed in owners, without editing their
assertions: terminal governed evidence reads no longer query audits for legacy
text runs, and capability metadata uses the existing `/v1/toolsets` response
instead of an extra request on text-only paths. Their focused rerun passed.
One new audit assertion initially referenced a detached ORM row; it now captures
the scalar ID inside the session and verifies the same measured usage assertion.
The disposable PostgreSQL container was removed after checking its task label.
No live model, production database, frontend gate or remote CI run is claimed.
The full rerun precedes the final stop/audit-output sealing changes; final
governed and restricted-writer selections verify those affected paths separately.
At the pre-commit delivery, original and current HEAD were
`9e66f05d177911c14f1fcd7bb4d58a841d3dd58d` on `development`, with 19 modified
tracked files and two new files listed above, all unstaged. That verification
phase performed no commit, push, merge, release, deployment, live inference,
running user-service restart or user credential/configuration change.
Both disposable PostgreSQL verification containers were removed after ownership
checks. JUnit evidence remains under ignored `.local/ai-engine-verification/`.
Residual work before MCP/integrations: owner-approved real-model capability
verification (including cost/data consent), access to normative private docs,
and approved cross-platform CI/UAT. Provider metadata and trusted-host/runtime
assumptions, estimated input admission and unavailable provider cost remain the
documented limits; no arbitrary connector/host/write execution is enabled.

Subsequent live PostgreSQL verification is recorded in [CI validation](ci-validation.md).
Write transactions now lock/refresh RunState before terminal decisions and usage
settlement; Core governance commit authorization precedes blueprint/version locks.
Real restricted-role tests cover concurrent reservations/settlement, advisory owner
rejection, stale owner fencing and unknown recovery. Earlier offline-only evidence
below remains historical; production host/ACL/distributed-worker claims remain unproven.

Tanggal audit/validasi: 8 Oktober 2026. Branch `development`, baseline dan HEAD awal
`5e9392c5f976b4725813dd98ccd8c6811472d9ae`. Working tree awal bersih dan HEAD tidak lebih
baru. `main` tetap `630cbc96d728a49a64247ad2b88978529a7cbbad`. Tidak ada push dalam delivery ini.

## Hasil dan batas klaim

Core memakai ledger budget existing, signed execution claim, owner process yang dikunci,
dan satu kontrak hasil persisten. Factory Bench memakai coordinator yang sama, termasuk bounded capabilities/model preflight dan action trace. BN-06,
AF-07, immutable AgentVersion, exact human approval, CAS, atomic publication/rollback,
dan independent history commitments migration 013 tetap berlaku.

Deployment yang didukung untuk execution sekarang adalah **satu authority process pada
satu host**, dengan beberapa coordinator dalam process tersebut. SQLite diuji dengan
proses OS nyata, bukan pengganti bukti live concurrency PostgreSQL. PostgreSQL DDL diuji offline; live PostgreSQL locking/privileges dan
multi-host failover belum terbukti. Hosted foundation freeze masih BLOCKED.

Provider tidak menyediakan exact input-token admission atau hard total-token/cost ceiling
pada kontrak existing. Karena itu, input admission adalah estimasi, output adalah request
cap yang diteruskan transport, dan total/input/output terukur diverifikasi setelah
completion. Pelanggaran terukur menjadi failure, bukan success; angka actual tidak
dipangkas agar terlihat sesuai policy. Missing evidence/timeout/outcome ambigu memblokir
verified completion dan mempertahankan reservation. Ini **bukan jaminan provider tidak
menagih lebih dari cap**, bukan hard tokenizer quota, dan bukan Managed AI billing.

## Root cause dan perbaikan

| Temuan | Root cause | Perubahan |
|---|---|---|
| H3 | Agent budget/timeout hanya metadata; preflight estimasi tanpa reservation; accounting Bench berada di wrapper API; missing usage bisa menjadi nol | Effective limits min agent/project/org/model/runtime, full token reservation sebelum dispatch, deadline Core, measured settlement satu transaksi, availability terpisah, Factory Bench melalui Core |
| H5 | Startup memperlakukan seluruh in-flight run/evaluation sebagai abandoned; tidak ada live owner atau fencing | OS lock lifetime, owner UUID per authority, PG advisory session lock, stale owner fence, recovery hanya owner sebelumnya setelah memperoleh authority, terminal outcome_unknown |
| M1 | Query scoped kosong jatuh ke global cache correlation ID | Scope wajib di semua reads; hasil database kosong tetap kosong; ephemeral cache filter org/project |
| M3 | Dependency exception/raw payload bisa masuk client, SSE, audit; prompt berulang di audit | Public code/message/IDs, scrub nested secrets/known credentials, prompt/output audit hanya fingerprint/reference; operational content tetap scoped |
| M4 | Persisted Bench verification membuat signer/identity/permission authority dari environment baru | Manager/engine memegang configured Core signer, PermissionEngine dan ApprovalEngine; revalidation memakai instance tersebut, bound mutation session |
| M5 | Studio membaca assignment sebelum await dan memakai version itu untuk audit/response | Semua run outcome/audit/cache/SSE dari committed Core claim; preclaim hanya intent; captured signed provenance tetap sama saat rollback |
| L1 | Project admin capability lebih luas daripada org governance commit authority; permissions sebelum await/transaction bisa stale | Org admin wajib approval/baseline/rollback, org admin/operator publication dengan project permission yang sesuai; membership re-read/lock saat commit; reads reauthorize setelah await |
| L2 | Response baru/cache/SSE/history berbeda dan status/error/usage/provenance parsial | RunResult persisten satu schema, explicit unknown/unavailable, typed important events/response reader, old flat aliases dipertahankan |

## Execution authority dan transaction boundaries

1. Studio default startup memperoleh `ExecutionAuthority` sebelum migration/provision/recovery.
   Coordinator dan Factory memperoleh instance yang sama per engine/database/process.
   SQLite absolute path memakai `.execution.lock` nonblocking OS lock; memory DB hanya
   authority process lokal. Host ACL harus melindungi path/parent dari unlink/replacement.
2. PostgreSQL membutuhkan protected `ARYN_HISTORY_COMMITMENT_PATH` dan session advisory
   lock database. Koneksi khusus dipertahankan sepanjang owner lifetime, diperiksa backend
   PID/invalidation, diserialisasi antar-thread, lalu explicit unlock dan invalidasi ketika
   disposed. Kehilangan koneksi menolak authority, bukan transparan reconnect/takeover.
3. Second process tidak boleh startup pada database yang masih dimiliki process hidup.
   Tidak ada lease expiry berbasis timeout yang dapat mengambil authority dari process
   lambat. Coordinator kedua dalam process yang sama berbagi owner dan melewati recovery
   atas run/Bench yang masih dimiliki owner tersebut.
4. Claim transaction: current membership + assignment/version/history/publication verification,
   effective limits, unique project idempotency key, Core run ID, owner/deadline,
   budget reservation, signed claim dan audit initiation commit **sebelum** runtime dispatch.
   Tidak ada lock database dipegang sepanjang inference. SQLite writes memakai BEGIN
   IMMEDIATE; PostgreSQL budget rows memakai FOR UPDATE, org `*` lalu project.
5. Setelah capabilities/model-availability await, Core memeriksa owner, state, deadline dan
   membership lagi sebelum dispatch. Factory approval/publication/assignment mengunci version sebelum membership;
   approval signatures/current approver authority direvalidate dalam session mutation.
6. Terminal transaction: owner/claim verification, model/runtime identity, measured usage,
   deadline/limits, ledger settlement, CAS state transition dan authenticated audit commit
   bersama. `usage_settled` serta terminal no-op mencegah double counting/re-dispatch.
7. Engine disposal/lost lock memfence coordinator lama. Engine lama tidak otomatis memperoleh
   authority baru. Restart memakai engine baru; old in-flight owner menjadi outcome_unknown,
   bukan confirmed failure/cancellation. Terminal tidak dapat diubah oleh stale completion.

Cancellation ACK hanya mencatat attempted/stopping. True dikembalikan ketika runtime/Core
terminal state membuktikan cancelled. Deadline, polling exception, caller cancellation atau
crash tanpa terminal evidence tetap unknown. Async deadline watchdog berjalan tanpa client
polling; runtime yang mengabaikan task cancellation tidak dapat menulis completion Core.
Provider/server mungkin masih bekerja sesudah Core deadline, sehingga reservation ditahan.
Rollout 013→014 harus menghentikan binary Core lama terlebih dahulu; mixed-revision live
execution tidak didukung. Pre-014 rows tanpa signed owner tidak membuktikan worker telah
mati. Recovery legacy hanya menyatakan outcome belum diketahui/read-only dan admission
scope diblokir sampai consumption direconcile, bukan proof termination/confirmed cancellation.
OS ownership proof berlaku pada authority 014 yang berpartisipasi dalam lock protocol.

Bench evaluation memiliki evaluation_owner_id. Startup tidak menolak evaluating version milik
owner hidup. Recovery owner sebelumnya menandainya rejected/interrupted, tanpa mengarang
Bench execution result/approval. Result commit memeriksa owner, exact payload, evaluating
state dan current permissions. Generic Factory service tetap melewati accounting walau tidak
melalui HTTP wrapper. Standalone BenchRunner adalah diagnostic tanpa persisted promotion
authority; signed Factory evidence selalu menggunakan Core coordinator.

Untuk multiworker/cloud scale-out diperlukan owner lease durable, heartbeat, fencing token
monotonik pada setiap commit, koordinasi durable dengan history commitment store, dan
independent provider-outcome reconciliation. Mekanisme sekarang tidak mengklaim distributed
worker framework, distributed freshness, atau native Hermes scheduler sebagai Core authority.

## Budget, usage dan provider contract

- Token total ceiling paling ketat dari agent RunRequest immutable config, Core default,
  organization `*` budget jika dikonfigurasi, project budget, dan model context window.
  Agent tidak dapat menaikkan project per-run cap. Timeout adalah min budget policy,
  AgentConstraints, Bench scenario/suite latency, request, dan runtime adapter timeout.
- Input UTF-8 admission estimate disimpan terpisah dalam effective_limits. Nilai itu tidak
  pernah dimasukkan sebagai measured ledger consumption. Exact tokenizer belum tersedia.
- Reservation mengunci **seluruh effective total ceiling**, bukan estimasi prompt, terhadap
  cumulative + outstanding reserved tokens. Org budget mencakup semua project; unknown
  historical execution juga memblokir admission pada scope aggregate org yang relevan.
- Ledger tetap `usage_budgets` existing. Tidak ada ledger API/Bench kedua. Fresh project
  budget default aggregate 1,000,000 tokens; migration tidak menebak quota organisasi/project
  lama: max_total_tokens NULL berarti aggregate quota belum dikonfigurasi. Existing per-run
  caps tetap berlaku. Jika legacy consumption belum bisa direconcile, execution scope diblokir. Angka aggregate tidak mengandung subscription/period-reset semantics.
- Complete measured triplet integer nonnegative dengan input+output=total diperlukan.
  Confirmed partial failure/cancellation dapat settle actual usage; unavailable evidence
  tidak menjadi measured zero. Numeric compatibility default 0 selalu disertai unavailable.
- Settlement membebaskan full reservation dan menambah actual tokens sekali saja, termasuk
  excess jika runtime melanggar limits. Missing evidence mempertahankan reservation;
  idempotent replay tidak dispatch atau settle lagi. Tidak ada auto-release/reconciliation
  yang menebak consumption. Operator harus memperoleh authoritative independent evidence.
- Cost hanya persisted bila runtime menyediakan finite nonnegative cost dengan source
  provider_usage/runtime_meter. Tidak ada harga/model-rate atau cost hasil perkiraan dibuat.
  Missing cost tetap NULL. Cost cap terukur yang dilanggar menjadi failure.
- Direct managed Gemini/Nous route diblokir bila pricing/ceiling authority belum tersedia.
  9Router/BYOK/local/mock diberi billing_category external_or_local; Core tidak melabeli
  konsumsi tersebut ARYN Managed AI. Atomic **money reservation** belum tersedia dan tidak
  diklaim. Managed AI baru dapat dibuka setelah trusted price/reservation/provider contract.
- Guarded Hermes transport meneruskan Core output cap, menolak extra n/completion override,
  membatasi satu upstream dispatch per receipt termasuk retry setelah success/failure,
  mempertahankan exact model dan deny-by-default tools. Tests memakai HTTP doubles;
  tidak ada paid/live-provider request.

## Audit, errors dan authority consistency

AuditEvent schema 2 dari migration 013 tetap authenticated/canonical UTC. New sanitization
berjalan sebelum hash/sign, mencakup nested sensitive keys, credential patterns dan credentials
runtime/gateway yang diberikan secara eksplisit. Prompt/system prompt/output/raw response/trace
pada audit menjadi SHA256 + byte count, bukan raw content. Token counters/evidence metadata
tidak ikut dihapus oleh regex credential. Historical weak audit tidak diubah atau dijadikan
approval/publication baru.

Audit correlation/all-events read memerlukan SecurityContext. Database query kosong tidak
menggunakan global cache. Repository/session/API selalu membatasi org/project. In-memory
cache juga discope, termasuk jika correlation ID dua tenant sama.

Dependency error text, repr, traceback dan upstream body tidak dikirim ke JSON/SSE atau audit.
Public error berisi error_code aman, pesan statis, correlation_id dan run_id bila claim ada.
Frontend ApiError mempertahankan IDs. Internal Core deadline persistence log hanya code/ID;
raw diagnostic exception tidak disimpan oleh jalur ini. Runtime native Hermes tetap trusted
operational storage/process terpisah; deployment harus membatasi akses log/trace/output dan
retention secara mandiri. Tidak ada retention enforcement baru yang diklaim. Recommended
operator policy: log diagnosis minimal/private, rotasi dengan TTL yang ditentukan operator,
scoped operational prompts/results hanya selama kebutuhan diagnosis yang disetujui.

Sanitizer tidak bisa mengenali semua secret arbitrer tanpa label/pattern/registered credential.
Host, signing key, trusted runtime configuration dan operational DB/ledger tetap trusted.
Tidak ada klaim tahan compromised database superuser/host atau coordinated snapshot rollback
ledger execution. Migration 013 independent history freshness boundary tetap berlaku sendiri.

BenchRepository dan activation/regression repository memakai DatabaseManager/session configured
signer, PermissionEngine, TrustedIdentityBinder dan ApprovalEngine. Tidak ada reconstruct
identity secret atau random signer dari environment pada persisted revalidation. Injected Core
trusted authority tetap berhasil tanpa ARYN_IDENTITY_SECRET, sedangkan missing/invalid authority
tetap deny. Approver org admin/status direvalidate saat mutation, tidak hanya saat approval dibuat.

## Run/Studio contract dan historical compatibility

RunResult selalu membawa Core run_id, status, requested/model, actual_model/provider/runtime/gateway
jika diamati, runtime_run_id jika tersedia, captured assignment/version/payload/transition,
publication reference dalam execution_provenance, effective_limits, verification flags,
usage availability/cost source, output_reference dan sanitized error_code. Timestamps UTC epoch
seconds pada envelope; UI menerima historical ISO timestamp juga.

JSON baru, SSE run.completed, cached terminal replay dan historical snapshot memakai serializer
persisted yang sama. run.completed berarti transport outcome tersedia; status bisa failed,
cancelled atau outcome_unknown dan UI tidak menampilkan success. In-progress replay kembali
state/provenance yang sama dan tidak memulai inference kedua. HTTP execution dependency failure
sebelum terminal evidence tetap sanitized error; caller bisa diagnosis/retry idempotent Core ID.

Rollback saat model preflight hanya mempengaruhi **claim berikutnya**. Core memilih exact current
version pada transaksi claim, dan final Studio audit/result berasal dari claim tersebut. Run yang
sudah in-flight tetap bound versi lama; current assignment tidak menulis ulang metadata history.
Preclaim event run.requested hanya membawa intent, tidak version/model yang bisa stale.

Historical rows tetap readable dengan missing claims/actual usage/provenance sebagai unverified
atau unavailable. Signed execution envelope mengikat org/project, run/request hash, model/provider,
owner, mode, canonical deadline, limits dan assignment attestation. Tamper/deletion sebagian
memblokir verification; menghapus seluruh new claim tidak membuat historical read-only row eligible
untuk authoritative execution replay. Existing completed counters tidak direattest sebagai measured.

## Migration dan compatibility

Migration `014_execution_authority` melanjutkan `013_history_integrity`. RunState menambah
execution claim/signature/owner/deadline/limits, reservation/settled/availability, sourced cost,
error code; UsageBudget menambah aggregate token cap/reservation; AgentVersion menambah evaluation
owner metadata. Tidak ada domain baru atau backfill historical evidence. Metadata fresh install
memiliki kolom yang sama dengan migration chain.

SQLite upgrade 005â†’014, 004â†’014, 009â†’014 dan 013â†’014; downgrade/re-upgrade 014â†”013 serta
legacy multi-revision migration diuji. PostgreSQL upgrade/downgrade DDL dikompilasi offline.
Downgrade menghapus execution-authority fields; backup wajib secara operasional sebelum downgrade.
Re-upgrade tidak mengarang kembali claim/settlement; unknown historical consumption memerlukan
reconciliation. Original database pengguna tidak dimigrasikan/dimutasi oleh validasi clone. Clone dari
.local/studio.sqlite3 (009) mempertahankan 8 runs, 13 versions dan 84 audit events; clone
aryn_local.db (004) mempertahankan empty counts. Keduanya upgrade ke 014, foreign_key_check
kosong, integrity_check ok dan zero fabricated execution claim. Original revision tetap sama.

## Evidence dan validasi aktual

Seluruh validation run final selesai. Hasil berikut berlaku untuk delivery ini. Command dijalankan dari repository root
kecuali npm dari apps/web. Tidak ada live model/provider berbayar diaktifkan.

| Command aktual | Hasil aktual |
|---|---|
| Dedicated command di bawah | **108 passed**, 31 warnings, 220.35 detik; no skipped |
| `python -m pytest -q -ra --tb=short` | **661 passed, 5 skipped**, 37 warnings, 619.25 detik; no failures |
| `npm.cmd test -- --reporter=dot` | **83 passed**, 13 files, 21.26 detik |
| `npm.cmd run build` | TypeScript/Vite PASS, 28.93 detik; existing >500 kB bundle warning |
| `npm.cmd run test:e2e` | **16 passed**, 0 retries/flaky/skipped, 5.0 menit; final serial run |
| SQLite clone migrations 009/004→014 | PASS, counts preserved, no fabricated claims, original DB unchanged |
| PostgreSQL upgrade + 014→013 offline SQL | PASS compilation only, covered dedicated tests |
| Focused Ruff `--select E4,E7,E9,F` changed production Python/new execution tests | PASS |
| `git -c core.safecrlf=false diff --check` | PASS |

```powershell
python -m pytest tests/security/test_core_execution_authority.py tests/integration/test_core_execution_contract.py tests/security/test_execution_idempotency_claims.py tests/security/test_governance_history_integrity.py tests/security/test_9router_exact_model.py tests/integration/test_schema_migration_compatibility.py tests/integration/test_assignment_activation_migration.py -q -ra --tb=short
```

Final logs: .local/execution-dedicated-release.log, execution-backend-release.log,
execution-browser-serial.log, execution-frontend-confirmed.log, execution-build-confirmed.log,
execution-existing-migration.json, execution-focused-lint.log. Logs tetap artefact lokal,
bukan data prompt model atau secrets yang dipublikasikan ke repository.

Lima backend skips adalah tiga live-model opt-in dan dua Hermes integration tanpa
API_SERVER_KEY. No paid/live-provider testing. Deprecation warnings FastAPI/httpx dan
Alembic path_separator dicatat; tidak berarti test failure. Percobaan full configured Ruff pada seluruh changed Python files menghasilkan **FAIL,
386 lint findings**, termasuk style rules dan unused fixture/import pada legacy tests;
full configured lint tidak direrun pada final revision. Final focused correctness lint di
atas PASS untuk changed production Python/new execution tests. Tidak ada klaim bahwa
seluruh configured lint clean; tidak ada security assertions dihapus sebagai lint fix.

Perubahan assertions compatibility yang disengaja: operational run-count tests membedakan
Core Bench consumption dari assignment runs; assertion tanpa operational dispatch tetap ada.
Downgrade tests membandingkan semua immutable configuration/evaluation/governance fields,
sedangkan evaluation_owner_id baru memang dihapus migration downgrade. Recovery/caller
cancellation sekarang mengharapkan outcome_unknown, bukan fabricated failure. Concurrent
idempotency mengharapkan one dispatch, in-progress signal, lalu exact terminal replay. API
failed runtime completion mengembalikan result envelope HTTP 200 dengan status failed;
transport error tetap error. Security assertions tidak dihapus untuk membuat PASS. Dua
existing approval-message assertions dipertahankan dan public/static denial text disesuaikan.

Percobaan validasi sebelum final mencatat failures yang diperbaiki: isolated cancellation
fixture kehilangan required output/created_at; org denied claim rolls back new budget row;
SSE browser Network.getResponseBody tidak tersedia. E2E kini membaca Response.clone pada
fetch browser yang nyata tanpa response replacement/request tambahan, serta mempertahankan
terminal evidence/URL assertions. Full run sebelum pesan approval diperbaiki menghasilkan
657 passed, 2 failed, 5 skipped; ini bukan final PASS. Beberapa full runs diinterupsi ketika
review menemukan perubahan tambahan, sehingga tidak digunakan sebagai completion evidence.

## Negative review akhir

- Tested agent timeout lebih rendah, measured input/output/total/cost breach, concurrent project
  quota dan aggregate org quota, idempotent settlement, Factory direct Bench consumption.
- Tested unavailable usage, partial failed usage, unknown reservation retention, no synthetic cost.
- Tested real Windows second process denial, crash process termination/new owner recovery, live
  same-process coordinator/app/Bench recovery exclusion, disposed stale worker terminal fencing.
- Tested cancellation ACK stoppingâ†’unknown, async deadline tanpa polling, membership revoke sesudah
  claim dan selama polling, project admin capability/commit denial, role change after preflight.
- Tested same correlation ID cross-tenant scoped empty read/cache, nested secret/prompt audit
  fingerprint, synthetic credential exception JSON/SSE/provider response, captured rollback race.
- Tested JSON/SSE/cached equality, in-progress actor binding/read reauthorization/unsigned claim denial,
  signed owner/deadline/limits/model tampering and claim deletion,
  injected generic Bench approval authority without environment secret, 013 commitments/BN-06/AF-07.
- Reviewed no hidden model retry, no successful error envelope, no fabricated historical approval,
  version immutability/state machine, no transaction kept open over model inference, exact claim
  source for API/audit/history, permission revalidation after async boundary.

Browser release run bersamaan dengan full/dedicated pytest mencatat 13 passed, 3 failed
pada display wait 5 detik. Trace menunjukkan snapshot HTTP 200 sekitar 4.9-9.6 detik dan
UI masih Memuat data proyek; tidak ada authority-denial bypass. Browser rerun final serial menghasilkan **16 passed** tanpa perubahan/kelonggaran assertions. Snapshot revalidation per-version,
long history dan repeated authority checks mempunyai biaya latency; optimisasi/pagination
belum diimplementasikan dan tidak diklaim scalable.

## Residual dan keputusan freeze

Supported local execution protections telah diimplementasikan; tidak ada klaim provider hard total
quota/cost, Managed AI ledger, distributed failover atau PostgreSQL live concurrency PASS. Unknown
outcomes mempertahankan reservation dan memerlukan manual evidence reconciliation, sehingga recovery
aman dapat mengurangi availability. Single-authority restriction sengaja enforced sampai desain
lease/heartbeat/fencing diterapkan dan diuji. Full audit-stream freshness/host compromise resistance,
production auth/retention enforcement dan operational reconciler tetap di luar capability yang dibuktikan.
Hosted foundation freeze tetap BLOCKED, selaras migration 013.

## Files changed

```text
.gitignore
STATUS.md
apps/web/e2e/studio.spec.ts
apps/web/src/components/canvas/canvas-builders.ts
apps/web/src/components/canvas/canvas-inspector.tsx
apps/web/src/components/shared.tsx
apps/web/src/components/version-form.tsx
apps/web/src/features/bench.tsx
apps/web/src/features/runs.tsx
apps/web/src/lib/api.ts
apps/web/src/lib/types.ts
apps/web/src/lib/utils.ts
apps/web/src/studio.tsx
apps/web/src/test/run-result-contract.test.tsx
database/connection.py
database/migrations/versions/014_execution_authority.py
database/repositories/agent_activation_repo.py
database/repositories/bench_regression_repo.py
database/repositories/bench_repo.py
database/repositories/budget_repo.py
database/repositories/run_state_repo.py
database/schema.py
docs/9router-gateway.md
docs/agent-factory-contracts.md
docs/bench-engine.md
docs/core-execution-hardening.md
docs/studio.md
modules/agent_factory/service.py
modules/bench/runner.py
modules/core/approvals/engine.py
modules/core/audit/logger.py
modules/core/errors.py
modules/core/permissions/engine.py
modules/core/usage/engine.py
modules/core/workflows/coordinator.py
modules/core/workflows/ownership.py
packages/contracts/runtime.py
packages/contracts/timestamps.py
packages/runtime_adapters/hermes/adapter.py
services/api/studio.py
services/runtime/gateway_transport.py
tests/e2e/test_smoke_end_to_end.py
tests/integration/test_9router_studio.py
tests/integration/test_assignment_activation_migration.py
tests/integration/test_core_execution_contract.py
tests/integration/test_schema_migration_compatibility.py
tests/integration/test_studio_api.py
tests/security/test_9router_exact_model.py
tests/security/test_agent_security_and_governance.py
tests/security/test_core_execution_authority.py
tests/security/test_core_persistence_security.py
tests/security/test_execution_idempotency_claims.py
tests/security/test_tenant_isolation_ownership.py
```


Commit delivery menggunakan pesan `Harden Core execution ownership, budgets, and captured provenance`.
Commit berada pada development dengan parent baseline 5e9392c5f976b4725813dd98ccd8c6811472d9ae;
hash aktual diberikan pada laporan akhir/git log. Tidak ada push, merge atau rebase main.

## Deployment authentication follow-up

Deployment boundary hardening continues this revision without changing captured execution claims, budgets/settlement, owner fencing or governance history. Hosted identity now comes from configured verified OIDC issuer/subject mapping and server session; Core binder signs the session reference and PermissionEngine revalidates session/mapping/current membership at authorization/commit. Local development identity requires explicit mode and cannot be enabled in production. See [deployment security](deployment-security.md); real hosted infrastructure remains unverified.
