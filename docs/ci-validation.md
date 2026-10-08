# CI delivery validation evidence

Validation date: 2026-10-08. Source baseline:
`58bde394ea40c9098f5c8d0e472ef21a3314468c` (`development`).
`main` was not changed; its local and remote reference was
`630cbc96d728a49a64247ad2b88978529a7cbbad`.

## Local results

| Check and actual command | Result |
|---|---|
| Python 3.12.12 / uv 0.12.0: `uv sync --frozen --extra dev` | PASS, isolated clean environment from committed lock |
| `python -m pytest -m 'not postgresql' -q --junitxml=.local/backend-final-current.xml` | **712 passed, 5 skipped, 33 deselected**, 499.89s; initial proposed-source verification was 704 passed / 5 skipped in 463.89s |
| `python -m pytest tests/postgresql -q --junitxml=.local/postgresql.xml` | **33 passed**, 70.91s; actual PostgreSQL 16.13 |
| Dedicated history, execution, authentication and Hermes security files | **113 passed**, 166.75s; also included in full suite |
| `python -m pytest tests/integration/test_hermes_9router_binding.py -q` | **1 passed**, 14.78s; installed native source, offline SDK doubles and denied outbound network |
| Node 22.23.3: `npm ci --ignore-scripts` | PASS, lockfile unchanged, zero reported vulnerabilities |
| `npm test` | **86 passed**, 14 files, 48.64s |
| `npm run typecheck` | PASS |
| `npm run build` | PASS, 17.20s |
| `npm run test:e2e` | **17 passed**, 4.3m; fresh API/database/authority for every case, no retries |
| `ruff check .` | PASS, zero findings under documented E4/E7/E9/F/B policy |
| `npm run format:check` | PASS, all configured frontend files |
| `actionlint` | PASS, actual workflow validation |
| `uv lock --check --offline` | PASS |
| `python scripts/check_repository.py` and `git diff --check` | PASS |
| `pip-audit --skip-editable --format json`, then `scripts/check_dependency_audit.py` | PASS; 73 distributions represented, no known advisory, installed inventory verified |
| `npm audit --audit-level=high --json` | PASS; zero advisories at any severity, 231 dependencies |
| `gitleaks git . --redact --log-opts='--all'` | PASS; 48 baseline commits, two exact reviewed synthetic fixture exceptions |
| `python scripts/build_delivery.py`, delivery and unpacked wheel Gitleaks scans | PASS for local review artifact, including isolated built-wheel imports; local source correctly labelled modified |

The five skips are three live paid-model opt-in scenarios and two Hermes tests
requiring a live runtime API credential. No paid inference was performed. Optional
native installation and platform-specific tests can add explicit skips on runners
without that installation/platform; the dedicated native Linux gate cannot silently
skip its configured runtime. Two backend/PostgreSQL deprecation warnings concern
Starlette TestClient/httpx and Authlib/httpx, not failed assertions. Vite reports the
existing approximately 712 KiB JavaScript chunk; size optimization remains separate.

The initial full backend command ran from an ignored verification source tree containing
all proposed code changes and the original `.env.example`. A concurrent local edit
to that file removed the loopback defaults and caused an initial endpoint example
assertion failure. That unrelated edit is preserved locally and excluded from this
commit. It was never overwritten to obtain a passing result. That example subsequently
returned to its original contents without a task edit. The latest full **712-test**
validation ran directly from the repository after adding the coverage/security tests.
The exact checked-in source will be tested again by Actions.

Initial Ruff autofixes removed imports that also register Studio fixtures. The full
suite caught those missing fixtures; explicit fixture import aliases restore them.
All existing Python test assertion ASTs were reviewed against the baseline and
retained. Frontend changes outside the E2E fixture/configuration are formatting.

## Live PostgreSQL evidence and fixes

A disposable digest-pinned PostgreSQL 16.13 container was used on loopback port
55432. Provisioning used the disposable administrator; each test generated a distinct
database, a migration owner and a restricted **non-owner application writer**. Product
operations never ran as the superuser. Explicit selection of PostgreSQL tests without
the PostgreSQL connection or roles fails instead of falling back to SQLite.

The tests prove fresh migrations through `015_authentication_boundary`, empty full
downgrade/upgrade, `012` upgrade compatibility, and populated `015`/`014` compatibility.
There is no new schema migration. They exercise atomic publication failure, concurrent
publication/baseline acceptance, rollback CAS/idempotency, READ COMMITTED visibility,
row locking, concurrent budget reservations and exactly-once usage settlement.

Actual concurrent completion exposed a race: the budget row was locked but a stale
RunState could still say usage was unsettled. Write transactions now lock/reload the
run before terminal/settlement decisions. The negative test verifies one settlement
and identical captured response under concurrent retries.

A deterministic concurrent baseline/publication test reproduced a PostgreSQL
deadlock: resource locks and membership locks were acquired in opposite order.
Factory approve, publish and assign now enforce current membership first, matching
baseline acceptance and rollback. They still validate exact approval/evidence and
resource state after acquiring resource locks. The race now commits the baseline
and requires fresh review for the candidate, without weakening authorization.

Populated signed evidence/history tables reject UPDATE, DELETE and TRUNCATE even
through the migration owner while guards are enabled. The restricted writer also
cannot disable triggers, assume ownership, alter schemas or read server files.
Lost, corrupt or substituted independent commitment storage and old assignment
pointer replay fail closed; historical records remain readable.

Separate-process tests use different commitment directories to ensure second-owner
rejection comes from the actual PostgreSQL advisory lock. Terminating the owner's
database connection fences its stale completion; replacement recovery records
`outcome_unknown`, retains uncertain reservation, and does not invent cancellation.
Authenticated audit scope/timestamps and nine existing signed-provider HTTP/Core
authentication scenarios are also exercised against PostgreSQL persistence.

The independent commitment directory is outside the database container and scoped
to the test. This proves the application's trust boundary in CI, **not** VPS filesystem
permissions, durable backup/restore discipline, resistance to a compromised host or
PostgreSQL superuser disabling guards. Those deployment requirements remain open.

## GitHub Actions evidence

Initial status before commit/push: **UNVERIFIED**. YAML parsing and local actionlint
are not evidence of a successful hosted workflow. Run URLs, terminal job results,
durations, retries and exact remote SHA are recorded after the actual push.

First pushed source: `e71ad56ead7ecbb4b4d35cd34e31ace9912b74a9`.
[Initial hosted run](https://github.com/aryn-labs/aryn/actions/runs/37783317962)
exposed a native environment setup defect: JSON Schema is an optional upstream
Hermes dependency but required by ARYN's imported contracts. The confined HTTP adapter
also requires optional aiohttp. The route test correctly
failed with a missing dependency; it was not skipped or weakened. CI now installs
the required contract/HTTP/security closure from ARYN's immutable lock, with wheel hashes,
no dependency resolution and consistency verification. The audit gate also requires
that contract dependency and exact installed versions; its positive/negative tests now total **8 passed**.
Materializing the complete environment also exposed **18 advisories in 3 packages**
(multidict 6.7.1, PyJWT 2.13.0 and urllib3 2.7.0). They were not waived or excluded
from scanning. Native source remains pinned, but its obsolete distribution metadata
is not installed; the reviewed source profile overlays secure dependencies from
ARYN's lock before native imports. The lock adds seven optional runtime dependencies,
now **80 packages** in total, with the existing Core/dev resolution preserved.
The source probe passed **1 test in 10.14s** with this profile, `uv pip check` passed,
and a complete **88-distribution** Windows profile audit reported **zero advisories**.
The installed user runtime is untouched; it does not inherit that security PASS.

Artifact upload moves to a pinned Node 24 action to remove the obsolete action
runtime warning. Exact-SHA mismatch and modified-source artifact guards were also
tested locally and rejected both cases before writing an artifact.

The first Linux backend job passed **686 / 23 skipped / 33 deselected** in 179.63s;
skips are 17 Windows PowerShell tests, 3 live paid-model scenarios, 2 live credential
tests and 1 uninstalled native runtime (covered by the separate mandatory native job).
Hosted PostgreSQL passed **33** in 44.90s; frontend, all three browser shards and
security/configuration passed. The Linux Python audit verified **71 distributions**,
with no advisory; different platform inventory is explicitly checked, not assumed
equal to Windows. The final corrected run must pass all gates before delivery.

The installed Windows Hermes launcher uses additional dependency directories;
auditing its base site-packages alone found only pip. That incomplete inventory is
**not** a dependency security PASS. CI instead materializes the pinned upstream
lock plus the reviewed security profile on Linux and rejects incomplete inventory with eight positive/negative checker
tests. Its dependency audit and clean exact-commit delivery remain UNVERIFIED until
their hosted jobs finish.

The initial hosted run finished **FAIL** after 20m19s: native setup failed and the
Windows backend timed out, so delivery was correctly skipped. Its interrupted JUnit
contains 360 passes / 6 skips, zero assertion errors, covering only 366 of 709 cases.
The slowest captured case took 36.66s; progress was continuing, not a stalled worker.
Windows now partitions sorted test identities across four independent runners,
keeping the original 20-minute limit and all assertions. Linux still runs the whole
suite. The gate validates both full collections, commit identity, disjoint Windows
union and actual JUnit case counts; missing, overlapping, interrupted and substituted
commit evidence is rejected by **6 local tests**. Actual local collection verifies
**717 cases**, split **180/179/179/179** with no missing/duplicated identity. This
addresses runner throughput without relaxing SQLite durability. The added timeout
stack dump only improves diagnosis and does not change test success semantics.

## Repository gates and residuals

Branch protections were read-only audited: neither `development` nor `main` had a
protection rule. No setting was changed. The owner should enable required PR review,
the stable `Required Quality Gates` status check, up-to-date branches and restrictions
on force pushes/deletion, using [the documented settings](ci-delivery.md). Dependabot
and manual workflow discovery require configuration on GitHub's default branch;
an owner-reviewed promotion PR is required, without changing `main` in this task.

No production release, package publication or deployment occurs. Artifacts are for
infra review, bind to the tested SHA and include file SHA-256 metadata and frozen
dependency descriptions. They exclude operational databases, authority stores,
credentials and diagnostic logs. This is not a signed SLSA attestation or installer.

The explicit Ruff correctness policy fixes the historical unused-import and compound
statement blockers. The broader unconfigured UP/I/RUF style backlog is documented;
it is not hidden by wildcard exclusions or represented as fully remediated.

Before VPS deployment: verify the real IdP, HTTPS/TLS, reverse proxy trust, private
runtime networking/firewall, PostgreSQL service/roles and commitment storage ACLs,
single-owner startup/operations and recovery/backup procedures. Signed offline
provider tests and container PostgreSQL do not establish production readiness.

## Changed files and removed placeholders

The complete delivered source file inventory and removed `.gitkeep` paths are
recorded below. `.env.example` is deliberately excluded as an unrelated local edit.

Delivered files (including deleted placeholders):

```text
.github/dependabot.yml
.github/workflows/.gitkeep
.github/workflows/quality.yml
.gitleaksignore
.node-version
.python-version
README.md
STATUS.md
alembic.ini
apps/web/.gitkeep
apps/web/e2e/fixtures.ts
apps/web/e2e/studio.spec.ts
apps/web/index.html
apps/web/package.json
apps/web/playwright.config.ts
apps/web/src/components/agent-flow.tsx
apps/web/src/components/canvas/aryn-canvas.tsx
apps/web/src/components/canvas/canvas-builders.ts
apps/web/src/components/canvas/canvas-inspector.tsx
apps/web/src/components/version-form.tsx
apps/web/src/features/bench.tsx
apps/web/src/features/factory.tsx
apps/web/src/features/governance.tsx
apps/web/src/features/runs.tsx
apps/web/src/lib/types.ts
apps/web/src/styles.css
apps/web/src/test/bench-suite-contract.test.tsx
apps/web/src/test/canvas-inspector.test.tsx
apps/web/src/test/canvas-laboratory.test.tsx
apps/web/src/test/gateway-readiness.test.tsx
apps/web/src/test/run-result-contract.test.tsx
apps/web/src/test/setup.ts
apps/web/src/test/studio-ux-laboratory.test.tsx
database/migrations/.gitkeep
database/migrations/env.py
database/repositories/approval_repo.py
database/repositories/run_state_repo.py
docs/ci-delivery.md
docs/ci-validation.md
docs/core-execution-hardening.md
docs/deployment-security.md
modules/agent_factory/service.py
modules/bench/.gitkeep
modules/bench/evidence.py
modules/bench/scenarios.py
modules/core/approvals/.gitkeep
modules/core/audit/.gitkeep
modules/core/identity/.gitkeep
modules/core/permissions/.gitkeep
modules/core/usage/.gitkeep
modules/core/workflows/.gitkeep
modules/core/workflows/coordinator.py
packages/contracts/.gitkeep
packages/model_adapters/providers/mock.py
packages/runtime_adapters/hermes/.gitkeep
pyproject.toml
scripts/.gitkeep
scripts/build_delivery.py
scripts/check_backend_coverage.py
scripts/check_dependency_audit.py
scripts/check_repository.py
scripts/install_quality_tools.py
services/api/.gitkeep
tests/backend_selection.py
tests/conftest.py
tests/e2e/.gitkeep
tests/e2e/test_smoke_end_to_end.py
tests/hermes_gateway_check.py
tests/integration/.gitkeep
tests/integration/test_9router_studio.py
tests/integration/test_agent_lifecycle_workflow.py
tests/integration/test_bench_baseline_regression.py
tests/integration/test_bench_engine.py
tests/integration/test_bench_regression_api.py
tests/integration/test_bench_stream_contract.py
tests/integration/test_hermes_9router_binding.py
tests/integration/test_hermes_adapter_integration.py
tests/integration/test_schema_migration_compatibility.py
tests/postgresql/conftest.py
tests/postgresql/test_hosted_authentication.py
tests/postgresql/test_hosted_persistence.py
tests/security/.gitkeep
tests/security/test_9router_discovery.py
tests/security/test_agent_security_and_governance.py
tests/security/test_bench_baseline_authority.py
tests/security/test_bench_engine_integrity.py
tests/security/test_core_persistence_security.py
tests/security/test_deployment_authentication.py
tests/security/test_endpoint_configuration.py
tests/security/test_governance_history_integrity.py
tests/security/test_hermes_security_gates.py
tests/security/test_rbac_authorization_boundary.py
tests/security/test_uat_model_availability.py
tests/security/test_version_payload_integrity.py
tests/unit/.gitkeep
tests/unit/test_agent_contracts.py
tests/unit/test_agent_factory_and_bench.py
tests/unit/test_backend_selection.py
tests/unit/test_bench_graders.py
tests/unit/test_bench_regression.py
tests/unit/test_contracts.py
tests/unit/test_dependency_audit.py
tests/unit/test_gemini_status_audit.py
tests/unit/test_persistence_repos.py
uv.lock
```

Removed redundant placeholders (18):

```text
.github/workflows/.gitkeep
apps/web/.gitkeep
database/migrations/.gitkeep
modules/bench/.gitkeep
modules/core/approvals/.gitkeep
modules/core/audit/.gitkeep
modules/core/identity/.gitkeep
modules/core/permissions/.gitkeep
modules/core/usage/.gitkeep
modules/core/workflows/.gitkeep
packages/contracts/.gitkeep
packages/runtime_adapters/hermes/.gitkeep
scripts/.gitkeep
services/api/.gitkeep
tests/e2e/.gitkeep
tests/integration/.gitkeep
tests/security/.gitkeep
tests/unit/.gitkeep
```
