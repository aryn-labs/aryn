# GitHub live UAT preparation

Audited baseline: `4f74ca77ddd7dffa43c43a1ddd7c4da0e7e1ce71`, branch `main`.
Scope: a bounded operator diagnostic and offline verification. The owner approved the limited
human operator Core profile on 16 October 2026 after reviewing the fixture-only
Bench boundary, subsequently ran one live read and authorized commit/push.
Preparation did not create/read the owner's real token file or call the live API.
The owner-reported live result is recorded separately below; deployment remains out of scope.

## Existing components and admission gap

Reuse `CoreTools.register/revoke`, `GitHubIssueConnectionDefinition`,
`HTTPSAdapter`, the existing identity/permission/budget authorities,
`RunCoordinator`, authenticated audit and signed Core execution evidence.
There is no need for another client, credential store, registry or coordinator.

The current governed agent path requires a published AgentVersion with the exact
temporary HTTPS binding, an active signed assignment and explicit tool grant.
Publication requires current passing Bench evidence for the version payload.
The `governed-github` suite requires `read_only_github_fixture`; Bench explicitly
rejects every HTTPS trust implementation outside `tests.https_fixture` before
execution (`modules/bench/runner.py`).

A production `HTTPSTrust` binding therefore cannot pass that publication path.
Evaluating a fixture version and substituting its endpoint/token afterwards is
also invalid: the binding and canonical version payload change, invalidating
approval. Allowing production trust through the fixture check, manufacturing
Bench evidence, or marking a draft as published would bypass existing governance.

## Approved operator execution profile

The implementation adds a narrow **trusted human operator UAT profile inside the existing
RunCoordinator**, without changing published-agent execution or the Bench fixture
gate. This profile is an explicit Core authority boundary, rather than
pretending the operator's diagnostic run is an already published agent run.

The approved profile enforces these requirements:

- require authenticated human `tool:register`, `model:verify`, `run:create`,
  `run:read` authority from existing Core membership; deny agents and viewers;
- require both file opt-in and explicit CLI confirmation before loading a token
  for registration, DNS resolution or socket dispatch;
- capture and sign exactly `aryn_github_issue_read`, `aryn-labs/aryn`, one bounded
  positive issue number, `https://api.github.com:443`, GET, one attempt and two
  isolated model-double turns; expose no HTTP endpoint or user-supplied tool grant;
- use the existing temporary SecretStr registration, immutable binding hashes,
  admission/budget/deadline/idempotency/ownership checks, repeated reauthorization,
  HTTPS socket boundary and physical response receipt verification;
- recheck the fixed operator profile and existing approval before every dispatch
  and continuation; never grant this profile to a published agent automatically;
- validate the normalized response and final output contract, verify signed audit
  and completion evidence, and report only sanitized identifiers/digests/status;
- revoke the connection in `finally`, dispose its isolated in-memory Core state
  and signing material at process exit, and never persist the PAT;
- leave the publication/assignment/Bench requirements for ordinary agent runs
  intact. UAT evidence must explicitly identify an operator run and model double.

`RunCoordinator.execute_github_uat` captures the fixed plan in the existing
signed claim and uses the same governed executor, CoreTools and HTTPSAdapter.
Final JSON must match the validated tool identity/state, including its source.
No application HTTP route, second client, registry or coordinator is added.
The command creates an isolated in-memory UAT organization/project and a human
membership using explicit random identity/signing keys; it does not use the
application's database or expose identity issuance to a network client.
The runtime provider is explicitly `github-uat-model-double`. Its existing
Hermes/9Router envelope labels are not evidence of a live runtime or provider.

## Local configuration contract

The owner will create `.env.github-uat` manually **after the implementation is
approved and finished**. Do not supply its contents to Codex or put a token in
command arguments, shell history, CI, screenshots, logs or artifacts.

```dotenv
ARYN_GITHUB_UAT_TOKEN=
ARYN_GITHUB_UAT_REPOSITORY=aryn-labs/aryn
ARYN_GITHUB_UAT_ISSUE_NUMBER=
ARYN_GITHUB_UAT_ENABLE_LIVE=0
```

`git check-ignore -v .env.github-uat` already matches `.gitignore`'s `.env.*`
rule; no ignore change is necessary. The example above contains no credential.
This file is local plaintext, **not production secure secret storage**. Restrict
its filesystem access to the owner; never source it into a shell or load it into
the application's, Hermes's or 9Router's environment.

The loader reads only that explicit local file on operator invocation,
accepts only the four exact names above, and rejects duplicates, unknown keys,
oversized/non-regular files, interpolation, commands and invalid values with
fixed errors that contain no input. There is no dotenv expansion, ambient token
fallback, automatic startup loading or token export into `os.environ`.
Fine-grained PAT prefix/length/ASCII syntax checking cannot prove token validity,
expiry, approval by the organization or actual permissions; those remain live UAT
observations. Only an existing **issue**, not a pull request, should be selected
from the owner's GitHub UI. Reading its number requires no discovery endpoint.

After preparation is complete, the owner can enable the file gate and run from
the repository root:

```powershell
.venv/Scripts/python.exe -m scripts.github_uat --confirm-live-github-read
```

File opt-in must also be exactly `ARYN_GITHUB_UAT_ENABLE_LIVE=1`; token presence
alone never enables networking. The command denies before DNS or dispatch if a
gate, repository, issue number or registration identity is invalid. Core also
denies changed/expired authority before physical dispatch and continuation.

The command performs one attempt per invocation, exactly two isolated model
turns, zero paid inference and no retry or pagination. Overall execution is
bounded at 30 seconds; the HTTPS operation keeps its three-second default and
five-second hard maximum. Missing CLI confirmation denies before file opening.
There is no model inference, actual Hermes listener or 9Router connection.

A successful owner live read exits 0 and prints one JSON summary containing:

```json
{"status":"VERIFIED","execution_profile":"human_operator_with_isolated_model_double","repository":"aryn-labs/aryn","issue_number":42,"source":"github_https","http_status":200,"tls_verified":true,"network_requests":1,"signed_execution_verified":true,"credential_revoked":true,"paid_inference":false}
```

Number 42 is illustrative; select a real issue yourself in the repository's
GitHub UI, not a pull request. The actual summary also includes safe run/trace
IDs, binding/repository/invocation/response/evidence digests and Core claim/
completion attestations. Title/body, token, Authorization header, raw upstream
text and tracebacks are never printed. Fixture tests report
`source: github_https_fixture`, which does not attest external GitHub access.

Approval/invocation signatures, the physical receipt, stored result, authenticated
audit, output contract and Core trace are checked inside the owning process using
existing verification paths. Core state, history commitments and signing keys
are in memory and discarded at exit. Retained JSON attestations are a session
verification record, not an independently re-verifiable permanent evidence
archive after that key is discarded. Persistent evidence/key storage requires
separate review. Python memory, swap and diagnostic redaction retention do not
promise secret zeroization; diagnostic protection remains until process exit.

Failure exits 1 with a fixed `error_code` and `retry: false`:

| Code | Interpretation |
|---|---|
| `uat_confirmation_required` / `uat_live_gate_disabled` | Mandatory gate absent; no dispatch |
| `uat_config_invalid` / `uat_config_unavailable` | File format/access failed; no dispatch |
| `uat_token_missing` / `uat_token_format_invalid` | Local field absent/invalid; no dispatch |
| `uat_repository_invalid` / `uat_issue_number_invalid` | Scope/input rejected; no dispatch |
| `uat_permission_denied` | Identity, membership, owned binding or approval denied |
| `github_unauthorized` | GitHub returned 401; credential not accepted |
| `github_forbidden` | GitHub returned 403; permission, organization policy or rate limiting may apply |
| `github_issue_not_found` | GitHub returned 404; issue missing or invisible to the PAT |
| `github_rate_limited` | GitHub returned 429; stop and inspect manually |
| `github_service_error` / `github_response_rejected` | Server error or rejected status/redirect |
| `uat_destination_denied` | Endpoint/DNS/approval safety could not be established |
| `uat_network_unverified` / `uat_tls_unverified` / `uat_timeout` | Connection, TLS or deadline failure |
| `uat_response_invalid` | Framing, size, JSON, schema, identity or reflection rejected |
| `uat_evidence_invalid` | Stored result, authenticated audit or signed evidence rejected |
| `uat_cleanup_failed` / `uat_failed` / `uat_cancelled` | Cleanup, unexpected local failure or owner interruption |

No failed request receives success provenance. Safe fixed transport stage
metadata improves diagnostics in signed Core evidence; response acceptance and
existing MCP/HTTPS/GitHub error codes are preserved.

## GitHub protocol audit

Official documentation was checked on 16 October 2026; documentation access is
separate from a live REST API request. The connector's fixed
`Accept: application/vnd.github+json`, Bearer authentication and named User-Agent
match the documented API contract. `X-GitHub-Api-Version: 2022-11-28` remains
supported through 10 March 2028; upgrading the response profile is unnecessary
for this preparation. The selected-repository fine-grained PAT needs **Issues:
read**; ARYN performs no provider permission management or OAuth.

Required raw fields (`number`, `title`, `state`, `body`, `url`, `html_url`,
`repository_url`) match the issue representation. A `pull_request` field is
explicitly rejected. Unknown metadata and URLs are discarded, never followed.
Titles/bodies remain untrusted; the model gets only the existing bounded envelope.

Compatibility limitations must remain visible:

- The adapter supports only uncompressed JSON with bounded Content-Length and
  connection close/EOF. GitHub documentation does not guarantee that framing.
  Chunked/compressed/missing-length responses are denied. The owner's successful
  single read establishes compatibility for that response only, not future framing.
- The default raw body limit is 16 KiB (hard maximum 32 KiB); title/body and
  normalized excerpt bounds can reject legitimate large issues. This is an
  explicit fail-closed restriction, not proof of general GitHub compatibility.
- GitHub can use **403 or 429** for rate limiting. Existing 429 maps to
  `github_rate_limited`, but 403 maps to `github_forbidden`; a 403 does not by
  itself distinguish token permission failure from rate limiting. No error may
  cause a retry or success evidence. A reviewed bounded header classification
  may improve this diagnostic later.
- 301/redirects, 304, 410, malformed framing/JSON, wrong repository/URL, reflected
  credentials and invalid TLS remain failures. DNS change, non-global addresses
  and proxy environment substitution remain denied at the existing socket path.

References: [Get an issue](https://docs.github.com/en/rest/issues/issues#get-an-issue),
[API versions](https://docs.github.com/en/rest/about-the-rest-api/api-versions),
[request headers](https://docs.github.com/en/rest/using-the-rest-api/getting-started-with-the-rest-api),
[rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).

## Verification and remaining work

The new offline admission regression proves that an official-origin connection
with synthetic credentials cannot enter the fixture-only Bench publication path.
Its DNS answer is a test double and it performs no external socket connection;
it is admission evidence, not transport or live GitHub evidence. Existing local
TLS fixture regressions remain the transport evidence.

The owner-approved implementation includes loader/default-deny gates, temporary
credential lifecycle, the fixed operator Core profile, signed evidence and
sanitized CLI output. All preparation tests use synthetic tokens and the existing
local HTTPS fixture. Preparation readiness alone does not establish live UAT or
production readiness. The owner's subsequent live result is recorded below.

The command distinguishes authentication failure (401),
permission or rate failure (403), visibility or missing issue (404), rate failure
(429), network/TLS/DNS/deadline failure and response-contract failure without
logging upstream text.
It revokes the temporary connection in `finally` and disposes isolated Core
state on success, rejection or interruption, without rewriting the owner's file.
After owner testing, turn the gate off, remove the local token/file using the
owner's editor/filesystem controls, clear any editor backup or clipboard copies,
and revoke the fine-grained token in GitHub account settings if no longer needed.
File removal is not a guarantee of secure erasure on SSDs, backups or synced disks.

## Owner-executed live UAT record

On 16 October 2026 the owner supplied the sanitized stdout from running:

```powershell
.venv/Scripts/python.exe -m scripts.github_uat --confirm-live-github-read
```

The reported result was `VERIFIED`, repository `aryn-labs/aryn`, issue `10`,
state `open`, source `github_https`, HTTP `200`, `tls_verified: true`,
`validation: schema_valid`, one network request, seven verified audit events,
`signed_execution_verified: true`, `credential_revoked: true` and zero paid
inference. The execution profile was `human_operator_with_isolated_model_double`.

Safe identifiers from that owner-supplied record:

| Field | Value |
|---|---|
| Run | `run_86b43dccd40349a3955dad7c7a50aa19` |
| Trace | `61cc1840-5d32-46dd-9fce-1fab04bae0e0` |
| Invocation hash | `2a9e08171bc506bd37f8f47c656fb698ac4ad79c81b4d9fea631e9f43578b788` |
| Response digest | `3d8122082d9995d6f47a8636484a8c97a93abc8671e708e270bd41500820ea69` |
| Evidence hash | `484c94625f17ad439719fe56dec1ffbd0c280120a29aa4590d8b5083c548be9f` |

This is an owner-reported successful read, with signature verification performed
inside the UAT process. Codex did not read/use the PAT, repeat the live request,
or independently verify the discarded session keys. The stdout is not a durable
cryptographic evidence archive, a published-agent execution, a general GitHub
compatibility qualification or proof of production credential storage.
`credential_revoked` refers to the temporary Core binding, not GitHub PAT revocation.
After testing, the owner should restore `ARYN_GITHUB_UAT_ENABLE_LIVE=0` and remove
or revoke the PAT if it is no longer needed. No local token file is included in delivery.

## Offline verification record

Preparation status was **READY FOR OWNER-EXECUTED GITHUB LIVE UAT**, limited to
the offline verification below. The later owner-run result is separate. Verification ran on Windows with
Python 3.12.12 and synthetic credentials; source remained identical throughout
both test groups. Python source fingerprint:
`da616d6ca62e8a02fe5b6bc44aa517ca209d3bc54511609077f337c19cbcda63`.

| Final verification | PASS | FAIL | SKIP |
|---|---:|---:|---:|
| Core, including 54 configuration and 43 UAT integration tests | 381 | 0 | 0 |
| GitHub integration and boundary | 132 | 0 | 0 |
| HTTPS integration and SSRF boundary | 142 | 0 | 0 |
| MCP integration | 63 | 0 | 0 |
| Installed native Hermes with isolated gateway | 1 | 0 | 0 |
| Total executed | **719** | **0** | **0** |

The current backend collection contains 1653 identities and retains all 1555
baseline identities. This is collection preservation; the full backend suite was
not rerun. PostgreSQL, Linux, frontend/browser and remote CI were not rerun in this
preparation. Existing Starlette/Authlib httpx deprecation warnings remain; no
dependency was changed. Remote CI results for the committed baseline do not
attest the preparation changes. Exact-SHA CI and the delivery artifact must be
verified after the separately authorized commit/push.

Actual test commands (the local source-bound orchestration retains the complete
argument lists in `.local/github-uat/verification.json`):

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_github_uat_config.py tests/integration/test_github_uat.py tests/security/test_governed_tools.py tests/security/test_core_execution_authority.py tests/security/test_execution_idempotency_claims.py tests/security/test_governance_history_integrity.py tests/security/test_bench_evidence_integrity.py tests/security/test_bench_engine_integrity.py tests/integration/test_bench_engine.py tests/integration/test_workflow_execution.py tests/security/test_automation_webhook.py -q --tb=short --durations=10 --junitxml=.local/github-uat/core.xml
.venv/Scripts/python.exe -m pytest tests/integration/test_github_tools.py tests/security/test_github_boundary.py tests/integration/test_https_tools.py tests/security/test_https_boundary.py tests/integration/test_mcp_tools.py -q --tb=short --durations=10 --junitxml=.local/github-uat/connectors.xml
.venv/Scripts/python.exe -m pytest tests/integration/test_hermes_9router_binding.py -q --tb=short --junitxml=.local/github-uat/native.xml
.venv/Scripts/python.exe -m ruff check .
uv lock --check --offline
.local/quality-tools/actionlint.exe
.venv/Scripts/python.exe scripts/check_repository.py
git check-ignore -v .env.github-uat
.local/quality-tools/gitleaks.exe dir .local/github-uat-source --redact --report-format json --report-path .local/github-uat-source-secrets.json
```

Ruff, frozen offline lock validation, actionlint, repository/diff hygiene and
redacted Gitleaks scanning of exactly the ten changed/new source files PASS.
The scan uses an isolated source export and does not read the owner's local
environment file. An actual CLI invocation without confirmation returned
`uat_confirmation_required`, exit 1, before reading that file or dispatching.
Only the owner runs the confirmed command with real credentials.
