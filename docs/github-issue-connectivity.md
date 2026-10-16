# GitHub issue connectivity

Audited baseline: `main`, `0c3608c9b2b7d58340471b7d48db31b115a98cfa`.
Local HEAD and the Git remote were equal, with a clean working tree. Previously
downloaded delivery evidence verifies 14 successful GitHub Actions jobs and the
commit-bound artifact on that baseline. It does not verify these new changes.
Initial authorization covered offline implementation and review. Following that
review, the owner authorized commit/push and GitHub Actions delivery verification.
Production GitHub API/token, OAuth, installation, deployment and other connectors
remain outside this authorization.

## Architecture audit

Read `AGENTS.md`, `README.md`, `SECURITY.md`, secure HTTPS connectivity, Core
execution hardening, workflow execution, governance history, Factory/Bench,
deployment security and CI delivery contracts. The sibling `aryn-docs` still
contains an index rather than the private normative architecture/security texts;
those unavailable documents are not claimed reviewed.

| Responsibility | Existing owner and change |
|---|---|
| Identity, tenant/project, human administration | Existing binder and PermissionEngine; no permission changes |
| Registration, ephemeral credentials and approvals | Existing CoreTools; recognize one GitHub definition and retain the same HTTPS approval/signature/lifecycle |
| Publication and assignment | Existing Factory/Bench approval/publication, immutable version, signed active assignment; reuse `metadata.https_bindings` |
| Execution | Existing coordinator, claim, ownership fence, reservation, cumulative limits, idempotency and cancellation |
| Network | Existing HTTPSAdapter and HTTPSTrust; add a fixed GitHub response profile and stricter one-shot framing |
| GitHub data | One small pure mapping module; no network client, policy authority or credential access |
| Evidence | Existing transport receipt, authenticated audit, signed completion and managed history; extend HTTPS provenance with repository/issue identity |
| Evaluation | Existing Bench registry/runner/graders and publication gate; one strict synthetic GitHub suite |
| Webhooks/automations | Existing ingress and scheduler remain unchanged; tool-enabled automation remains outside the supported target contract |

No second registry, router, HTTP client, credential manager, permission engine,
coordinator, evaluator or database schema is created. No dependency, lockfile,
frontend or model/provider configuration changes are needed.

Existing production files changed: `packages/contracts/tool.py` and `bench.py`;
`packages/tool_adapters/https.py`; `modules/core/tools.py`, `capabilities.py` and
`workflows/coordinator.py`; `modules/bench/runner.py` and `scenarios.py`.
The new production file `packages/tool_adapters/github.py` owns only reviewed
headers, safe error mapping, identifier mapping and response normalization.

New verification files: `tests/github_fixture.py`,
`tests/integration/test_github_tools.py`, `tests/security/test_github_boundary.py`
and `tests/postgresql/test_github_persistence.py`. They reuse the TLS fixture and
Core lifecycle rather than introducing another test HTTP engine. The existing
TLS fixture and installed Hermes boundary tests are extended without removing
their assertions. README links this contract.

## Request and repository binding

The only operation is `github.issue.read`, exposed to the model as
`aryn_github_issue_read` with exactly `{"issue_number": 42}`. The identifier must
be an integer (not a boolean, float or numeric string), in `1..2147483647`.
Unknown properties, scope, repository, URL, headers, body and credential fields
are rejected. The trusted adapter converts the validated integer to canonical
decimal in the existing `{key}` route slot. No model-authored route is accepted.

Human organization-admin `tool:register` authority in the current project must
register a GitHubIssueConnectionDefinition through the existing CoreTools owner.
The trusted definition fixes owner/repository, GET, exact input/output schemas,
response profile and limits. The supported canonical repository subset is a
lowercase ASCII owner of at most 39 characters, with internal single hyphens,
and a lowercase ASCII repository of at most 100 characters, beginning/ending in
an alphanumeric character with internal dots, underscores or hyphens permitted.
Aliases outside this deliberately narrow subset require a separately reviewed
contract; no discovery or automatic canonicalization is performed.

The route must equal `/repos/{approved_owner}/{approved_repo}/issues/{key}`.
Production trust accepts only `https://api.github.com:443`, additionally requiring
exact operator HTTPS origin allowlisting and public pinned DNS destinations.
Other production hostnames/ports are denied even when generally allowlisted.
Only the existing test-owned FixtureTrust subclass permits its exact literal
loopback origin with a synthetic CA. No production bypass flag is introduced.

Fixed reviewed headers are `Accept: application/vnd.github+json`,
`X-GitHub-Api-Version: 2022-11-28`, `User-Agent: ARYN-GitHub-Issue-Reader`,
`Accept-Encoding: identity` and `Connection: close`. Host and bearer authorization
remain transport-authored. The versioned profile is a fixture contract, not a
claim of compatibility verified against today's production GitHub API.

Approval hashes the entire definition, scope, owner, endpoint, route, schema,
limits, trust identity, DNS answer set, random binding and keyed credential
identity. Repository or credential replacement requires revoke/register and a
new approval hash; published versions pin the original hash and cannot adopt it.
No public registration API is added.

## Response contract

The raw GitHub body does not contain or supply ARYN scope. Strict JSON and a
bounded schema require `number`, `title`, `state`, `body`, `url`, `html_url` and
`repository_url`. Types/ranges, title length (1–256), body (null or at most 16384
characters), and URL lengths are checked. Every identity URL must match the
approved repository and requested issue exactly. URL aliases, queries, fragments,
different issues/repositories and internal addresses are rejected, never fetched.
Any `pull_request` field, including null, explicitly rejects the object.

Unknown ordinary upstream fields are discarded. Sensitive-key/credential
reflections are rejected before discarding or truncating data; a top-level token
field is forbidden. The response has no authority over Core scope or grants.

The strict normalized envelope has exactly:

- Core `organization_id`, `project_id` and approved `repository`;
- `kind: issue`, requested `issue_number`, bounded `title`, `state: open|closed`;
- validated GitHub issue `url`, `body_excerpt` (at most 1024 characters), and
  `body_truncated`;
- `content_trust: untrusted` and `source: github_https_fixture|github_https`.

No raw user/labels/comments metadata or full response is delivered to the model.
Title/body remain untrusted tool-result data, never system instructions. A model
following injected shell, secret, grant, other-repository, upload or commit/push
instructions still encounters the same Core grant/schema/limit checks. Tests
prove authority confinement with a model double, not live-model behavioral safety.

401, 403, 404, 429 and 5xx map to distinct fixed safe failure codes. Other non-200
statuses, including redirects, are rejected. No error body or upstream exception
text is copied into audit or public errors; no failure gets success provenance.
Rate responses consume the attempt and never retry. Core settlement preserves
only the explicit safe GitHub error-code allowlist.

The existing transport still enforces verified TLS 1.2+, the whole approved DNS
set, numeric pinned connect/peer checks and reauthorization at DNS/TCP/TLS/HTTP
and response boundaries. No proxy environment, redirects, retries, alternate
addresses, URL following or fallback exists. Its one-shot HTTP profile also
requires EOF after Content-Length: truncated and trailing/pipelined bytes fail.
Chunking, compression, duplicate/invalid headers, missing/oversized length,
malformed/duplicate-key JSON and wrong Content-Type are rejected. Existing limits
remain: 8 KiB/64 headers, default 16 KiB body (32 KiB hard maximum), five-second
maximum operation timeout, at most twelve attempts/minute/connection and 128
retained invocation identities. Failed attempts count. Large production issues
and response framing outside this supported profile can fail closed.

## Credential isolation and signed execution

Synthetic SecretStr tokens enter only trusted Core registration. The existing
session-only binding, TTL at most 300 seconds, 60-second freshness check,
revocation, rotation, keyed identity and retained diagnostic protection apply.
There is no environment token discovery, plaintext persistence, secret export or
model access. Restart loses the credential and approval. Python memory handling
does not promise secret zeroization.

Future production authentication can supply a selected-repository GitHub App
installation token or a fine-grained read-only PAT through this same trusted
binding entry point. Provider permissions/installation ownership, secure storage,
expiry/rotation/revocation and operating-environment controls need separate owner
review and live verification. No App installation, provider integration, real PAT,
OAuth login or refresh-token implementation is included.

Actual flow: published version with exact HTTPS binding and explicit GitHub grant
→ active signed assignment → model issue-number proposal → existing Core
identity/scope/publication/grant/approval/budget/deadline checks → signed HTTPS
invocation → repeated Core reauthorization → actual pinned TLS GET → strict raw
validation/normalization → existing in-memory physical exchange receipt → Core
receipt/provenance/output verification → authenticated tool-result audit → bounded
model continuation → existing final output-contract validation and signed result.

HTTPS evidence is extended with `connector_identity: github.issue.read`, a scoped
repository binding hash and the issue number. Existing fields bind run, trace,
scope, connection/tool/grant identity, approval/schema/endpoint/target/invocation/
input/output digests, raw response digest, HTTP status, TLS, validation, request
and byte usage, timeout and policy. The signed run's captured AgentVersion,
payload and assignment provenance bind publication and allowed grants. No URL,
DNS addresses, raw issue body or token is put into transport evidence. Forged or
missing physical exchange receipts cannot produce a verified tool completion.

Capabilities remain informative: connector structure and temporary bindings do
not grant access. Fixture verification is test evidence; production GitHub API,
production credentials and OAuth remain NOT VERIFIED. Bench uses the existing
`governed-github` suite and graders, with an authorized read and a no-grant case,
restricted to the existing test TLS trust. There is no live evaluation fallback.

## Verification and limitations

Verification uses Windows, Python 3.12.12, the existing installed native Hermes
and a disposable local PostgreSQL 16.13 service with distinct migration owner and
restricted writer. No production credentials or external GitHub REST calls are
used. The final Python source digest is
`d14ee23234e8022238dca3f7d920b268744f17ece8db8520c44af200873b8a8d`.
PostgreSQL independently records that same digest before and after its full run.

Actual commands (local orchestration and evidence remain ignored under `.local`):

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/test_github_tools.py tests/security/test_github_boundary.py -x -q --tb=short --durations=8 --junitxml=.local/github-focused.xml
.venv/Scripts/python.exe -u .local/verify_github_backend.py
.venv/Scripts/python.exe -u .local/run_github_backend.py 2
.venv/Scripts/python.exe .local/verify_github_results.py
.venv/Scripts/python.exe -u .local/verify_github_postgresql.py
.venv/Scripts/python.exe -m ruff check .
uv lock --check --offline
.local/quality-tools/actionlint.exe
.venv/Scripts/python.exe scripts/check_repository.py
git diff --check
.venv/Scripts/python.exe .local/audit_github_dependencies.py
.venv/Scripts/python.exe scripts/check_dependency_audit.py .local/github-python-audit.json
.venv/Scripts/python.exe .local/scan_github_sources.py
.local/quality-tools/gitleaks.exe git . --redact --log-opts=--all --report-format json --report-path .local/github-history-secrets.json
```

The backend wrapper runs the unchanged selector with `-m 'not postgresql'
--backend-shard=N/4 -v --durations=15 -o faulthandler_timeout=120 --tb=short`,
and independent JUnit/selection manifests. Shards execute sequentially; native
Hermes is in shard 2/4, after PostgreSQL and the other shards have finished.
The coverage verifier compares every JUnit identity, checks identical current
Python source digests and a disjoint full union, and verifies retention of all
1424 baseline backend identities. It never fabricates a Linux runner report.

The first full shard 2/4 run had 388 PASS and one FAIL: the three-second adapter
deadline expired after TLS reauthorization and before writing GET in the HTTP
401 case. Core retained `outcome_unknown / execution_deadline`, with no successful
tool evidence. Its actual log, JUnit and manifest are preserved in
`.local/github-backend-initial/windows-2`. The entire shard was repeated on the
identical source: 389 PASS, zero FAIL/SKIP, including HTTP 401 and native Hermes.
No timeout, permission or assertion changed. This observed timing failure remains
part of the review record. The exact operating-system scheduling/storage cause
was not profiled; a repeat PASS does not establish a guaranteed latency bound.

Offline dependency audit evaluates all 86 exact-version third-party packages
using the existing pip-audit evaluator over cached responses, with socket/DNS
access prohibited. The inventory checker verifies all 87 installed distributions
(including the permitted first-party editable skip). No known vulnerabilities
appear in the cache dated 15 October 2026, 10:30:10–10:30:16 UTC. This is cached
advisory coverage, not a fresh advisory lookup. No dependency or lockfile changed.

Linux/remote CI on the uncommitted implementation is NOT RUN. Frontend source
and contracts are unchanged; no additional frontend/browser run is claimed.
The previously validated baseline is not CI evidence for these changes.

Final verification on 16 October 2026:

| Verification | PASS | FAIL | SKIP |
|---|---:|---:|---:|
| Final Windows shard 1/4 | 387 | 0 | 2 |
| Final Windows shard 2/4, complete repeat | 389 | 0 | 0 |
| Final Windows shard 3/4 | 387 | 0 | 2 |
| Final Windows shard 4/4 | 387 | 0 | 1 |
| Complete Windows backend | **1550** | **0** | **5** |
| GitHub integration, included above | 90 | 0 | 0 |
| GitHub security boundary, included above | 41 | 0 | 0 |
| Existing HTTPS integration/security, included above | 142 | 0 | 0 |
| Existing MCP integration, included above | 63 | 0 | 0 |
| Governed execution/probe, included above | 103 | 0 | 0 |
| Webhook security, included above | 20 | 0 | 0 |
| Installed native Hermes, included above | 1 | 0 | 0 |
| Full PostgreSQL integration | **144** | **0** | **0** |

Subset rows are not additive. The focused GitHub suite also completed 131 PASS,
zero FAIL/SKIP before the full backend run. The final manifests cover 1555 unique
backend identities, retaining every baseline identity; JUnit identities match
exactly, and partitions have no overlap or missing cases. Local evidence:
`.local/github-backend/windows-[1-4]/{backend.xml,backend-selection.json,backend.log}`,
`.local/github-verification.json`, `.local/github-postgresql.xml` and
`.local/github-postgresql-source.json`. These are offline review records, not a
Validated Delivery Artifact.

The five retained skips are explicit:

- `test_live_end_to_end_smoke`, `test_live_hermes_assigned_research_agent_run` and
  `test_live_hermes_run_lifecycle_and_cancellation`: live inference requires
  owner-authorized opt-in, which is absent in this scope.
- `test_live_hermes_health` and `test_live_hermes_capabilities_and_confinement`:
  no local runtime API_SERVER_KEY is supplied. Installed native Hermes separately
  passes with synthetic credentials and network-denied model doubles.

Ruff, actionlint, frozen offline lock validation and repository/diff hygiene PASS.
Redacted Gitleaks scanning of 91 Git commits and all 18 changed/new files found
no leaks. Model turn/result, Bench, audit, trace, errors and SQLite bytes are also
checked for synthetic credential exposure in the integration tests. PostgreSQL's
temporary server was stopped after the full suite. Existing Starlette/Authlib
httpx deprecation warnings remain; dependencies were not replaced in this scope.

| Area | Status |
|---|---|
| GitHub issue read connector | VERIFIED — offline fixture |
| HTTPS fixture integration | VERIFIED — actual TLS/GET |
| Core authorization | VERIFIED — existing governance and negative tests |
| Credential isolation | VERIFIED — temporary synthetic bindings |
| SSRF enforcement | VERIFIED — application socket boundary and offline fail-closed tests |
| Signed evidence | VERIFIED — actual exchange receipt, authenticated audit and signed completion |
| Prompt injection boundary | VERIFIED — Core authority confinement with model doubles |
| External GitHub API | NOT VERIFIED |
| Real GitHub credentials | NOT VERIFIED |
| Remote CI | NOT RUN |
| Milestone C1 | COMPLETE — OFFLINE IMPLEMENTATION COMPLETE |

All implementation acceptance criteria are verified within the stated offline
fixture boundary. This table records the offline review checkpoint, when HEAD
was still at the baseline and all 18 changed/new files were uncommitted. The owner
subsequently authorized commit/push. Delivery must be verified against the pushed
SHA and its GitHub Actions artifact; the table does not attest those later checks.
Deployment and subsequent milestones remain outside this work.

Production GitHub responses, rate-limit behavior, token permissions, TLS trust
operations, persistent credentials and deployment/network UAT remain unverified.
Application socket enforcement does not claim protection from a compromised Core
host, kernel/routing/NAT changes or signing keys. Workflow/automation tool-enabled
targets are not expanded. Frontend remains frozen; no other connector or next
milestone is started. Delivery requires separate owner-authorized commit/push,
all required CI on that exact SHA and its Validated Delivery Artifact.
