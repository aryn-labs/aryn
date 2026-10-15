# Secure HTTPS connectivity

Baseline audited: `main`, `cf5068059d0dc622650793209c45d09b8213604f`.
Scope: Stage 2 Milestone B, offline implementation. Following the offline review,
the owner authorized commit/push and GitHub Actions delivery verification.
Deployment, external API access, live model inference, production credentials,
connector OAuth and Milestone C remain outside this authorization. Frontend remains frozen.

## Existing architecture audit

Read `AGENTS.md`, `README.md`, `SECURITY.md`, Core execution/automation contracts,
deployment security, governance history and CI delivery contracts. The sibling
`aryn-docs` contains only its document index; private normative PRD/architecture/
security sources remain unavailable. No claim is made to have read them.

| Responsibility | Reuse and required extension |
|---|---|
| Authentication / tenancy | Existing verified identity binder, current membership, PermissionEngine and scoped repositories; no authentication changes |
| Publication / assignment | Immutable version payload and metadata, existing Bench/approval/publication gate and active assignment; exact `https_bindings` pin |
| Tool approvals | Extend the existing `modules/core/tools.py` owner and its single in-memory registry. `CoreTools` retains `MCPTools` as a compatibility alias, and `core.mcp_tools` remains the existing composition handle |
| Admission / execution | Same coordinator, signed claim, reservation, cumulative budgets, cancellation, ownership fence, deadline and idempotency; no second dispatcher |
| Credentials | Existing SecretStr, keyed binding identity, diagnostic redaction and protected audit/output sanitation; temporary binding only |
| HTTPS / SSRF | Missing before this change. A transport adapter owns a numerically pinned socket with mandatory certificate/hostname verification |
| Evidence | Existing signed append-only audit/history and run evidence; no new evidence database or migration |
| Bench | Existing suites, runner, graders and promotion gates; one strict synthetic HTTPS suite |
| Webhook | Existing HTTP ingress → WebhookIngress → signed/deduplicated occurrence → CoreAutomations owner → Core admission |
| Capabilities | Existing informative projection; separate structural adapter/temporary binding from unverified external connectivity, unavailable persistent credentials and OAuth |

No router, credential store, authorization engine, automation engine or execution
coordinator is created. The only new production module is the HTTPS transport.
No dependency, lockfile, frontend, provider/model configuration or DB schema changes.

New files: this document, `packages/tool_adapters/https.py`, `tests/https_fixture.py`,
`tests/integration/test_https_tools.py`, `tests/security/test_https_boundary.py`,
and `tests/postgresql/test_https_persistence.py`.

Modified files: `README.md`; `modules/core/tools.py`, `modules/core/capabilities.py`,
`modules/core/errors.py`, `modules/core/workflows/coordinator.py`;
`packages/contracts/tool.py`, `packages/contracts/runtime.py`,
`packages/contracts/bench.py`; `modules/bench/runner.py`,
`modules/bench/scenarios.py`; `tests/hermes_gateway_check.py`,
`tests/integration/test_hermes_9router_binding.py`,
`tests/security/test_automation_webhook.py`.

Audit risks retained: trusted Python composition/Core host and signing keys remain
trusted; OS routing/firewall and production trust-store operations require UAT.
Webhook automation currently permits published agents with **empty tool grants**.
That restriction remains: a webhook cannot select an HTTPS-enabled agent to expand
its authority. HTTPS-enabled automation requires a separately reviewed extension.

## Request, approval and credential contract

Trusted composition supplies an explicit HTTPS origin allowlist to the existing
coordinator (`https_endpoints`, empty by default). Current human organization-admin
`tool:register` authority is required to register an HTTPSConnectionDefinition.
Scope and owner must match the authenticated context. No public registration API,
environment secret discovery or model-to-client path exists.

The supported slice is one reviewed GET route ending in `{key}` (default
`/records/{key}`), no request body and no query string. Proposal input is exactly
`{"key": "..."}`: ASCII lowercase letters/digits/hyphens, length 1–64. Transport
rechecks the entire identifier and applies canonical encoding. Unknown fields,
URLs, host/scope/header/auth selection, path separators, percent-encoding and
control characters are denied. Route segments cannot contain traversal or query
syntax. Authorization, Host and HTTP method are authored by the adapter.

Approval binds organization, project, owner, connection/tool identity, canonical
origin, route/method, input/output schemas, limits, DNS answer set, TLS trust hash,
random binding ID and keyed credential identity. Core signs the exact approval.
AgentVersion metadata pins the hash, and changing endpoint, schema, trust,
credential or approval invalidates the old published pin.

Synthetic/temporary bearer credentials enter only trusted registration as SecretStr,
32–256 ASCII token characters. They are held only in memory. Revocation removes the
binding; rotation requires revoke/register and creates a new hash. TTL is at most
300 seconds and an observation older than 60 seconds denies use. Restart never
restores approval or credentials. Retained diagnostic redaction values deliberately
outlive revocation within the process so late errors cannot disclose old secrets;
Python does not promise memory zeroization. Per-Core retained protection values
are bounded and registration fails closed at capacity. No plaintext credential is
written to SQLite, PostgreSQL, a file, prompt or evidence. Persistent storage needs
a separately approved OS keychain/Windows secure storage/cloud secret manager design.

## Physical transport and SSRF

1. Parse an exact lowercase ASCII HTTPS origin with explicit port. Reject userinfo,
   trailing dot/case aliases, noncanonical IP notation, encoded/scoped hosts,
   control characters, fragments, query, paths and ambiguous URL syntax.
2. Require exact operator allowlist membership **before DNS**. Resolve A/AAAA under
   the operation timeout; every returned address must be public and safe. Reject
   private, loopback, link-local, reserved, shared, multicast, unspecified, metadata
   and IPv4-mapped/transition/NAT64 address ranges. Pin the full approved answer set.
3. Before each invocation, resolve again. A changed set is DENY, including a change
   to another public IP. Reauthorize after resolution and before physical connect.
4. Connect directly to the selected numeric approved address with a nonblocking
   socket, without a hostname resolver or proxy transport at connect time. Check
   actual peer address/port. No alternate address, retry, redirect or fallback.
5. Reauthorize before TLS and before HTTP write. Verify the server certificate
   against the trusted CA set and original hostname; minimum TLS 1.2. Disabling
   certificate/hostname verification or changing trust configuration is DENY.
6. Reauthorize after response validation and again at Core readback before model
   continuation. Cancellation and deadline cleanup close the socket; no success
   receipt is created for an incomplete exchange.

An explicit monotonic operation deadline is checked after synchronous Core
reauthorization and before each socket/TLS/HTTP dispatch, in addition to asyncio's
overall timeout. A slow authorization callback cannot postpone GET beyond the
adapter deadline simply by preventing the event loop timer from running.

The production HTTPSTrust class contains **no private-network bypass option**.
`tests/https_fixture.py` owns a narrow subclass accepting only literal `127.0.0.1`
at the configured fixture origin, with a freshly generated synthetic test CA.
No production environment variable enables that exception. The test socket guard
rejects any connect outside the fixture port. Test trust is supplied only through
trusted Python composition; arbitrary Python mutation is outside the model threat
boundary. Production non-loopback dispatch has not been exercised.

This is application socket enforcement, not proof about OS NAT, kernel compromise,
transparent interception, custom network translation or production firewall rules.
Such operating-environment guarantees need deployment/network UAT. A changed DNS
answer cannot redirect the numeric socket. DNS resolver work may finish in its OS
thread after cancellation, but cannot cause HTTP dispatch.

## Response and signed evidence

The deliberately narrow HTTP/1.x response profile requires status 200, one bounded
Content-Length and JSON Content-Type (`application/json`, optionally UTF-8).
Redirects, HTTP errors, duplicate/ambiguous headers, transfer encoding/chunked
framing, absent length and compressed bodies are denied. Compression is never
decoded. Headers are limited to 8 KiB/64 fields; body defaults to 16 KiB and has a
32 KiB hard maximum. Async transport receive buffers are bounded separately by
the stream reader/OS; the application never accumulates an unbounded response.
One operation has a maximum five-second overall timeout, one GET, at most twelve
attempts/minute/connection and 128 retained invocation identities. Failed attempts
consume quota. No token/cost usage is fabricated for the HTTP operation.

Strict JSON rejects duplicate keys, malformed content and nonfinite values;
existing schema validation rejects external references and requires exact
organization/project constants and no extra output properties. Credential-bearing
or sensitive-key output is denied before continuation. Response text stays in a
tool-result data message. It never changes grants; a model following injected
instructions still receives Core DENY for an ungranted proposal. Final output must
meet the existing version output contract. Exact model and a stable provider
identity are checked across governed turns; fallback cannot become verified success.
A final model turn without a tool proposal has no HTTPS action or provenance;
run completion alone is never evidence of HTTPS connectivity.

Core signs the invocation including run/trace/scope, call ID/number, binding,
input digest and authoritative deadline. Actual validated TLS exchange creates an
in-memory digest receipt. Core consumes it and verifies all returned provenance
before writing the existing authenticated `core.tool.result` audit event. Evidence
contains run/trace/scope, connection/tool identity, binding/schema/endpoint/target/
invocation/input/output hashes, raw response digest, status, verified TLS,
validation/policy, byte/request counts, measured duration and timeout. Endpoints,
DNS addresses, routes, response body and credentials are omitted. Signed run
evidence and history verification remain unchanged. No actual dispatch/valid
response/receipt means no successful tool evidence or verified continuation.

## Webhook integration

Existing hosted transport/session boundary, scoped bearer credential hashes,
rotation/revocation, timestamp ±300 seconds, strict bounded event schema, durable
deduplication and automation approval/scope checks remain in place. The event can
only signal the previously reviewed target and fixed input. It cannot supply
permissions, project, agent/workflow selection or tool grants. Paused, revoked or
changed configuration/owner denies dispatch. Recovery uses the existing signed
occurrence and Core idempotency/fencing; a completed duplicate does not run again.
No provider-specific webhook or authentication schema is added.

## Verification and readiness

Local verification completed on 16 October 2026 on Windows, Python 3.12.12,
OpenSSL 3.5.5 and disposable PostgreSQL 16.13. HEAD remains the audited baseline;
all implementation changes are uncommitted. The four completed Windows runs bind
to the same current Python source digest:
`cb0a69bfff8bea5f7a0c501f3d174abb297b84c1da4403ca5b8407b92ddd14cd`.

| Actual verification | PASS | FAIL | SKIP | Evidence / qualification |
|---|---:|---:|---:|---|
| Windows backend shard 1/4 | 354 | 0 | 2 | 356 selected |
| Windows backend shard 2/4 | 355 | 0 | 1 | 356 selected |
| Windows backend shard 3/4 | 354 | 0 | 2 | 356 selected |
| Windows backend shard 4/4 | 356 | 0 | 0 | 356 selected |
| Complete Windows backend | **1419** | **0** | **5** | 1424 unique identities; exact JUnit/selection match, disjoint union, identical current source hash |
| HTTPS Core/Factory/Bench integration | 56 | 0 | 0 | Included in backend total; actual TLS server/GET and model doubles |
| HTTPS security boundary | 86 | 0 | 0 | Included; DNS/IP/alias/redirect, TLS, proxy, TOCTOU, deadlines, credential isolation |
| Existing MCP baseline | 63 | 0 | 0 | Included; no test removed |
| Governed execution / capability probe | 103 | 0 | 0 | Included |
| Webhook security | 20 | 0 | 0 | Included; existing ingress and recovery regression |
| Installed native Hermes boundary | 1 | 0 | 0 | Included; network-denied model doubles, HTTPS declaration/continuation added |
| Full PostgreSQL integration | 143 | 0 | 0 | Real restricted writer, migrations, signed history, webhook and HTTPS persistence |
| PostgreSQL admission recheck | 6 | 0 | 0 | After shared-registry compatibility adjustments; repeats existing cases |
| PostgreSQL HTTPS transport recheck | 1 | 0 | 0 | After final synchronous-deadline guard; repeats HTTPS case |

Subset/recheck rows are **not additive** to full totals. The full PostgreSQL run
preceded the last adapter-only deadline hardening; its affected HTTPS persistence
case was repeated successfully afterward. Linux and remote CI were not run for
this uncommitted implementation.

The five unchanged skips are explicit:

- `tests/e2e/test_smoke_end_to_end.py::test_live_end_to_end_smoke`: live inference requires owner opt-in.
- `tests/integration/test_agent_lifecycle_workflow.py::test_live_hermes_assigned_research_agent_run`: live inference requires owner opt-in.
- `tests/integration/test_hermes_adapter_integration.py::test_live_hermes_run_lifecycle_and_cancellation`: live inference requires owner opt-in.
- `tests/integration/test_hermes_adapter_integration.py::test_live_hermes_health`: no local Hermes `API_SERVER_KEY` supplied.
- `tests/integration/test_hermes_adapter_integration.py::test_live_hermes_capabilities_and_confinement`: no local Hermes `API_SERVER_KEY` supplied.

Actual local orchestration commands (helpers and evidence are ignored under `.local`):

```powershell
.venv/Scripts/python.exe -u .local/run_https_backend.py 1
.venv/Scripts/python.exe -u .local/run_https_backend.py 2
.venv/Scripts/python.exe -u .local/run_https_backend.py 3
.venv/Scripts/python.exe -u .local/run_https_backend.py 4
.venv/Scripts/python.exe .local/verify_https_results.py
.venv/Scripts/python.exe -u .local/verify_https_postgresql.py
.venv/Scripts/python.exe -u .local/verify_https_postgresql.py tests/postgresql/test_https_persistence.py tests/postgresql/test_webhook_persistence.py tests/postgresql/test_hosted_persistence.py::test_mcp_duplicate_and_stop_fencing_with_restricted_writer tests/postgresql/test_hosted_persistence.py::test_mcp_protocol_signed_settlement_and_replay_with_restricted_writer
.venv/Scripts/python.exe -u .local/verify_https_postgresql.py tests/postgresql/test_https_persistence.py
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe scripts/check_repository.py
.local/quality-tools/actionlint.exe
uv lock --check --offline
.venv/Scripts/python.exe .local/audit_https_dependencies.py
.venv/Scripts/python.exe scripts/check_dependency_audit.py .local/https-python-audit.json
.local/quality-tools/gitleaks.exe git . --redact --log-opts=--all --report-format json --report-path .local/https-history-secrets.json
.local/quality-tools/gitleaks.exe dir .local/https-source-scan --redact --report-format json --report-path .local/https-source-secrets.json
```

The backend helper invokes the unchanged repository selector with
`-m "not postgresql" --backend-shard=N/4 -v --durations=15 -o faulthandler_timeout=120`
and independent JUnit output. The verification helper checks every selected
identity against its actual JUnit case, source digest and complete disjoint union;
it never fabricates a Linux report. Full manifests, per-shard XML/logs and
`.local/https-verification.json` are review evidence, not a Validated Delivery Artifact.

Ruff, actionlint, repository hygiene/diff and offline lock validation PASS. Gitleaks
found no leaks in 81 Git commits or the 19 new/modified source files. No dependency
or lockfile changed. The initial archived dependency report was rejected by the
existing inventory verifier because it omitted packages; no gate was weakened.
The completed offline audit uses the existing `pip-audit` PyPI evaluator and JSON
formatter over **86/86 exact-version cached responses**, with all socket/DNS
operations prohibited. The repository inventory verifier then PASSed for all 87
installed distributions (ARYN is the allowed local editable-project skip).
No vulnerabilities appear in those responses. Their source dates are
15 October 2026, 10:30:10–10:30:16 UTC (17:30 Bangkok). This proves cached advisory
coverage, **not a fresh advisory lookup**. Cache provenance is recorded in
`.local/https-advisory-cache.json`; results in `.local/https-python-audit.json`.

All tests use synthetic credentials, model doubles and local fixtures. The outbound
HTTPS test performs a real certificate handshake and GET through loopback sockets.
Existing hosted webhook TestClient checks are ASGI transport tests, not a claim of
internet ingress TLS deployment. Native Hermes uses network-denied HTTP doubles.

External API connectivity, live inference, OAuth, production credential storage,
operating-environment network enforcement and remote CI on these changes remain
unverified. Offline implementation is distinct from validated delivery: delivery
requires owner-approved commit/push, all Actions on that SHA and its Validated
Delivery Artifact. No production-ready or delivery-complete claim is made here.

| Area | Status |
|---|---|
| Secure HTTPS read-only adapter | VERIFIED — controlled TLS fixture |
| Core-governed authorization | VERIFIED — offline |
| SSRF enforcement | VERIFIED — application socket guard and fail-closed offline negatives; production network UAT outstanding |
| Credential isolation | VERIFIED — temporary synthetic bindings |
| Webhook integration/regression | VERIFIED — existing engine and existing target restrictions |
| Offline end-to-end execution | VERIFIED |
| External API connectivity | NOT VERIFIED |
| OAuth provider integration | NOT VERIFIED |
| Remote CI | NOT RUN |
| Milestone B overall | COMPLETE — OFFLINE IMPLEMENTATION COMPLETE only |

The table records the offline review checkpoint before owner-authorized commit/push.
Subsequent delivery must be verified against the pushed SHA and its GitHub Actions
artifact. No deployment, live inference, real API/credential, OAuth integration or
Milestone C was performed.
