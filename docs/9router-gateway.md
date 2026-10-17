# ARYN: Hermes runtime, gateway model 9Router

## Current working-tree consolidation — 17 October 2026

The `main` baseline is `024dd77a833c7fd865944a1206c98e3b5421e399`.
The single production model path, removal of legacy provider adapters, volatile
connection lifecycle, native capability matrix and Core-governed worker are
described in [runtime control plane](runtime-control-plane.md). Actual local
results and remaining exact-commit CI requirements are in
[runtime consolidation verification](runtime-consolidation-validation.md).
The dated sections below retain their historical baselines and source findings.

## Official isolation controls and unresolved delivery gates — 15 October 2026

The owner explicitly declined live inference and requested a source-only blocker
review. The actual baseline remains `development` at
`4994a6cc49f95deec0e2fe5b8608b0ca6e32a489`, with 23 modified existing tracked files.
No application/test source changed in this follow-up. The 21 modified non-Markdown
files match the saved SHA-256 snapshot in
`.local/ai-engine-verification/provider-preflight-20261015/source-state.json`.
Actual final JUnit identities and selection manifests still agree on 1208 distinct
backend cases: 1203 passed, 5 skipped. The same-source PostgreSQL report has 6
passed; the pinned-Node frontend execution JSON has 125 passed. These are retained
execution results, revalidated against current source, not newly executed live or
remote tests. The previous failing native subprocess reports remain retained.

Read-only review of installed 9Router **0.5.91** found the following supported
controls and limitations. No endpoint request, settings mutation, user credential access,
provider request or second gateway process was used to perform this audit.

| Control / installed source | What it actually controls | Remaining limitation |
|---|---|---|
| README Docker example; server data-directory code in `chunks/3726.js`; CLI client `src/cli/api/client.js:getDataDir` | `DATA_DIR` selects separate storage. CLI `--host` and `--port` select bind address and port. | An invalid/unwritable data directory can fall back to default storage. Verify the effective directory before any account configuration. These controls do not cap inference attempts. |
| `cli.js:killAllAppProcesses`, called before server startup | Stops matching 9Router/Next processes and performs MITM/tunnel cleanup. CLI PID cleanup uses the default user app directory. | A second CLI invocation on this host can disturb existing processes even with another port/data directory. Prefer a separately approved disposable VM/container with no user data mounts, rather than assuming a second local CLI is isolated. Nothing was started here. |
| Authenticated provider update handler, module 98244 in `app/api/providers/[id]/route.js` | `isActive` allows disabling individual connections. | Exactly one active approved connection in isolated storage removes alternate-account candidates; it does not disable retries of that connection, inline credential refresh or endpoint fallback. No existing connection was changed. |
| `chunks/4572.js`, module 80238 credential selector | `providerStrategies[provider].fallbackStrategy` / global `fallbackStrategy`, with `fill-first` or `round-robin` selection and sticky round-robin limits. | These are account-selection strategies, not a failure-rotation off switch. The chat loop calls the selector without its optional `preferredConnectionId`; that preference is not an enforceable client pin on this route. |
| `app/src/sse/services/backgroundTokenRefresh.js`; compiled `chunks/4037.js` | Official `DISABLE_BACKGROUND_TOKEN_REFRESH=1` prevents this scheduler from starting. | It does not disable on-demand refresh in an inference request. It is only a proposed setting for a separately approved isolated environment. |
| Settings PATCH module 20617; `quotaAutoPing.js:configureQuotaAutoPing` | Per-connection auto-ping maps, including `claudeAutoPing` / `codexAutoPing`, control scheduled quota pings. Empty/false connection maps stop that scheduler. | Current maps are UNKNOWN. Disabling that scheduler would not disable other discovery, refresh or inference paths. No settings PATCH was sent. |
| `chunks/2132.js`, module 41004 | `FETCH_CONNECT_TIMEOUT_MS` configures a per-attempt fetch connection timeout; installed default is 60000 ms. | This is not a whole-run deadline or retry-count control. The executor clears its timer after fetch resolves; it cannot prove cancellation or a billing ceiling for all upstream work. |
| `chunks/700.js`, module 74957 `execute` | Retry configuration merges static defaults with provider executor configuration. Defaults allow three additional attempts for 502/503, two for 504, and none for 429; network failures use the 502 branch. | No consumed official setting/request field for disabling all inference retries or limiting total upstream requests was found in the audited chat path. Settings PATCH accepting an arbitrary key would not make that key effective. |
| Shared `getBaseUrls` / `getFallbackCount`, generic runtime transport and provider-specific executors | Base-URL lists and selected provider transport determine endpoint fallback. | No uniform official client control disabling every provider's base-URL fallback was found. A single verified endpoint removes alternate endpoints for that particular path, not retry/refresh logic. Saved transport and endpoint overrides are UNKNOWN. |
| `chunks/7220.js:buildModelsList` / model GET handler | Some active-provider catalog paths perform dynamic discovery and credential refresh. The skip-dynamic option does not cover every provider path. | A gateway model listing is not universally an offline/local-only operation. Any later authorized probe plan must account for its discovery/refresh traffic as well as inference attempts. No model GET was sent here. |

Thus storage/account isolation is possible through existing official mechanisms,
but **zero retry / zero endpoint fallback / a trusted total upstream request cap
is not established for this installation**. Even the shared executor can make
four attempts on one URL under its three-retry defaults. This observation is not
an aggregate cap: account count, refresh re-execution and provider-specific loops
also matter. Two Core model dispatches must not be presented as two upstream
requests. Native Hermes and ARYN still have zero automatic alternate-model
fallback; the gateway's additional behavior is a distinct boundary.

### Provenance boundary and safe engineering choices

Core can sign its claim, observed tool proposal/decision/result, continuation,
output hash, usage as reported by runtime, and probe receipt. The runtime binding
binds the ARYN gateway URL/credential scope and runtime instance. It does **not**
identify the gateway's private provider configuration or chosen account. Hashing
the installed package, catalog or a user-written configuration label would not
repair that gap.

The missing evidence lies between the 9Router provider executor and its normalized
completion/catalog responses: some converters can synthesize model/usage fields,
and the installed server chunks contain no `provider_configuration` contract.
Neither a matching echoed model ID nor a Core signature proves raw upstream
identity, measured usage origin or a configuration revision that was never
reported. Existing `ModelProbeEvidence.live_eligible` and
`NineRouterGateway._verified_tool_probe` therefore remain strict; `supported` is
not issued from missing metadata, isolated doubles or an invented revision.

Safe next choices require separate owner review:

1. Restore authorized metadata access through the administrator responsible for
   the saved/managed origin policy on `http://127.0.0.1:20128`. Dashboard login and
   an earlier owner confirmation did not remove the actual denial. No alternate
   browser, hostname, direct HTTP client or CLI token is used as a workaround.
   Alternatively, the owner can provide a nonsecret metadata export from an
   authorized environment. An export supports preflight only, not live attestation.
2. Prepare an approved disposable gateway environment, pin the audited artifact,
   use empty separate storage and one owner-configured approved account, prevent
   unrelated schedulers, and verify the effective route/settings. Do not copy the
   user's credential database or launch the CLI against existing host processes.
   This narrows uncertainty; it does not by itself create an upstream cap or
   trustworthy provenance. No environment was provisioned in this follow-up.
3. Obtain an official gateway contract or reviewed upstream enhancement covering
   a per-request attempt/account/endpoint limit, preserved output limit, deadline
   propagation, and authenticated execution receipts. Receipts need raw upstream
   model/provider, effective nonsecret configuration revision, actual subrequest
   count and usage origin, bound consistently to catalog and completion evidence.
   ARYN's existing adapter can consume valid evidence; no second router, proxy,
   authority or synthetic attestation is proposed here. No installed source was
   patched. Provider-specific behavior must be covered, not just the shared loop.
4. If the owner later accepts an explicitly bounded ARYN-side diagnostic with
   unknown upstream cost/attempts, functional success could be reported separately
   from attestation. This would not close verified-capability acceptance. Such
   inference and any credential refresh/persistence it could cause remain unapproved.

### Multi-provider live plan, not authorized or dispatch-ready

No provider currently qualifies for an unconditional testing order. First restore
authorized metadata, then rank routes by preserved limits and provenance; choose
one exact route explicitly. Alternatives require their own approval and Core
claim. These are owner-requested candidates, not freshly confirmed catalog entries:

| Candidate exact ID | Stock source mapping, not actual provider proof | Availability / tool / structured output | Current gate |
|---|---|---|---|
| `ds/deepseek-flash` | DeepSeek route | UNKNOWN / UNKNOWN / UNKNOWN | Current catalog, endpoint/account, request bound and provenance unverified. |
| `ag/gemini-3.8-flash` | Antigravity route | UNKNOWN / UNKNOWN / UNKNOWN | Same gates, plus provider-specific 429/base-URL behavior and output transformation review. |
| `cx/gpt-6-luna` | Codex route | UNKNOWN / UNKNOWN / UNKNOWN | Same gates; current executor removes output-token limit fields, so excluded from a plan promising a preserved 128-token upstream limit. |

For a later explicitly approved eligible candidate, use only the existing Core
`verify_model(..., mode="tool_calling")`: fixed synthetic prompt and schema,
`aryn_fixture_lookup({"key":"aryn-core"})`, maximum one fixture call, two ARYN
inference dispatches, 128 requested output tokens per turn, 4096 measured total
tokens and a maximum 60-second Core deadline (subject to tighter existing limits).
No private project data is included. Current proposed gateway ingress remains
`http://127.0.0.1:20128/v1/chat/completions` through confined Hermes; actual runtime
binding, upstream provider/endpoint and configuration are UNKNOWN. Maximum total
upstream requests and potential cost are **UNKNOWN**, and these Core limits are
not a provider billing cap. No automatic retry, model substitution or alternate
candidate invocation is authorized on the ARYN side.

Expected evidence remains a genuine structured proposal with valid call identity,
Core authorization, verified fixture output, continuation and schema-valid JSON,
available usage and signed Core evidence. Gateway identity/configuration/usage
origin must be separately trustworthy before VERIFIED CAPABILITY can be claimed.
Without that evidence the strongest functional outcome is **FUNCTIONAL SUCCESS /
ATTESTATION INCOMPLETE**. No live functional outcome has been observed here.

Delivery review covers all 23 existing modified files, with no newly discovered
ARYN defect requiring application changes. Exact IDs, immutable versions, signed
history, permission/claim/budget ownership and Bench authority remain unchanged.
This follow-up updates only this existing documentation. Offline implementation
remains COMPLETE for the accepted tested scope; live verification is BLOCKED;
remote CI execution is BLOCKED pending explicit commit/push authorization; Stage 1
remains PARTIAL. No commit, push, deployment or paid/provider inference occurred.
Current follow-up checks passed: `.venv/Scripts/python.exe -m ruff check .`,
`.venv/Scripts/python.exe scripts/check_repository.py`, `git diff --check`, and
`git diff --no-ext-diff | .local/gitleaks/gitleaks.exe stdin --redact --no-banner`.
The redacted scan found no leaks in the tracked diff. Since application/test hashes
are unchanged, the accepted same-source regressions were not rerun solely for this
documentation update. Remote CI has not tested these uncommitted changes.

## Provider preflight and delivery audit — 15 October 2026

This follow-up rechecked `development` at
`4994a6cc49f95deec0e2fe5b8608b0ca6e32a489` with 21 modified tracked files. Prior
results were not assumed to verify the current tree. No live inference, provider
credential access, configuration change, commit, push or deployment is authorized.
The installed package reports 9Router 0.5.91; current dashboard metadata is blocked
by a saved browser origin permission for `http://127.0.0.1:20128`. After the owner
confirmed that the permission was opened, the same authorized browser access
was retried once and again denied by saved permission/managed policy.
No alternate transport is used to bypass it. Current configured connections,
catalog membership of the three candidate IDs, authentication/credit, custom
endpoints and configuration revision therefore remain UNKNOWN. The 50-route
observation below is historical, not current preflight evidence.

Read-only source audit examined the installed public server bundle under
`C:/Users/User/AppData/Roaming/npm/node_modules/9router/app/.next-cli-build/server/`.
These are stock source behaviors, not proof that a particular user setting is active:

| Boundary / source symbol | Observed behavior | Consequence |
|---|---|---|
| `chunks/6249.js`, module 40669 `g`/`i`; `chunks/8635.js`, module 38775 `i`/`j` | Explicit slash IDs parse a provider token and model; unprefixed aliases can consult saved mappings. Slash routes bypass named combo lookup. Public provider definitions map `ds`, `ag`, `cx`, but saved overrides are not inspected. | Keep exact slash ID; actual connection/endpoint still needs metadata. |
| `chunks/8635.js`, module 17603 `l`; `chunks/8910.js`, module 18910 `n` | Capacity routing is driven by vision/PDF/audio/video inputs. | The fixed text-only fixture payload does not request these adaptations. This is not a universal fallback guarantee for arbitrary requests. |
| `chunks/8635.js`, module 79489 `A` | Loops over available accounts; failures can select another account of the resolved provider. | Connection count and effective account strategy are unknown; two ARYN POSTs do not bound upstream attempts. |
| `chunks/700.js`, module 74957 `execute`; `chunks/2132.js`, module 41004 defaults | Per-base-URL retry; defaults allow 3 retries for 502/503, 2 for 504, 0 for 429; network errors use the 502 branch. Provider overrides apply. | Even one account can issue multiple upstream inference requests. This is distinct from generic HTTP-library retry defaults. |
| `chunks/8895.js`, module 92500 `N`; `chunks/3943.js`, module 8521 `K` | 401/403 may refresh credentials, with up to three refresh attempts, then invoke the executor again. | Inference may indirectly refresh provider credentials and persist refreshed state. Read-only preflight does not invoke this code. |
| Public Antigravity definition; executor module 39536 | Provider-specific 429 retries and base-URL fallback logic. | Additional retry/endpoint uncertainty; current account configuration unknown. |
| `chunks/5330.js`, module 19932 Codex executor | Additional transient SSE retries; removes `max_tokens`, `max_completion_tokens`, `max_output_tokens`; can normalize model/reasoning identifiers. | `cx/gpt-6-luna` is BLOCKED for a proposal promising an enforced 128-token provider output cap. Do not silently substitute a route. |
| `chunks/8895.js`, modules 5016/81626 response conversion | Some paths reconstruct completion/model/usage fields; e.g. a response model can fall back to the requested model. | An equal response ID alone is not independent proof of raw upstream identity or provider-measured usage. |
| Entire installed public server chunk set | No `provider_configuration` receipt field found; current ARYN requires it in catalog and completion with explicit provider provenance. | Gateway capability limitation: functional success cannot become authoritative supported capability without trustworthy configuration/model/provider/usage evidence. |

Public endpoint defaults include DeepSeek
`https://api.deepseek.com/chat/completions` and Codex
`https://chatgpt.com/backend-api/codex/responses`. They are not attested current
endpoints. Native Hermes revision was rechecked as
`3637c512fc3211bdccb61b7140d09ac1018508ba`. Only 9Router was listening during
initial inspection (port 20128, all interfaces); ARYN runtime/API ports 8642/8710
were not listening. No listener/configuration was changed. Live runtime session
authentication therefore remains unavailable; installed-native offline tests use
isolated authentication and outbound-denied doubles.

Blocker classification: missing gateway receipt/provenance is **B**; blocked
metadata and stopped runtime are **D**; multiplied upstream requests, token
transformation and continued work after a Core deadline are **E** uncertainties.
No live request has tested a model, so no **C** provider tool-support failure is
asserted. Unknown evidence is not repaired by inventing a revision or relaxing
exact identity. A safe gateway extension would need bounded dispatch/cancellation,
explicit route/account policy, configuration revision, raw upstream model/provider,
usage origin and subrequest evidence; it requires separate review/authorization.

The conditional live proposal below remains unapproved. Current readiness does
not justify an unconditional provider order: first refresh authorized metadata;
then prefer a route with preserved token parameters and sufficient provenance.
DeepSeek is a conditional diagnostic candidate because its stock OpenAI-compatible
path has fewer conversions, not a required dependency. Antigravity is a conditional
alternate after its retry/token behavior is established. Codex is excluded from
the bounded-output proposal until its output-limit contract is resolved. Successful
tool proposal → Core fixture → continuation → schema output with missing identity
or configuration provenance must be labeled **FUNCTIONAL SUCCESS / ATTESTATION
INCOMPLETE**, never VERIFIED CAPABILITY. Strict identity mismatch remains failure.

The current proposal is conditional; no provider is eligible for immediate live
dispatch while the metadata policy gate remains blocked:

| Field | Current proposal/evidence |
|---|---|
| Provider | Actual provider UNKNOWN; installed stock mappings identify DeepSeek and Antigravity routes only. |
| Exact model ID | Primary candidate `ds/deepseek-flash`; alternate candidate `ag/gemini-3.8-flash`. Both are requested candidates, not freshly confirmed catalog entries. `cx/gpt-6-luna` is excluded due to output-cap removal. |
| Availability / tool / structured output | UNKNOWN / UNKNOWN / UNKNOWN for both candidates; no live invocation or truthful capability receipt exists from this audit. |
| Route | ARYN contract is private Hermes → `http://127.0.0.1:20128/v1/chat/completions`; effective runtime binding/session and actual external endpoint are not currently verified. |
| Internal retries | ARYN zero automatic retries; at most two ARYN model POSTs. Gateway retries/account refresh/rotation exist as described above; total upstream attempts UNKNOWN. |
| Fallback | Disabled in ARYN. Source excludes combo/capacity adaptation for these explicit slash IDs and the fixed text-only payload; gateway account/base-URL fallback still exists. Current saved configuration is UNKNOWN. |
| Provenance | Partial static source evidence; trustworthy actual provider/model/configuration/usage-origin attestation is missing. Equal or reconstructed IDs are insufficient. |
| Token/deadline budget | Core reserves a maximum 4096 measured total tokens; at most two turns, one fixture call, 128 requested output tokens per turn, deadline at most 60 seconds and further reduced by Core/runtime limits. This is not a guaranteed upstream token/billing ceiling. |
| Potential cost | UNKNOWN; no verified price/credit or total upstream request bound. No amount is represented as a spending cap. |
| Test data | Fixed synthetic prompt/system instructions, registered fixture schema, `{"key":"aryn-core"}`, returned fixture text, call ID and continuation; native static Hermes framing. No project/private data or provider credential in the model payload. |
| Expected evidence | Structured tool proposal, validated name/arguments/call ID, Core permission decision, one fixture effect, validated continuation JSON, available reported usage, signed Core run evidence; capability remains unknown if attestation is incomplete. |
| Approval | Separate owner approval of exact model, synthetic data, at most two ARYN dispatches and unknown upstream costs/retries. Any approval is conditional on restoring authorized metadata access and admission. No automatic alternate-model execution. |

An overly broad public bundle excerpt during audit included bundled OAuth client
constants. No user credential file/value was accessed or copied to the repository;
subsequent source output was restricted to selected audit fields. This limitation
is recorded rather than claiming all tool output was credential-free.

## Multi-provider discovery and presentation — 15 October 2026

`NineRouterGateway` remains the only gateway catalog. `ModelRouter` requires an
explicit exact selection, never a DeepSeek default or an automatic substitute.
The legacy standalone provider payload builders do not execute Studio requests.
No provider was added, configured or contacted for inference in this change.

The catalog separates `model_id` from `display_name`. The projection first ignores
rich metadata with sensitive field names (including nested credential fields) or
excessive nesting; it never inspects their values to infer readiness. For those
rows, labels come only from the ID and provider identity stays unknown. For other
rows, a bounded plain-text gateway `display_name`/`name` takes precedence.
Otherwise, deterministic presentation formatting
recognizes the existing 9Router route tokens `ds`, `ag`, `cx`, `gemini`, `openai`
only for IDs with one separator. Unknown/multiple namespaces remain intact.
These tokens describe presentation, never provider identity or authorization.
The installed 9Router 0.5.91 public provider definitions confirm these aliases;
they do not prove an active connection or the upstream model actually used.
Case-insensitive duplicate labels receive an exact-ID suffix. For example:

| Internal ID, unchanged | Display label |
|---|---|
| `ds/deepseek-flash` | DeepSeek Flash |
| `ag/gemini-2.5-pro` | Gemini 2.5 Pro |
| `ag/gemini-2.5-flash` | Gemini 2.5 Flash |
| `unknown/model-name` | unknown/model-name |

Chat/Factory/discovery already consume these API labels. The fixed Chat picker
also uses a matching catalog label, falling back to the historical ID if absent.
Option values, request bodies, immutable versions, run/Bench identities, signing
and historical evidence retain the exact ID. Evidence inspectors retain raw IDs.
No records are renamed and there is no migration.

Rows now expose `listed`, `provider_identity_status`, `provider_configured`,
`provider_reachability`, `credit_status` and `rate_limit_status` independently of
model availability. Configuration requires an explicit gateway boolean; absent
metadata is unknown. Reachability requires verified provider-discovery evidence
at most 60 seconds old. Neither configuration nor reachability proves model
availability, capability or credit. Credit/rate-limit metadata is unavailable in
the existing discovery contract and remains unknown. `owned_by` may be a routing
alias and is not treated as an upstream provider identity. Only bounded explicit
provider metadata is projected; raw provider configuration/errors are excluded.

Fresh gateway capability attestations additionally require an explicit provider
identity and configuration revision. Core probe receipts must match that current
catalog provider, exact reported model, gateway/credential scope, runtime instance,
configuration revision and expiry. Missing provenance leaves capability unknown.
Isolated doubles still cannot issue live attestations.

**Identity contract hardening:** transport no longer equates provider-prefixed
and unprefixed response model IDs using provider-specific heuristics. The actual
gateway response must equal the selected exact ID. Providers that report a
different ID are rejected, even if a human considers the names equivalent. An
eventual alias contract would need trustworthy model/configuration-bound evidence;
display formatting cannot authorize it. Existing historical evidence is preserved,
not rewritten. This deliberately tightens the previous namespace compatibility.

Provider failures remain sanitized and latched per turn. HTTP 429 is
`provider_rate_limited`; explicit `insufficient_credit` or `insufficient_balance`
codes produce `provider_insufficient_credit`; `insufficient_quota` is reported
separately as `provider_quota_exhausted`, without inferring its billing cause; 502/503/504
produce `provider_unavailable`. Other failures are not guessed to be credit
problems. These observations grant neither fallback nor retry. Core retains
`outcome_unknown` and reservations when settlement evidence is missing, along
with the bounded diagnostic code. A transient provider failure does not permanently
mark the model rejected. ARYN limits native dispatches; opaque gateway internal
retries and external billing ceilings remain unverified.

Read-only metadata refresh through the logged-in local dashboard was denied by
the browser origin approval gate during this audit. No alternative transport was
used to bypass it. Earlier observations listed 50 routes across configured
DeepSeek, Gemini, Antigravity and Codex connections, all with unknown model
availability. That observation is not current readiness evidence. Installed public
provider definitions corroborate routing aliases only. No live tool support,
credit, actual upstream identity or provider configuration revision is asserted.

### Conditional live verification proposal (not authorized or executed)

These are earlier observed catalog candidates, not freshly verified available
providers. Mapping comes from installed public gateway definitions plus the
earlier local connection metadata, not inference from a prefix alone. Current
connection state must be refreshed after owner permission for local metadata.
No model is substituted if its route fails.

| Gateway provider route | Exact model ID | Availability | Tool calling / structured output | Provenance |
|---|---|---|---|---|
| DeepSeek | `ds/deepseek-flash` | unknown | unknown / unknown | earlier catalog/configuration observation; actual upstream/configuration revision unavailable |
| Antigravity | `ag/gemini-3.8-flash` | unknown | unknown / unknown | installed route mapping; actual upstream provider/model/configuration revision unavailable |
| Codex | `cx/gpt-6-luna` | unknown | unknown / unknown | installed route mapping; actual upstream provider/model/configuration revision unavailable |

For each explicitly approved model:

- Route: Core → confined Hermes → `http://127.0.0.1:20128/v1/chat/completions`.
  Actual external endpoint is not verified. ARYN fallback is disabled; gateway
  internal routing/retry policy must be established before promising a bound.
- Caller: current human `model:verify` and `run:create`; a separate exact-model
  idempotency claim and budget reservation per approved probe.
- Dispatch: at most two ARYN-to-gateway model POSTs per probe, one per native
  turn, zero automatic ARYN retries; one Core fixture read. Approving all three
  candidates would permit at most six ARYN model POSTs, but they are not a batch
  default. External provider request counts remain unknown behind the gateway.
- Limits: 128 requested output tokens per turn, 4096 Core measured total-token
  ceiling, at most 60 seconds bounded further by runtime/Core deadlines. Provider
  input/reasoning accounting and opaque retries prevent a guaranteed billing cap.
- Data: only `TOOL_PROBE_PROMPT`, `TOOL_PROBE_SYSTEM`, the strict fixture tool
  definition, `{"key":"aryn-core"}`, Core-verified fixture text
  `ARYN Core owns execution authorization.`, call identity and continuation
  transcript. No project/private data or provider credential enters the prompt.
- Output: strict `{"summary":"ARYN Core owns execution authorization."}`.
  Inspect actual model/provider, measured usage, tool trace, signed evidence and
  current configuration revision. Missing provenance yields unknown, never an
  authoritative supported receipt. Identity mismatch rejects the probe.
- Costs/quotas: unknown. Configured accounts or a static pricing table do not
  establish remaining credit or actual charges. Separate owner approval of the
  exact candidate list, data, cost uncertainty and request-count uncertainty is
  required before any inference. Resolve metadata/routing blockers first.

## Explicit Core tool capability probe — 15 October 2026

`RunCoordinator.verify_model(..., mode="tool_calling")` is a server-only fixed
synthetic operation, separate from the existing default text probe. It requires
current human `model:verify` and `run:create` permissions. It does not grant tools
to an agent, publish a version, or add an API endpoint. Normal agent and Bench
admission still require verified model availability and tool capability.

Only this probe may test an exact listed candidate with unknown readiness. It
has one Core claim/reservation, at most two model requests, one
`aryn_fixture_lookup({"key":"aryn-core"})` read, and strict JSON summary
validation. Its fixed payload, two-turn/one-call limits, Core deadline and budget
are checked at both Core and the private runtime turn contract. Each native
Hermes turn still dispatches once, without native tool execution or retries.

Core signs the completed observation and retains its trace in the existing
audit/evidence records. Replay returns historical evidence without dispatch or
renewing its expiry. Failed/unknown/cancelled observations cannot issue a
capability receipt. A receipt lasts no more than 60 seconds and is checked again
against model, gateway URL/credential scope, runtime instance and the gateway's
provider configuration revision before reuse. Gateway/runtime restarts, model
removal/rejection, configuration changes, signature failure or expiry invalidate it.

The optional `provider_configuration` field is a SHA-256 configuration revision
reported by the gateway in both its model catalog and actual completion. ARYN
does not invent that revision or read 9Router's private provider credentials.
Missing provider identity or revision leaves live capability **unknown**, even
if the fixed fixture conversation completed. Current standard 9Router may omit
these fields; a successful probe alone is not proof of opaque upstream routing
configuration. No live support is claimed until actual evidence is observed.

Transport doubles are explicitly labeled `isolated_test_double`; unregistered
runtimes have no live attestation binding. Offline probe evidence remains
inspectable but cannot populate the live capability registry. The supported
structured-output observation is limited to the fixed fixture schema, not a
guarantee of arbitrary provider-native constrained decoding. Provider input and
cost admission retain the existing estimated/postflight limits, not a guaranteed
external billing ceiling. Live requests require separate owner approval.

Governed fixture extension (13 October 2026): `/aryn/turn` is an authenticated
private loopback proposal/continuation protocol; native toolsets remain empty
and native tool execution is forbidden. Core owns grants and all execution of
`aryn_fixture_lookup`. Each Hermes turn still permits one gateway dispatch.
See [the Core contract and limits](core-execution-hardening.md).

`ModelCapabilities` reports text, structured output and tool calling independently.
Catalog membership and `supports_tools=true` do not establish any of them.
Explicit capability fields require `capabilities_verified=true`, source
`provider_attestation` or `runtime_probe`, a Unix `capabilities_checked_at` age
of 0–60 seconds, and typed `supported`/`unsupported`/`unknown` values in
`capabilities`. A Core-settled text probe proves text generation only. Missing,
stale, rejected or malformed evidence remains unknown and governed tool runs are
blocked. Standard 9Router installations are not assumed to provide these fields.
No model probe, gateway configuration or credential change is performed by discovery.
The raw reported model identifier is retained in governed iteration audit while
exact response identity is required as described above. Provider identity is
unavailable if the provider does not report it; a gateway cannot prove a provider
that returns dishonest metadata.

Status Home/Chat V1.0 pada 11 Oktober 2026: percakapan nyata multi-turn memakai
`ds/deepseek-flash` telah diverifikasi melalui API/Core/Hermes/9Router. Consent
first-use memakai receipt Core tersimpan dan dapat dicabut, bukan checkbox setiap
percakapan. Provider downstream/local-only yang tidak diattest tetap tidak diklaim.
Bagian berikut mencatat tahap gateway sebelumnya; kontrak dan bukti terbaru ada
di [Home/Chat](chat-workspace.md) dan [validasi](../apps/web/VALIDATION.md).

Audit dan implementasi pada branch `development`, mulai dari
`c3dbd87368bbf9c22293b409ffd2ff84861fbc6d`. Tidak ada perubahan pada `main`,
Batch 2, Brief/Relay, instalasi/config provider 9Router, atau hardening Hermes.

## Akar masalah

1. Studio memakai katalog/default Nous statis. Kehadiran model pada daftar
   tersebut tidak membuktikan model dapat dijalankan. Router lama juga memiliki
   interface credential provider dan konfigurasi fallback.
2. Adapter membaca autentikasi dari `.env` Hermes, yang bisa berisi credential
   provider. Readiness runtime dan model belum dipisahkan dari gateway baru.
3. Hermes OpenAI-compatible endpoint dapat mengembalikan model yang diminta
   sebagai metadata response. Echo tersebut bukan bukti model aktual provider.
4. Run tersimpan belum memiliki field gateway, backend runtime, provider aktual,
   dan actual model terpisah. Metadata historis tidak boleh dikarang saat migrasi.

## Arsitektur dan batas credential

**Studio → ARYN API → Core → HermesRuntimeAdapter → Hermes native API/AIAgent
→ transport 9Router → provider.** Hermes tetap execution engine. ARYN tidak
melakukan inference sendiri dan tidak membaca/mengelola provider API key.

`services/runtime/hermes_9router.py` mengikat native `APIServerAdapter` dan
`AIAgent` dari instalasi Hermes yang ada. Model dan parameter berasal dari versi
Core, toolset harus sudah kosong, dan semua panggilan SDK memakai endpoint
gateway yang ditentukan. `.env` loader Hermes dinonaktifkan pada proses khusus
ini; file instalasi dan konfigurasi Hermes tidak diubah. Bootstrap menghapus
environment bernama `*_API_KEY` selain key 9Router tanpa membaca nilainya.

Transport membuang header SDK/config, lalu menyertakan hanya gateway auth
opsional. SDK Hermes menggunakan sentinel publik, sehingga credential gateway
asli hanya diketahui transport. Response upstream disaring sebelum masuk
Hermes: error body, credential, tool calls, response model berbeda, completion
tidak lengkap, dan usage inkonsisten ditolak. Rejection dilatch per turn untuk
mencegah retry/fallback melakukan panggilan model tambahan.

Receipt per request menangkap `requested_model`, `actual_model`, gateway,
backend, dan provider jika dilaporkan. Native Hermes API meneruskan receipt
terverifikasi sebagai `aryn` evidence. Worker thread mendapatkan receipt secara
eksplisit; request bersamaan tidak berbagi evidence. Run asynchronous menyimpan
receipt pada native durable run status. Core dan Bench tetap memverifikasi exact
model; echo-only response dari runtime lama ditolak.

Native `/aryn/gateway` membutuhkan runtime auth dan melaporkan binding endpoint
serta enforcement. Hermes lama yang belum memakai launcher ini gagal pada gate
binding. Browser hanya memanggil API Studio; CSP `connect-src 'self'` tetap aktif.

## Discovery dan fail closed

ARYN server membaca **GET `${ARYN_9ROUTER_BASE_URL}/models`**. Tidak ada katalog
Nous/default model di Studio. Response disaring menjadi `model_id`,
`display_name`, `gateway=9Router`, availability dan alasan. Kegagalan discovery
menghapus snapshot lama; model substitusi/fallback tidak digunakan. Combo dan
route non-LLM ditolak untuk governed execution.

Endpoint resmi 9Router bisa menghasilkan daftar dari tabel/default ketika
provider discovery tidak tersedia. Karena itu listing saja berstatus `unknown`.
`available` membutuhkan evidence eksplisit: `availability_verified=true`, source
`provider_discovery` atau `runtime_probe`, serta `availability_checked_at` berupa
Unix seconds dengan umur 0–60 detik. Tidak ada endpoint pemberian evidence dari
browser. Penolakan model oleh provider dilatch `unavailable` selama proses API
berjalan. Preflight selalu menyegarkan discovery; cache listing bukan izin run.

Tambahan Chat (10 Oktober 2026): endpoint standar 9Router tidak wajib menyediakan
field evidence tambahan tersebut. Model LLM dengan status `unknown` dapat dipilih
untuk **verifikasi pada saat kirim**, tanpa dilabeli `available`. Consent pengguna
mencakup biaya probe singkat. Core melakukan claim persisten `model_probe`, izin,
reservasi budget, deadline, audit dan idempotency sebelum Hermes mengirim prompt
verifikasi tetap, text-only, tanpa tool, ke satu model yang dipilih. Hanya hasil
Core `completed` dengan identitas gateway/runtime/model yang tepat dan usage
terukur menjadi evidence readiness selama 60 detik. Eksekusi chat normal tetap
melewati preflight `require_model_available`; claim probe gagal/unknown tidak
diulang dengan idempotency key yang sama dan tidak menerima pesan pengguna.
Discovery sendiri tidak memanggil inference. Combo, route non-LLM, model yang
ditolak, binding runtime tidak cocok dan input di luar katalog tetap ditolak.
Tidak ada pembacaan credential/database private 9Router atau silent fallback.

Verifikasi live Chat 10 Oktober 2026 berhasil untuk `ds/deepseek-v4-pro` dan
`ds/deepseek-flash`. Rute V4 Flash lama mengembalikan `deepseek-flash` sehingga
ditolak oleh pemeriksaan identitas; DeepSeek telah
[mengalihkan rute V4 Flash ke V4.1 Flash](https://api-docs.deepseek.com/updates/).
Setelah pengguna login, **Add Custom Model** pada dashboard 9Router mendaftarkan
ID resmi `deepseek-flash` pada provider DeepSeek existing. Publik `/v1/models`
sekarang menampilkan `ds/deepseek-flash`; kandidat lain tidak otomatis tersedia.
Tidak ada perubahan key/provider, grant, fallback, atau instalasi 9Router.
Tiga turn nyata Flash melewati API/Core/Hermes, menyimpan history dan usage,
termasuk follow-up setelah refresh. Lihat [bukti dan kontrak Chat](chat-workspace.md).

Residual pre-Batch-2 (7 Oktober 2026): pembacaan `_active_gateway_providers()`
terhadap database internal 9Router telah dihapus. `providerConnections.isActive`
dan alias provider bukan public contract dan bukan bukti exact-model availability.
ARYN tidak membaca database tersebut untuk credential atau availability.
Discovery API existing tetap digunakan; tidak ada probe/fallback/katalog yang
direka. Katalog tanpa evidence availability yang memenuhi pemeriksaan di atas
tetap `unknown` dan gagal pada preflight Bench/Run. Instalasi yang sebelumnya
dianggap tersedia hanya dari state provider lokal kini akan diblokir. Ini tidak
mengubah instalasi/config 9Router atau exact-model enforcement.

Seluruh default endpoint development didefinisikan hanya di `packages/config.py`.
`GatewaySettings` mengambil settings tersebut dan tidak membaca environment/default
sendiri. Ketiga launcher memakai resolver terpusat; non-development tanpa
konfigurasi endpoint lengkap ditolak sebelum start. `API_SERVER_KEY` tetap
process-only, acak jika belum ada, diwariskan ke Runtime/Studio, dan diabaikan
saat membaca `.env`. Lihat [hasil regresi residual](pre-batch2-residual-validation.md).

Pemeriksaan lokal read-only tanggal 6 Oktober 2026 menghasilkan gateway
terhubung, discovery valid, **49 kandidat, semuanya `unknown`**. Versi 9Router
lokal tidak memberi evidence readiness yang dibutuhkan pada `/v1/models`.
**Bench/Run live tetap diblokir.** Ini bukan PASS inference live. Tidak ada
inference probe berbayar, bypass availability, atau perubahan konfigurasi provider.

Readiness dipisah menjadi API Studio, ARYN Runtime, gateway, binding runtime ke
gateway, dan selected model. Bench memeriksa dependency sebelum empat skenario;
unavailable/unknown menghasilkan nol dispatch. Semantics evidence tetap:
4/4 verified = Lulus; gagal/skor <100% = Gagal; passing unverified = Tidak
Terverifikasi. Historical evaluation tetap tersedia untuk dibaca.

## Kontrak dan data

- Workspace API menyediakan `gateway`: koneksi, validitas discovery, reason dan
  `runtime_binding_verified`; daftar model berasal dari discovery server.
- RunResult menambah `requested_model`, `actual_model`, `gateway`,
  `runtime_backend`, `provider`. Audit completion menyimpan metadata yang sama
  beserta token dan Core run ID. Raw runtime response tidak diekspos.
- Migrasi `009_gateway_provenance` menambah nullable `actual_model`, `gateway`,
  `runtime_backend`, `actual_provider` pada `run_states`. Model existing tetap
  requested model. Data lama tidak dibackfill dengan provenance buatan.
- Hash/version, signature Bench, approval, publikasi, assignment, budget,
  atomic idempotency claim, ownership dan recovery tetap memakai Core existing.
- API menolak input yang mengandung credential runtime/gateway yang diketahui,
  termasuk JSON escaped. Error, discovery, metadata, dan response runtime
  disanitasi; credential tidak dimasukkan ke audit/DB/frontend/log aplikasi.

## Environment dan menjalankan aplikasi

`.env.example` hanya berisi:

```dotenv
ARYN_ENV=development
ARYN_9ROUTER_BASE_URL=http://127.0.0.1:20128/v1
ARYN_9ROUTER_API_KEY=
```

Environment dibaca server-side, bukan otomatis dari `.env`. Gateway key boleh
kosong jika 9Router tidak memerlukan auth. Jika diperlukan, berikan melalui
environment server; jangan memasukkannya ke frontend, database, Git atau log.
`API_SERVER_KEY` adalah auth **runtime**, terpisah dari provider/gateway key.
Launcher membuat key runtime acak sementara jika belum ada, tanpa menampilkan
atau menyimpannya. Launcher `start-aryn.ps1` memulai runtime dan Studio dalam satu proses PowerShell induk agar keduanya menerima autentikasi yang sama.

1. Jalankan instalasi 9Router yang sudah ada; jika belum aktif, `9router
   --no-browser` dari terminal tersendiri. Jangan ubah provider/config key.
2. Hentikan Studio lama melalui launcher existing. Hentikan Hermes lama melalui
   mekanisme yang digunakan untuk menjalankannya, bila masih memakai port 8642.
   Launcher baru menolak port terpakai dan tidak membunuh proses lain otomatis.
3. Jalankan launcher bersama:

```powershell
Set-Location D:\ARYN\aryn-labs\aryn
$env:ARYN_ENV = 'development'
$env:ARYN_9ROUTER_BASE_URL = 'http://127.0.0.1:20128/v1'
# ARYN_9ROUTER_API_KEY kosong untuk instalasi gateway tanpa auth.
.\scripts\start-runtime-9router.ps1 -CheckOnly
.\scripts\start-aryn.ps1
```

Runtime berjalan loopback 8642; Studio http://127.0.0.1:8710. Launcher runtime
memverifikasi kompatibilitas/confinement, menggunakan interpreter instalasi
Hermes, menjalankan background tersembunyi dan mengecek binding sebelum menyatakan
siap. Jika kebijakan PowerShell memblokir script, buka satu sesi dengan
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-aryn.ps1`.
Menjalankan runtime dan Studio melalui dua proses PowerShell terpisah dapat
kehilangan runtime auth sementara; Studio akan menampilkan alasan autentikasi
yang belum dikonfigurasi atau ditolak. UI memakai nama Model Gateway; identitas
9Router tetap tercatat pada kontrak dan dokumentasi teknis.

```powershell
.\scripts\stop-studio.ps1
.\scripts\stop-runtime-9router.ps1
```

Stop runtime hanya menargetkan PID/start time/command milik launcher. Penghentian
proses bukan bukti cancel berhasil; Core recovery tetap mencatat outcome unknown.
Runtime/Studio yang sedang berjalan saat audit tidak diganti atau dimatikan.

## Validasi otomatis

Semua model call otomatis memakai test double. Uji instalasi Hermes memakai
native engine dan HTTP SDK double dalam subprocess dengan HOME/config terisolasi;
tidak menggunakan database konfigurasi provider pengguna.

Hasil final yang benar-benar dijalankan:

| Gate | Hasil |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest -q` | **217 PASS, 5 SKIP**, 45,27 detik |
| Vitest pada file khusus commit | **33/33 PASS**, 6 file |
| Vitest working tree, termasuk test popup pengguna | **34/34 PASS** |
| `npx tsc --noEmit` dan `npm run build` | **PASS** |
| Playwright pada salinan khusus commit | **14/14 PASS**, 2,3 menit |
| axe seluruh halaman, dark/light, mobile/tablet, reduced motion | **PASS**, dalam Playwright |
| Native Hermes + SDK double: direct, concurrency, async durable evidence, mismatch, secret rejection | **PASS**, dalam pytest |
| Runtime launcher `-CheckOnly`, tanpa inference | **PASS** pada instalasi lokal |
| SQLite migration, foreign-key/integrity checks; PostgreSQL SQL offline | **PASS**, dalam pytest |
| Discovery/readiness, exact model, API/audit/DB/log secret leakage, no browser runtime access | **PASS**, dalam regression suites |

5 SKIP: tiga model-live test membutuhkan opt-in pemilik; dua pemeriksaan runtime
live memerlukan auth yang tidak tersedia pada environment sesi audit. Opt-in
membutuhkan `ARYN_RUN_LIVE_MODEL_TESTS=1` serta `ARYN_LIVE_MODEL` eksplisit;
variabel tersebut tidak ditambahkan ke contoh environment dan tidak diaktifkan
saat audit. Tidak ada default model pada test live.

Vitest/build/Playwright juga dijalankan pada salinan source khusus commit di
`.local/gateway-verification-0b6e00b8`, menggunakan Core/API/test database asli
repository dan runtime double. Salinan mengecualikan perubahan UI pengguna yang
belum di-commit; working tree pengguna tidak ditimpa. Satu assertion drag awal
membandingkan seluruh inline style dan gagal karena React Flow berpindah dari
hidden ke visible saat init. Tes diperbaiki agar menunggu node visible lalu
membandingkan transform node; pemeriksaan drag/connection read-only tetap aktif.

Warnings tersisa: deprecation Starlette/httpx, konfigurasi Alembic path separator,
dan ukuran JS bundle Vite >500 kB. Tidak ada error gate. Tidak ada perubahan
package/dependency untuk menyembunyikan warnings tersebut.

Bukti Playwright khusus commit: `.local/gateway-verification-0b6e00b8/apps/web/playwright-report`.
Command standar tetap sama dengan bagian pengujian pada `docs/studio.md`.

Referensi primary source yang diaudit:
[Hermes native API](https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server.py),
[konfigurasi model Hermes](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/configuring-models.md),
[9Router models endpoint](https://raw.githubusercontent.com/decolua/9router/master/src/app/api/v1/models/route.js).
Implementasi disesuaikan juga dengan source instalasi Hermes dan 9Router lokal.

## Tindak lanjut UAT: label dan autentikasi runtime (6 Oktober 2026)

UI memakai nama **Model Gateway** pada topbar, Pengaturan, canvas, dan pesan
kegagalan. Identitas 9Router tetap benar pada metadata run/kontrak dan dokumentasi
teknis. Tidak ada perubahan routing, schema, governance, atau credential boundary.

Saat pemeriksaan awal, proses Hermes hidup dan `/health` merespons, tetapi
readiness/binding ARYN belum terverifikasi. Launcher terpisah dapat kehilangan
`API_SERVER_KEY` sementara ketika dipanggil melalui proses PowerShell berbeda.
`start-aryn.ps1` memulai kedua layanan dari induk yang sama. API membedakan
`runtime_authentication_missing` dan `runtime_authentication_rejected`, tanpa
menampilkan key; runtime yang sehat tetapi belum terautentikasi tidak diklaim siap.

Sesudah pemeriksaan nol run aktif, layanan milik launcher dimulai ulang bersama.
Workspace aktual menunjukkan `runtime.ready=true`, `tools_confined=true`, seluruh
toolset nonaktif, serta binding gateway terverifikasi. Database lokal tetap
tersimpan: `PRAGMA integrity_check=ok`, nol pelanggaran foreign key. Endpoint
model gateway `/v1/models` kemudian timeout; katalog kosong dan Bench/Run tetap
fail closed. Runtime siap tidak dijadikan bukti bahwa gateway/model tersedia.

Regresi native Hermes awal menemukan probe metadata yang belum terisolasi dari
jaringan. Test kini memakai HTTP double untuk probe metadata dan SDK model,
serta memblokir socket keluar; pengecualian hanya socketpair internal asyncio
Windows. Penamaan sesi otomatis Hermes dapat mengirim request model tambahan;
jalur tersebut dinonaktifkan hanya pada proses khusus ARYN, tanpa mengubah
instalasi atau konfigurasi Hermes. Native integration tetap memeriksa exact model,
concurrency, evidence durable async, penolakan mismatch/secret dan jumlah panggilan.

Validasi akhir: backend **221 PASS, 5 SKIP** (54,40 detik); Vitest source khusus
commit **34 PASS**, working tree **35 PASS** termasuk popup pengguna; TypeScript
check dan production build **PASS**; Playwright/axe **14 PASS** (2,8 menit).
Test launcher memeriksa autentikasi sementara bersama, penerusan opsi, dan bahwa
Studio tidak dimulai setelah runtime gagal. Tidak ada inference live yang diklaim
PASS. Tidak ada push/merge ke main atau perluasan Batch 2.

## Residual limitation dan satu sesi UAT

- Inference provider live belum diuji dan tidak diklaim lulus. Current catalog
  unknown memblokir Bench/Run sampai ada evidence readiness authoritative.
- Prefix/alias 9Router bisa berbeda dengan canonical model response provider.
  ARYN sengaja menolak perbedaan tersebut; tidak melakukan normalisasi atau
  menyembunyikan fallback. Provider yang tidak melaporkan actual model ditolak.
- Bukti bergantung pada laporan model gateway/provider. Tidak dapat membuktikan
  identitas model bila gateway/provider mengembalikan metadata palsu.
- Binding memakai API internal native Hermes; upgrade Hermes perlu compatibility
  check dan regression native integration. Tidak ada trace runtime terstruktur
  untuk direct turn; audit Core tetap tersedia.
- Schema SQLite upgrade dan SQL PostgreSQL diuji; tidak ada integrasi PostgreSQL
  Cloud/live database. Stop/restart masih bisa menghasilkan outcome unknown
  untuk inference yang sudah diterima provider, tanpa retry otomatis.

UAT bersama: periksa runtime/gateway secara terpisah di Pengaturan, lihat katalog
aktual di Factory, pastikan unknown/unavailable memblokir Bench dan Run, serta
buka historical evaluation/run dan audit tanpa kehilangan data. Lifecycle live
passing sampai publikasi membutuhkan readiness evidence yang valid dan izin
inference eksplisit; jangan meluluskan gate hanya untuk mencoba UI. Setelah
commit batch ini berhenti untuk audit/UAT, tanpa otomatis memulai Batch 2.

## File dalam perubahan gateway

File existing Inspector hanya menyertakan nomenklatur dan metadata gateway.
Perubahan lokal pengguna pada full-text Inspector, CSS, dan test popup dipertahankan
dan tidak dimasukkan dalam commit ini.

- `.env.example`
- `README.md`
- `apps/web/e2e/studio.spec.ts`
- `apps/web/src/components/agent-flow.tsx`
- `apps/web/src/components/canvas/canvas-builders.ts`
- `apps/web/src/components/canvas/canvas-inspector.tsx`
- `apps/web/src/components/shared.tsx`
- `apps/web/src/components/version-form.tsx`
- `apps/web/src/features/factory.tsx`
- `apps/web/src/features/overview.tsx`
- `apps/web/src/features/runs.tsx`
- `apps/web/src/features/settings.tsx`
- `apps/web/src/lib/studio-state.ts`
- `apps/web/src/lib/types.ts`
- `apps/web/src/studio.tsx`
- `apps/web/src/test/gateway-readiness.test.tsx`
- `apps/web/src/test/studio-context.test.tsx`
- `apps/web/src/test/studio-fixtures.ts`
- `database/migrations/versions/009_gateway_provenance.py`
- `database/schema.py`
- `docs/9router-gateway.md`
- `docs/studio.md`
- `modules/core/workflows/coordinator.py`
- `packages/contracts/model.py`
- `packages/contracts/runtime.py`
- `packages/model_adapters/providers/gemini.py`
- `packages/model_adapters/providers/nous.py`
- `packages/model_adapters/router.py`
- `packages/model_adapters/gateway.py`
- `packages/runtime_adapters/hermes/adapter.py`
- `scripts/hermes-9router.py`
- `scripts/start-runtime-9router.ps1`
- `scripts/stop-runtime-9router.ps1`
- `services/api/studio.py`
- `services/runtime/__init__.py`
- `services/runtime/gateway_transport.py`
- `services/runtime/hermes_9router.py`
- `tests/e2e/test_smoke_end_to_end.py`
- `tests/gateway_fixtures.py`
- `tests/hermes_gateway_check.py`
- `tests/integration/test_9router_studio.py`
- `tests/integration/test_agent_lifecycle_workflow.py`
- `tests/integration/test_schema_migration_compatibility.py`
- `tests/integration/test_hermes_9router_binding.py`
- `tests/integration/test_hermes_adapter_integration.py`
- `tests/integration/test_studio_api.py`
- `tests/live_gateway.py`
- `tests/security/test_9router_boundary.py`
- `tests/security/test_9router_discovery.py`
- `tests/security/test_9router_exact_model.py`
- `tests/security/test_runtime_provenance_verification.py`
- `tests/security/test_hermes_security_gates.py`
- `tests/security/test_uat_model_availability.py`
- `tests/studio_runtime.py`
- `tests/unit/test_gemini_status_audit.py`
- `tests/unit/test_model_router.py`

## Core deadline, usage dan bounded dispatch

Core memasang deadline dan full effective token reservation sebelum Hermes dispatch. Transport
meneruskan Core output max_tokens, membuang override n/max_completion_tokens, dan hanya
mengizinkan satu upstream dispatch per receipt termasuk setelah successful completion.
Model/provider aktual tetap evidence runtime/gateway; missing usage bukan angka nol terukur.
Input token admission estimated; total/input/output measured postflight. Provider tidak
diklaim mempunyai hard total-token/cost cap. BYOK/local/9Router tidak otomatis Managed AI.
Timeout/ACK cancellation bukan proof provider berhenti; unknown retains reservation.
Lihat [Core execution/runtime hardening](core-execution-hardening.md) untuk owner, recovery,
contract, security evidence dan PostgreSQL limitations.

## Deployment runtime isolation

The dedicated ARYN Hermes wrapper now owns its actual aiohttp application/loopback listener and registers only minimal health, verified empty toolsets/capabilities, gateway receipt, text turn, run result and stop operations. Native jobs/cron, unrestricted sessions, responses, platform/profile/plugin ingress and browser-control WebSockets are unavailable even with a valid native API key. Request fields cannot grant tools, inject internal receipt, select native session IDs or enable fallback. Installed Hermes startup/router dispatch is tested with isolated home and HTTP model doubles; this does not prove VPS/firewall/container isolation. Runtime key remains private to API/runtime. See [route table and deployment boundary](deployment-security.md) and [actual validation](deployment-validation.md).
