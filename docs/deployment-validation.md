# Deployment Boundary Hardening — actual evidence

8 October 2026. Baseline `27c3f0e66840ef4dee671dc5852fe4c3142d9465`, branch `development`.
Root cause, architecture, exact route table, trust boundaries dan configuration terdapat pada
[deployment security](deployment-security.md). Tidak ada push atau perubahan `main`.

## Actual automated results

| Check | Actual result | Evidence |
|---|---|---|
| Dedicated auth/runtime/Core/history/migration regression | **190 passed**, 37 warnings, 217.46 s | `.local/deployment-dedicated.log`; sebelum additional CLI/ES256 tests, additional coverage juga masuk final full suite |
| Reviewed auth + registry scope | **44 passed**, 3 warnings, 55.17 s | `.local/deployment-authority-final.log` |
| Updated environment/Local launcher contract | **21 passed**, 1 warning, 27.58 s | `.local/deployment-launcher-final.log` |
| Reviewed auth including public-bind CLI guard | **35 passed**, 2 warnings, 24.61 s | `.local/deployment-auth-reviewed.log`; ES256/unsigned/HMAC follow-up kemudian diuji dalam final full suite |
| Installed Hermes actual wrapper startup/router, final session-header review | **1 passed**, 19.06 s | `.local/deployment-native-reviewed.log`; real installed Hermes, actual loopback listener/app, isolated model transport; Session-Id and Session-Key denied |
| Final boundary review: auth/exact-model/native routes | **52 passed**, 2 warnings, 44.95 s | `.local/deployment-boundary-reviewed.log`; conflicting sync/async limit locations now rejected before dispatch |
| Full backend, final code | **698 passed, 5 skipped**, 43 warnings, 542.47 s | `.local/deployment-backend-complete.log`; includes final limit and both native session-header rejection |
| Frontend, final Local/Hosted labels | **86 passed**, 14 files, 18.86 s | `.local/deployment-frontend-release.log` |
| TypeScript + Vite, final assets | **PASS**, Vite 8.69 s | `.local/deployment-build-release.log`; existing >500 KiB chunk warning |
| Focused Ruff E4/E7/E9/F | **PASS** | `.local/deployment-lint-complete.log`; existing delayed imports probe E402 exemption explained below |
| Focused frontend Prettier | **PASS** | `.local/deployment-frontend-format.log`; four changed TS/TSX files |
| Whitespace | `git diff --check` **PASS** | no whitespace errors; Windows CRLF conversion notices only |
| SQLite existing DB copies + migration compatibility | **PASS** | `.local/deployment-existing-migration.json`; fresh/upgrade/downgrade + offline PostgreSQL DDL also in full suite |
| Browser suite, isolated database groups | **17 passed** = 6 + 6 + 5; 1.1 min + 44.9 s + 2.2 min | `.local/deployment-browser-isolated-{1,2,3}.log`; one worker per group, all assertions/timeouts preserved |

First unsegmented browser run: **14 passed, 3 failed** (5.9 min). Failure traces showed
valid session/workspace and project snapshot still loading; accumulated shared-fixture data
made snapshots take approximately 4.9–6.8 seconds, beyond existing 5-second UI assertions.
The complete suite subsequently ran serially in three groups, each starting a fresh disposable
database. One old test depended on another test's blueprint; it now creates its own real
Core/Bench fixture and preserves the validation/permission-denial assertions. The first
isolated second group exposed that dependency (5 passed, 1 failed); its final rerun passed 6/6.
No timeout was increased, no security assertion removed, no automatic retries used.
Snapshot latency on larger datasets remains a residual; this is not a performance PASS for
the unsegmented accumulated dataset. No real hosted IdP/TLS/VPS browser UAT is claimed.

```powershell
# Repo root, explicit isolated pytest secrets; never opts in live models.
.\.venv\Scripts\python.exe -m pytest tests/security/test_deployment_authentication.py tests/integration/test_authentication_migration.py tests/integration/test_hermes_9router_binding.py tests/security/test_endpoint_configuration.py tests/security/test_rbac_authorization_boundary.py tests/security/test_core_execution_authority.py tests/integration/test_core_execution_contract.py tests/security/test_execution_idempotency_claims.py tests/security/test_governance_history_integrity.py tests/security/test_9router_exact_model.py tests/integration/test_schema_migration_compatibility.py tests/integration/test_assignment_activation_migration.py -q -ra --tb=short
.\.venv\Scripts\python.exe -m pytest tests/security/test_deployment_authentication.py tests/integration/test_agent_registry_rollback.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/test_studio_launcher.py tests/security/test_9router_boundary.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/security/test_deployment_authentication.py -q -ra --tb=short
.\.venv\Scripts\python.exe -m pytest tests/integration/test_hermes_9router_binding.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/integration/test_hermes_9router_binding.py tests/security/test_9router_exact_model.py tests/security/test_deployment_authentication.py -q -ra --tb=short
.\.venv\Scripts\python.exe -m pytest -q -ra --tb=short
# apps/web, after backend tests complete
npm.cmd test -- --reporter=dot
npm.cmd run build
$env:PATH = 'D:\ARYN\aryn-labs\aryn\.venv\Scripts;' + $env:PATH
npm.cmd run test:e2e
# Entire browser suite, with a fresh disposable database per group, serial workers:
npm.cmd run test:e2e -- --fully-parallel --workers=1 --shard=1/3
npm.cmd run test:e2e -- --fully-parallel --workers=1 --shard=2/3
npm.cmd run test:e2e -- --fully-parallel --workers=1 --shard=3/3
npx.cmd prettier --check src/lib/api.ts src/studio.tsx src/test/authentication-contract.test.tsx e2e/studio.spec.ts
```

Five skips: three model tests require explicit owner opt-in, two live Hermes health/capability
checks lack `API_SERVER_KEY`. Installed Hermes isolated integration is **not skipped**.
No paid/live model requests or production provider credentials were used. Warnings include
existing Alembic path_separator and FastAPI/Authlib httpx deprecation; tested versions
Authlib 1.8.0, PyJWT 2.15.1, FastAPI 0.142.2, httpx 0.28.1, uvicorn 0.54.0.
Dependency migration to httpx2 is a separate compatibility task; it was not silently performed.

First full run: **693 passed, 3 failed, 5 skipped**. Two failures were old exact environment/
`.env.example` lists that lacked explicit authentication config, and one expected production
to use the Local launcher. Lists now enumerate only explicit authentication/database variables;
AST prohibition of environment enumeration/dynamic getenv remains. Launcher production assertion
now requires failure, preserves no-secret/no-start assertions; development still requires success.
An intermediate full run passed 696 with 5 skips; final CLI bind and ES256 tests are included
in the **698/5** final run. No security assertions were deleted/relaxed.

Initial installed-runtime test caught an eager Core package import requiring SQLAlchemy in
Hermes' dedicated interpreter. Core public exports now load lazily, so runtime sanitization
does not import database/control-plane dependencies; later installed-runtime runs pass.
Original HTTP `_aryn_receipt` ignored-field fixture now receives a negative rejection test;
positive execution uses only allowlisted fields, preserving actual-model/physical-call assertions.

Focused lint command actually used:

```powershell
.\.venv\Scripts\python.exe -m ruff check --select E4,E7,E9,F --per-file-ignores tests/hermes_gateway_check.py:E402 services/api/authentication.py services/api/studio.py services/api/__main__.py services/runtime/hermes_9router.py modules/core/__init__.py modules/core/errors.py modules/core/identity modules/core/permissions/engine.py database/schema.py database/migrations/versions/015_authentication_boundary.py packages/contracts/core.py tests/security/test_deployment_authentication.py tests/integration/test_authentication_migration.py tests/hermes_gateway_check.py
git diff --check
```

Existing probe imports deliberately occur after isolated Hermes path/home/network setup.
The E402 exemption preserves that security initialization order; it is not a broad lint suppression.
Unused runtime imports were removed. Full style lint is not claimed. Browser/build assets were
searched for server `API_SERVER_KEY`/`ARYN_9ROUTER_API_KEY` or environment access with no matches;
client assets contain no server secret configuration. Registered synthetic credential tests also
exercise responses, prompt boundary, diagnostic logging and existing audit/SSE regressions.

## Negative security evidence

| Scenario | Evidence/result |
|---|---|
| Production auth missing or local-development mode | Startup ValueError before local provisioning; production test flag cannot bypass |
| Loopback reverse proxy anonymous bootstrap | `/api/session` 401, no cookie, no development org/admin rows |
| Host/Origin/Forwarded/X-User/X-Role/X-Forwarded-User | Denied 403; trusted proxy HTTPS headers still confer no identity |
| Direct HTTP upstream / untrusted proxy | 403; exact trusted HTTPS proxy can reach login only |
| Invalid issuer/audience/signature/expiry/iat/nonce/azp | Callback 401 and no session |
| Unsigned/HMAC JWT / valid ES256 | Unsupported algorithms rejected; valid signed ES256 verified; RS256 fixtures cover full login |
| Invalid state/duplicate callback/expired transaction/cross-browser cookie/replay | 401; durable transaction consumed before external await |
| Redirect manipulation | Login query 400, mismatched callback config rejected |
| Email/role/actor claims without provisioned subject/current membership | No login authority; browser escalation payload 422; real DB role remains operator |
| Development identity mapping in hosted | 401; shared development principal cannot become production session |
| Session/mapping/membership revoked or session expired after preflight | Core mutation raises PermissionDeniedError, HTTP 401/403 |
| Role downgraded between preflight and commit | Org-admin governance permission denied within write transaction |
| Session fixation/logout/CSRF/stripped signed session reference | New random session, old session revoked, invalid CSRF 403, logout invalidates cookie; reference stripping invalidates binder |
| Cross-tenant/project access | 403; workspace lists only readable real project |
| Anonymous SSE / docs/debug/diagnostics | API 401; sensitive paths 404; no Studio WebSocket authority |
| Hosted Factory/Bench/publication/assignment/run/cache/SSE | Actual Core lifecycle through signed mock login; signed claim + activation + authenticated audit verified, exact model/version preserved |
| Native jobs/cron/session admin/profile/plugin/browser-control/approval/steer/unknown routes | Actual installed native route table resolved on real wrapper-started application; 404 even with valid native key |
| Native browser Upgrade/session-ID/session-key selection/tools/fallback/internal receipt | 403/422, no additional physical model calls |
| Conflicting top-level/model-options execution limits | Sync and async actual native router reject 422; ignored alternate parameters cannot imply a stricter enforced cap |
| Allowed runtime operation | Real Hermes AIAgent and HTTP model doubles; exact model/output cap, tool-free request, async durable proof, substitution/credential leak rejection preserved |
| API CLI public bind override | Process rejects `--host 0.0.0.0` before startup |
| Runtime listener binding | Actual started socket address `127.0.0.1`, ephemeral fixture port; no native routes outside explicit table |
| Runtime/server secrets in public responses/logs/prompt/assets | Registered synthetic values rejected/scrubbed; installed stdout/stderr checked; no server config in client assets |
| BN-06/AF-07/013/014/ownership/budget/provenance | Existing security/integration/full suites pass without assertion weakening |

## Final authority review and residual

Browser data/headers cannot mint Core contexts or write role/membership. Authenticated external
subject is mapped only via DB; membership/project policy remains Core. Signed session reference
is revalidated at commit, with session → identity → membership lock order, including login rotation.
Callback consume and session creation are separate short transactions around provider await.
No session/evidence key defaults and no production local-admin fallback exist. No historical
approval/publication/comparison or Bench evidence was fabricated for authentication compatibility.

Runtime application registers no native connect/profile/plugin ingress or scheduler. Only
authenticated confined text/run operations remain; private shared runtime key is a trusted internal
transport credential. It cannot unlock removed administrative routes, but its theft plus internal
network access could invoke permitted text operations outside Core; per-run cryptographic runtime
fencing is not claimed. Host/runtime/DB administrators, signing secrets and deployment ACLs remain
trusted. Native model/tool controls are verified on the installed revision and isolated config,
not a complete OS sandbox proof for arbitrary runtime plugins/configurations.

PostgreSQL upgrade/downgrade compiled offline only; `psql` unavailable and Docker daemon not running.
No real IdP registration/SSO logout/revocation, TLS handshake, reverse proxy server, firewall,
container networking or VPS deployed. Backend signed-provider tests use HTTPS ASGI fixture and
httpx doubles. New browser login test is a presentation/error contract double; Local browser
lifecycle uses real HTTP API/Core/SQLite with isolated runtime. No hosted production-ready claim.

ARYN session logout is local, not IdP/global logout/backchannel invalidation. Edge rate limits,
mapping/session operational revocation, expiry-row/log retention, protected backup/restore and
real provider configuration/UAT remain deployment responsibilities. Existing 013 independent
commitment and 014 single-authority/provider token/cost limitations remain in force.
Large accumulated project snapshots exceeded the unchanged browser visibility timeout;
isolated fixture groups pass but production snapshot scaling remains unverified.
Hosted foundation freeze remains **BLOCKED**.

## Files changed

39 files berubah; commit dibuat lokal pada `development`, tanpa push.
`main` tetap `630cbc96d728a49a64247ad2b88978529a7cbbad`.

```text
.env.example
README.md
SECURITY.md
STATUS.md
apps/web/e2e/studio.spec.ts
apps/web/src/lib/api.ts
apps/web/src/studio.tsx
apps/web/src/test/authentication-contract.test.tsx
database/migrations/versions/015_authentication_boundary.py
database/schema.py
docs/9router-gateway.md
docs/agent-factory-contracts.md
docs/bench-engine.md
docs/core-execution-hardening.md
docs/deployment-security.md
docs/deployment-validation.md
docs/studio.md
modules/core/__init__.py
modules/core/errors.py
modules/core/identity/binder.py
modules/core/identity/sessions.py
modules/core/permissions/engine.py
packages/contracts/core.py
pyproject.toml
scripts/start-aryn.ps1
scripts/start-studio.ps1
services/api/__main__.py
services/api/authentication.py
services/api/studio.py
services/runtime/hermes_9router.py
tests/conftest.py
tests/hermes_gateway_check.py
tests/integration/test_authentication_migration.py
tests/integration/test_hermes_9router_binding.py
tests/integration/test_schema_migration_compatibility.py
tests/security/test_9router_boundary.py
tests/security/test_deployment_authentication.py
tests/studio_server.py
tests/unit/test_studio_launcher.py
```
