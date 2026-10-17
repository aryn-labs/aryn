# Runtime consolidation verification

Baseline: `024dd77a833c7fd865944a1206c98e3b5421e399`, `main`.
Offline verification: 17 October 2026, Asia/Bangkok, before commit/push.
The owner authorized commit/push on 18 October 2026. The results below preserve
the offline review snapshot; exact-commit CI remains the remote delivery gate.
This report distinguishes local verification from commit-bound CI and live
provider/hosting evidence. Final local result artifacts are under `.local/` and
are not committed secrets or a published delivery artifact.

## Audit and implementation evidence

The working tree was clean before the audit. `AGENTS.md`, README, model/runtime
contracts, adapters, Core, Factory, Bench, Studio, Web, launchers, security,
configuration and integration tests were inspected. The documentation repository
contains an index/scaffold rather than the approved strategic documents.

Hermes 0.21.6 at `3637c512fc3211bdccb61b7140d09ac1018508ba` was inspected and
executed with HTTP doubles and denied external networking. Its 63 discovered
toolsets and native API flags are recorded in `.local/runtime-inventory-audit.json`.
The selective nonsecret global configuration audit records 58 installed skill
files, local terminal backend, enabled memory/compression and no enabled API
toolsets. Global user state/configuration was not changed or copied into ARYN.
9Router 0.5.91 was inspected from its installed package/source; actual provider
accounts, retries, costs and live availability remain unverified.

`runtime-control-plane.md` gives the architecture and complete capability matrix.
The removed adapters are Gemini, Mock and Nous descriptors. Default model policy
does not select a mock. Historical provider/version data stays readable; new
provider policy must use 9Router. Optional typed Hermes metadata uses existing
canonical version storage and signatures, with no database migration or evidence
rewrite. Existing simulation/UAT composition is explicit and cannot substitute
for an unavailable production gateway.

Core now governs immutable skill content pins, discovered toolsets, exact native
action bindings, worker resource/isolation policy, signed pre-dispatch decisions,
current approval, owner/RBAC, grants, budgets, cancellation and idempotency. Web
Settings and the existing Agent Factory inspector expose the corresponding
controls. Draft preview cannot silently ignore or authorize native capabilities.

## Commands and retained results

The following are actual commands used in this work; earlier failing/interrupted
reports remain separate from final evidence. A passing targeted rerun is not
presented as a passing full suite.

| Verification | Command / composition | Retained evidence |
|---|---|---|
| Core, gateway, skills, native approvals, scope negatives | `uv run --frozen --extra dev pytest tests/security/test_runtime_control.py ...` | `runtime-control-current.xml`, `runtime-policy-current.xml`, `runtime-control-isolation.xml` |
| Factory/canvas/Core regressions | `pytest tests/security/test_runtime_control.py tests/integration/test_agent_editor.py tests/integration/test_agent_canvas.py tests/security/test_core_execution_authority.py -n 4 --dist worksteal ...` | 84 passed at that source; `skills-governance-regressions.xml` |
| GitHub UAT / completeness gate compatibility | `pytest tests/unit/test_backend_selection.py tests/integration/test_github_uat.py -n 4 --dist worksteal ...` | 49 passed; `compatibility-regressions.xml` |
| Gateway/native/HTTPS boundary regressions | `pytest tests/security/test_runtime_control.py tests/integration/test_9router_studio.py tests/security/test_hermes_security_gates.py tests/integration/test_github_tools.py::test_normalization_discards_extra_fields_and_bounds_untrusted_data tests/integration/test_github_tools.py::test_http_errors_are_distinct_failed_no_retry ...` | 44 passed; `gateway-native-final-targeted.xml` |
| Installed native Hermes binding / launchers | `pytest tests/integration/test_hermes_9router_binding.py tests/security/test_hermes_security_gates.py tests/unit/test_studio_launcher.py ...` | 24 passed at that source; `native-boundary-current.xml` |
| Actual native sandbox | `python scripts/prepare-native-worker.py --hermes-source <installed source> --base-image <reviewed image> --output .local/native-worker`; `python -m tests.native_worker_check --manifest .local/native-worker/manifest.json` | `native-worker-verification.log`, immutable `native-worker/manifest.json` |
| Frontend | Pinned Node 22.23.3; Vitest, TypeScript, ESLint, Prettier, Vite | `frontend-current.json`, lint/typecheck/build logs; final results appended below |
| Browser | Playwright shell/home, chat, projects, agents, operations, workflows, intelligence configs | `browser-*-current.log`, existing screenshots/traces/report directories |
| PostgreSQL | Disposable PostgreSQL 16.13, migration owner and restricted writer; `pytest tests/postgresql` | `postgresql-current/postgresql.xml` |
| Python dependencies | `pip-audit --skip-editable --format json` plus the existing audit checker | `consolidation-python-audit.json` |
| Native image dependencies | Read-only image, temporary cache; `pip-audit --skip-editable --format json` | `consolidation-native-audit.json` |
| Node dependencies | `npm audit --audit-level=high --json` | `consolidation-node-audit.json` |
| Repository / Actions / lock | `ruff check .`, `scripts/check_repository.py`, actionlint, `uv lock --check --offline` | associated `.local/consolidation-*.log` |
| Secret scans | Gitleaks full history and current source snapshot, redacted | `consolidation-history-secrets.json`, reviewed source report |

Native verification uses real official terminal/read/write/patch/search handlers
in a bounded container, with a labelled offline model double. It verifies a
multi-turn file sequence, no network/credentials, denied protected-root writes,
no cross-run file access, signed admission/results, and container cleanup.
Expected denied operations are security PASS evidence, not successful writes.
No provider inference, paid model request, global native skill installation or
public deployment occurred.

The source scan found two unchanged, previously reviewed synthetic fixtures:
the RBAC rotation test's old key string and the persistence test's idempotency
key. Their exact source lines were verified before translating the existing
historical exclusions to local snapshot fingerprints. No broad scanner rule,
assertion, required gate or repository ignore was weakened.

## Linux CI performance and coverage

Run `38903239923` was inspected directly. Its Linux job was cancelled at the
20-minute limit after approximately 60% of the collection; Windows shards and
other functional jobs succeeded. A retained Windows shard contains 414 cases
and roughly 501 seconds of aggregate test time. An unpartitioned full collection
does not fit the old Linux wall-clock budget as coverage grows.

Setup/call/teardown JSON-lines profiling was added, including failed/interrupted
runs, rather than increasing the timeout. Initial local profiles identify calls
as the dominant cost; fixture setup/teardown is recorded separately. The initial
consolidation also exposed implicit mock-catalog dependencies and stale synthetic
JUnit fixtures. These were corrected through explicit test composition and real
identities, preserving assertions. One initial HTTPS regression exceeded its
approved deadline under concurrent host load; its complete affected suite passed
when run separately. Those initial failures are retained, not labelled PASS.

Linux now executes the complete same collection with three xdist workers and
`--dist worksteal` inside the existing job. Windows keeps its four deterministic
shards. Every worker collection must agree. The coverage checker now compares
actual JUnit identities against each selection manifest, in addition to count,
commit, overlap and union checks. The 20-minute Linux timeout, 14-job topology and
required delivery dependencies remain unchanged. No test or new skip was added
to make CI pass. Existing Windows-only launcher skips on Linux and explicit live
provider opt-outs are reported by identity; dedicated native verification remains
mandatory.

Remote CI **14/14 and the Validated Delivery Artifact require verification on
the owner-authorized pushed SHA**. Local timing is evidence about this host/container,
not a fabricated successful rerun of the historical GitHub Actions run.

## Readiness

| Classification | Meaning in this delivery |
|---|---|
| Implemented | Single model policy/gateway path, secure volatile connection lifecycle, native metadata, skill pins, exact native action grants, isolated filesystem/terminal execution, Web controls |
| Offline verified | Actual native Hermes with HTTP doubles; actual Docker tools with isolated model; Core and security regressions and local browser/database checks as recorded below |
| Live verified | No live model/provider capability or billing claim is made |
| Blocked by upstream provenance | Installed 9Router source has no `provider_configuration` producer; the existing live tool-probe gate requires that revision in catalog/completion evidence. Offline native actions cannot grant live model eligibility |
| Unsupported by installed native API | Config admin writes, memory-write API, audio API, realtime voice flags are false; native skill mutations do not have the required scoped API lifecycle |
| Blocked by security boundary | Raw native sessions, persistent native memory, unmediated browser/credentials/external writes, jobs/scheduler dispatch, children/delegation, interactive native run approvals and raw token event forwarding |
| Awaiting deployment verification | Tenant-isolated hosted gateway binding, trusted persistent credential provider, hardened dedicated worker/image operations, actual gateway/provider receipts and exact-commit CI |

This is not a production-ready label. The upstream/security blockers and their
resolution conditions are explicit in the capability matrix. They are not
silently simulated or deferred behind a development-stage naming scheme.

## Final working-tree verification

The final implementation fingerprint (all tracked/current implementation files,
dependencies, workflows and tests, excluding Markdown) is
`c8392000a29162112b2a4461c2dd83f22162e0d216ad6f4dc0b88df8804cf229`.
`.local/consolidation-file-inventory.json` records each source hash and the full
change list. Markdown reporting updates do not change that implementation hash.

The baseline selection manifest contains 1,653 distinct backend identities.
The final collection contains 1,688: **zero removed, 35 added**. Local manifests
are explicitly uncommitted (`commit: null`); they do not impersonate CI evidence.
The final cross-platform report checks JUnit identities, manifest equality and
the baseline subset directly. It does not fabricate four Windows CI shard reports.

The interrupted Windows verification retained under `windows-final` exposed the
deleted provider namespace lookup test: Python raises `ModuleNotFoundError` when
the parent namespace itself is absent. The test now verifies that exact missing
parent or the missing child specification, alongside absent source files and
adapter exports. Its isolated rerun passed all three identities. Verification was
restarted against the frozen implementation; interrupted output is not PASS.

The final startup audit additionally found native bootstrap update completion,
repair and dependency-lease side effects. The dedicated process now uses the
upstream read-only dependency selector, refuses pending repair markers and
blocks automatic mutation/lazy installation. Six targeted tests, including
actual installed Hermes, passed; the home-ancestor negative also passed. Linux
was restarted under `linux-frozen` after that final hardening. Earlier green
Linux reports are retained as earlier-source evidence.

The complete Linux run under `linux-governance-current` passed 1,665 tests with
23 existing skips in 876.26 seconds. PostgreSQL passed all 144 tests in 442.60
seconds. After the coverage-checker correction below, Windows completed with
**1,683 PASS, 5 SKIP, zero FAIL/ERROR in 729.52 seconds** under `windows-review`.
Its 1,688 JUnit identities match its selection manifest directly. The skips are
three explicit model-inference opt-outs and two authenticated runtime health/
capability checks lacking `API_SERVER_KEY`; those latter checks do not run model
inference. Linux then completed with **1,665 PASS, 23 SKIP, zero FAIL/ERROR in
779.81 seconds (12 minutes 59 seconds)** under `linux-runtime`. Its collection
and executed JUnit identities equal Windows directly, with all 1,653 baseline
identities retained and 35 added. The extra Linux skips are 17 Windows-only
launcher tests and the installed-runtime test exercised separately in dedicated
native verification. No new skip or assertion change was introduced.

Final setup/call/teardown profiles are aggregate seconds across three workers;
they are not additional wall-clock durations:

| Platform | Setup | Call | Teardown | Pytest wall time |
|---|---:|---:|---:|---:|
| Linux | 554.95 | 1,719.83 | 16.89 | 779.81 |
| Windows | 507.51 | 1,631.01 | 18.66 | 729.52 |

The final Linux result leaves about seven minutes under the unchanged 20-minute
job limit on this verification host/container. GitHub runner setup, scheduling,
resource contention and artifact upload still require exact-commit CI evidence;
this measurement does not claim that remote 14/14 has already run.

Comparing actual JUnit names with the manifest exposed a parser defect in the
new identity check: IPv6 parameters containing `::` were incorrectly split as
Python namespaces. The checker now separates the parameter suffix before
splitting the address, matching pytest's JUnit format. Existing completeness
fixtures now include IPv6 and class-based identities; a same-count substituted
identity must still fail. All six focused coverage tests passed. No collected
test identity was removed or renamed. Final full runs include this correction.

The four-worker Linux profile completed in 887.25 seconds with one GitHub tool
deadline failure: 836.51 seconds aggregate setup, 2630.08 call and 18.81 teardown
across workers. The fixture's parent run had 120 seconds, while its approved tool
operation had three seconds; retained audit timing shows the tool decision at
11:20:21.654 UTC and `outcome_unknown/execution_deadline` at 11:20:25.347 UTC.
The analogous Windows run also reached a connector deadline. Neither is PASS.

Source profiling found unnecessary durable intent/finalization writes for
verification-only governance transactions. The optimization is SQLite-only and
requires a read-only SQL profile, an unchanged DBAPI `total_changes` counter
and no mutation authorization after flush. The SQLite authorizer is reset per
transaction so cached SQL is reauthorized; raw callback DDL is also detected.
Legacy connections lacking that authorizer retain the original protocol.
DML, DDL, unknown SQL, `SELECT` functions that mutate rows or schema,
PostgreSQL and every protected-head update retain the original durable protocol.
For a true read-only transaction, the independent store's writer lock covers
signature/pending/head verification **through application database commit**.
There is no authority cache or relaxed deadline. History format/signatures remain
unchanged. Eight new atomic tests verify unchanged store bytes, changed heads,
pending intents, concurrent lock coverage and lost ACK after row/DDL/function
mutations, including DDL from a SQL callback. Broader history/GitHub regressions
passed before final full reruns.

The other completed verification results are:

| Check | Actual outcome |
|---|---|
| Linux full backend, final source | 1,665 PASS, 23 existing SKIP, 0 FAIL, 779.81 seconds |
| Windows full backend, final source | 1,683 PASS, 5 existing SKIP, 0 FAIL, 729.52 seconds |
| PostgreSQL 16.13, restricted writer | 144 PASS, 0 FAIL/SKIP, 442.60 seconds |
| Frontend unit tests | 128 PASS, 0 FAIL/SKIP, 17 files |
| Browser shell/home | 90 PASS |
| Browser chat / projects / agents | 29 / 12 / 14 PASS |
| Browser operations / workflows / intelligence | 15 / 14 / 16 PASS |
| Browser total | 190 PASS, no retries or added skips |
| Native container actions, frozen Core | PASS: five scenarios; two expected tool failures are verified denials, not successful effects |
| Native Windows / read-only bootstrap | Targeted installed runtime and standalone launcher PASS, no inference |
| Native Linux API with hash-locked overlay | PASS, every protocol marker, exit 0, denied external networking |
| Application / tool-worker / API verification image dependency audits | 89 / 112 / 119 distributions, complete inventory/version match, no known advisory |
| Node audit | 608 dependency records; zero advisory at every severity |
| Ruff / Actions / repository hygiene / lock check | PASS |
| Frontend format / lint / TypeScript / Vite build | PASS; existing large-bundle warning remains nonfatal |
| Gitleaks history | 93 commits, zero unreviewed findings |
| Gitleaks source / unpacked final wheel | PASS; source uses only the two exact previously reviewed synthetic fixture fingerprints |

Two full Linux runs overlapped briefly during the final startup audit. Connector
fixture failures appeared in the older run under that load; neither interrupted
run is counted as a final PASS. Their timing/interruption records are retained.
The final platforms run separately with unchanged deadlines and assertions.

The browser rerun under `browser-chat-governance.log` recorded 28 PASS and one
Home-readiness failure in the 390-pixel dark case. The retained trace shows the
Home loading state rather than a chat composer at the existing five-second
assertion deadline. API responses in that trace succeeded; the evidence does not
establish a definitive cause. The failure/trace is retained separately under
`browser-chat-failure`; the complete chat suite is rerun without changed
assertions, timeouts or retries. Other browser suites completed successfully.
The complete chat rerun (`browser-chat-runtime.log`) then passed all 29 cases,
including the previously affected case, with no source/test change. Together
with the other six completed suites this gives 190 browser PASS. The earlier
failure is not reclassified as PASS and its root cause remains unproven.

The later `windows-runtime` run stopped before emitting complete JUnit or a
process result, and its process was absent on resumption. It is interrupted
evidence, not PASS. `windows-review` and `linux-runtime` are the last complete
verification locations for the unchanged implementation fingerprint above.

The final bootstrap also executed successfully in Linux against the archived,
immutable Hermes source image, with networking denied and HTTP/model doubles.
Its tool-worker base deliberately omits `aiohttp`; the first API composition
failed with that missing optional dependency. A separate verification image
then overlaid the same 16 hash-locked API dependencies used by CI and passed
all native markers (`native-linux-api/native.log`, exit 0). No installed/global
dependency environment was changed. This is an actual native runtime check,
not a live model-provider check.

That disposable Linux API image links SQLite 3.46.1. Native Hermes detected the
WAL-reset corruption issue and explicitly selected DELETE journaling for its
owned test databases. Installed Windows Hermes links SQLite 3.53.1. Dependency
distribution audits do not certify the operating system, container kernel or
SQLite library; those remain deployment image review responsibilities.

Exact final test commands:

```text
# Windows: Python 3.12.12, locked dependencies; full collection, three local workers
uv run --frozen --extra dev pytest -m 'not postgresql' --backend-shard=1/1 -n 3 --dist worksteal -q --tb=short --durations=25 --timing-report=.local/windows-review/backend-timings.jsonl -o faulthandler_timeout=120 --junitxml=.local/windows-review/backend.xml

# Linux: Python 3.12.12 container, no network, 4 CPUs, 4 GiB; same copied source
PYTHONPATH=/work pytest -m "not postgresql" --backend-shard=1/1 -n 3 --dist worksteal -q --tb=short --durations=25 --timing-report=/results/backend-timings.jsonl -o faulthandler_timeout=120 --junitxml=/results/backend.xml

# Disposable real PostgreSQL 16.13, migration owner plus restricted product writer
PYTHONPATH=/work pytest tests/postgresql -q --tb=short --junitxml=/results/postgresql.xml

# Actual installed Hermes; test process replaces native HTTP/model transport only
uv run --frozen --extra dev pytest tests/integration/test_hermes_9router_binding.py -q --junitxml=.local/native-installed-final.xml --basetemp=.local/native-boundary-evidence

# Real native Docker handlers and scoped Core continuation, explicitly offline model
uv run --frozen --extra dev python -m tests.native_worker_check --manifest .local/native-worker/manifest.json

# Pinned Node 22.23.3, from apps/web
npm.cmd test -- --reporter=json --outputFile=../../.local/frontend-final.json
npm.cmd run format:check
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:e2e
npm.cmd run test:chat:e2e
npm.cmd run test:projects:e2e
npm.cmd run test:agents:e2e
npm.cmd run test:operations:e2e
npm.cmd run test:workflows:e2e
npm.cmd run test:intelligence:e2e
```

The review wheel is built from a clean source snapshot, avoiding stale build
cache artifacts. The new Core/native contracts, adapters and bootstrap modules
are included; removed provider paths and the tests fixture package are absent.
The existing fixed GitHub operator UAT diagnostic shim remains packaged for
compatibility; it requires explicit isolated composition and is never a
production gateway fallback. Extracted-wheel imports
and Gitleaks passed. `review-metadata.json` marks `source_modified: true` and
`local review only`; this package is not a Validated Delivery Artifact.
Its SHA-256 is
`59cb2125e1485f3e5645da4055df35aefc406d3618d8a0be48f12784aaecd8ef`.
All 155 packaged source files match the current working tree byte for byte.
The remaining four archive entries are wheel distribution metadata.

Ruff, actionlint, repository hygiene, lock consistency and `git diff --check`
passed again after the full runs. Source, extracted wheel and built Web secret
scans passed. No disposable verification container or network remains running.
The installed Hermes checkout remains clean at its audited revision and its
global configuration checksum is unchanged. At the offline review snapshot,
HEAD remained the original baseline and no commit/push had occurred. Subsequent
owner authorization permits delivery; no real-key request or public deployment
is authorized by that delivery step.

`.local/runtime-review-index.json` provides checksums for the final JUnit,
selection manifests, native/frontend/browser evidence, source inventory, wheel
and these review documents. `.local/consolidation-test-summary.json` records
both complete collections, every skip reason and aggregate timing. The source
fingerprint covers implementation/tests/workflows, while the index separately
binds Markdown reporting. All are local review evidence with `source_modified:
true`, not signed/commit-bound remote delivery validation.

## File changes

The final scope is **16 added, 67 modified, 3 deleted files**. Existing security
test identities and assertions remain; test composition now explicitly supplies
offline catalogs. No historical file was renamed to fit the new architecture.

| Change | Repository path |
|---|---|
| Modified | `.github/workflows/quality.yml` |
| Modified | `README.md` |
| Modified | `apps/web/src/app/router/pages.tsx` |
| Modified | `apps/web/src/features/agents/AgentInspector.tsx` |
| Modified | `apps/web/src/features/agents/api.ts` |
| Added | `apps/web/src/features/settings/RuntimeControl.tsx` |
| Modified | `apps/web/src/features/settings/preferences.css` |
| Added | `apps/web/src/features/settings/runtime-control.test.tsx` |
| Modified | `database/connection.py` |
| Modified | `docs/9router-gateway.md` |
| Modified | `docs/ci-validation.md` |
| Modified | `docs/deployment-security.md` |
| Added | `docs/runtime-consolidation-validation.md` |
| Added | `docs/runtime-control-plane.md` |
| Modified | `modules/agent_factory/service.py` |
| Modified | `modules/core/agent_preview.py` |
| Modified | `modules/core/history.py` |
| Added | `modules/core/runtime_control.py` |
| Modified | `modules/core/tools.py` |
| Modified | `modules/core/workflows/coordinator.py` |
| Modified | `packages/contracts/agent.py` |
| Modified | `packages/contracts/agent_builder.py` |
| Modified | `packages/contracts/model.py` |
| Added | `packages/contracts/native_tool.py` |
| Modified | `packages/contracts/runtime.py` |
| Added | `packages/contracts/runtime_control.py` |
| Modified | `packages/contracts/tool.py` |
| Modified | `packages/model_adapters/__init__.py` |
| Modified | `packages/model_adapters/gateway.py` |
| Deleted | `packages/model_adapters/providers/gemini.py` |
| Deleted | `packages/model_adapters/providers/mock.py` |
| Deleted | `packages/model_adapters/providers/nous.py` |
| Modified | `packages/model_adapters/router.py` |
| Modified | `packages/runtime_adapters/hermes/adapter.py` |
| Added | `packages/tool_adapters/native.py` |
| Modified | `pyproject.toml` |
| Modified | `scripts/check_backend_coverage.py` |
| Modified | `scripts/github_uat.py` |
| Modified | `scripts/hermes-9router.py` |
| Added | `scripts/prepare-native-worker.py` |
| Modified | `scripts/start-aryn.ps1` |
| Modified | `scripts/start-studio.ps1` |
| Modified | `services/api/__main__.py` |
| Modified | `services/api/agent_canvas.py` |
| Modified | `services/api/studio.py` |
| Added | `services/runtime/bootstrap.py` |
| Modified | `services/runtime/gateway_transport.py` |
| Modified | `services/runtime/hermes_9router.py` |
| Added | `services/runtime/inventory.py` |
| Added | `services/runtime/native_worker.py` |
| Modified | `tests/conftest.py` |
| Modified | `tests/e2e/test_smoke_end_to_end.py` |
| Modified | `tests/gateway_fixtures.py` |
| Modified | `tests/hermes_gateway_check.py` |
| Modified | `tests/integration/test_agent_lifecycle_workflow.py` |
| Modified | `tests/integration/test_agent_registry_rollback.py` |
| Modified | `tests/integration/test_assignment_activation_migration.py` |
| Modified | `tests/integration/test_hermes_9router_binding.py` |
| Added | `tests/model_fixtures.py` |
| Added | `tests/native_worker_check.py` |
| Modified | `tests/postgresql/conftest.py` |
| Modified | `tests/postgresql/test_hosted_persistence.py` |
| Modified | `tests/postgresql/test_projects_persistence.py` |
| Modified | `tests/postgresql/test_workspace_persistence.py` |
| Modified | `tests/security/test_9router_boundary.py` |
| Modified | `tests/security/test_9router_exact_model.py` |
| Modified | `tests/security/test_agent_rollback_authority.py` |
| Modified | `tests/security/test_agent_security_and_governance.py` |
| Modified | `tests/security/test_bench_evidence_integrity.py` |
| Modified | `tests/security/test_core_execution_authority.py` |
| Modified | `tests/security/test_core_persistence_security.py` |
| Modified | `tests/security/test_execution_idempotency_claims.py` |
| Modified | `tests/security/test_governance_history_integrity.py` |
| Modified | `tests/security/test_governed_tools.py` |
| Modified | `tests/security/test_rbac_authorization_boundary.py` |
| Added | `tests/security/test_runtime_bootstrap.py` |
| Added | `tests/security/test_runtime_control.py` |
| Modified | `tests/security/test_tenant_isolation_ownership.py` |
| Modified | `tests/security/test_uat_model_availability.py` |
| Modified | `tests/security/test_version_payload_integrity.py` |
| Modified | `tests/unit/test_agent_contracts.py` |
| Modified | `tests/unit/test_backend_selection.py` |
| Modified | `tests/unit/test_bench_graders.py` |
| Modified | `tests/unit/test_gemini_status_audit.py` |
| Modified | `tests/unit/test_model_router.py` |
| Modified | `uv.lock` |
