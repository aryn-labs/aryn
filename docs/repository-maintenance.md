# Repository maintenance

Cleanup baseline: `31491840dfbcadbb6ebc852a41ec0f64ee31aa73`, `main`.
The baseline [ARYN Quality run](https://github.com/aryn-labs/aryn/actions/runs/39056546049)
completed all 14 jobs successfully, including the Validated Delivery Artifact.
That result does not attest these subsequent cleanup changes.

The owner authorized local cleanup and, after offline verification, explicitly
authorized commit/push of all three repositories to `main` on 18 October 2026.
Deployment, real model credential use and paid inference remain outside scope.
Ignored databases, environments, credentials, user profiles and existing local
evidence are outside deletion scope.

## Audit and disposition

The audit covers tracked Python, TypeScript/JavaScript, styles, configuration,
scripts, test discovery, CI, launchers, native registry loading, package exports,
database migrations and documentation across the repository. Static references
are candidate evidence; framework callbacks and CLI/native entry points remain.

Eight unused Python declarations were removed: the unbounded legacy blueprint/
assignment list helpers, unused project audit/member list helpers, unused membership
suspension convenience method, unused in-memory audit-list alias, unused OutputFormat
enum and duplicate model-routing request helper. Existing bounded Core queries,
membership revocation, current model policy and historical data contracts remain.

The Gemini, Nous and Mock production provider files were already absent at this
cleanup baseline. `packages/model_adapters` retains only the package exports,
exact-model policy router and 9Router discovery gateway. Historical provider enum
values and explicit direct-adapter denial methods remain because persisted data
and negative boundary tests still require them; they provide no inference path.
No persisted field, HTTP route or schema migration changes in this cleanup.

Full verification also exposed a Core authority cleanup defect after PostgreSQL
owner termination. Fenced sessions now close without issuing further unlock SQL,
physical invalidation and close are always attempted, and the authority registry is
released even when shutdown raises. The old engine stays fenced. Three additional
security regressions reproduce the defect against historical code and pass with
the repair; all prior recovery assertions remain unchanged.

Frontend cleanup removes unused Tabs/media-query modules, unused exported aliases/
types, unreachable legacy layout wrappers/styles and the Tabs-only dependency.
Manual screenshot/live-chat scripts are superseded by maintained E2E suites.
The manual Projects harness is removed; its empty admin/viewer matrix is migrated
with every assertion into the automated disposable Projects suite. The duplicate
populated live Projects checks are already covered by that suite's API/Core flows.

Empty desktop/commercial/UI/worker/evaluation and redundant Core scaffold directories
are removed. No database migration, active route, security gate or application
capability is removed. The operator GitHub UAT, workspace benchmark, PowerShell
lifecycle launchers, native worker and test doubles remain active entry points.

## Repository separation and evidence

23 source-derived engineering references and retained runtime verification were
copied and verified byte-for-byte in sibling `aryn-docs/engineering/aryn` before
source deletion. Source commit, Git blob, original/copy hash and destination hash
are recorded in that repository's `source-history.json`. Link rebasing is recorded
separately from the verified copy. These references do not promote missing normative
corporate/PRD/architecture documents to approved baselines.
Raw copy hashes are retained alongside CRLF-to-LF normalized content hashes for
portable verification after Git checkout on Windows or Linux.

The Nginx review/UAT example was copied byte-for-byte from the application security
document to `aryn-infra/deployment/cloud/nginx.conf`, with source provenance. The
application security contract retains authentication/proxy trust requirements.
No deployment/IaC is executed; product launchers and quality-test containers stay
in the application repository.

15 superseded progress/validation/inventory documents were removed. Their exact
contents remain traceable at the baseline Git commit; current contracts, regression
tests and baseline CI evidence are preserved. No old report is presented as proof
of this cleanup.

Delivery targets `main` in all three repositories and preserves `development`
as a historical reference. Destination commits are published and verified before
application-source deletions are delivered. Application links pin the verified
destination commits; historical links pin original source commits. There are no
new compatibility wrapper documents.

Verified destination commits on remote `main`: `aryn-docs` at
`e826deba288803d8d52d51e176be5e4d8ab0fd04` and `aryn-infra` at
`939e4a48bd759c18f4f8213ad59a749f47f3e746`. All destination Git blobs and
normalized transfer hashes were verified before application publication.

Two destination placeholders are also removed after their directories are populated:

- `aryn-docs/engineering/.gitkeep`: the verified engineering documents now occupy this directory.
- `aryn-infra/deployment/cloud/.gitkeep`: the verified Nginx example, provenance and README now occupy this directory.

## Verification

These offline results apply to the reviewed cleanup implementation before publication. Python 3.12.12 and Node 22.23.3 were used; real Hermes is 0.21.6 at `3637c512fc3211bdccb61b7140d09ac1018508ba`. Native API/worker tests use isolated homes/containers and explicit model/gateway doubles. No real model credential or paid inference is used.

| Check | PASS | FAIL | SKIP |
| --- | ---: | ---: | ---: |
| Full Windows backend/security | 1686 | 0 | 5 |
| Full Linux backend/security | 1668 | 0 | 23 |
| PostgreSQL | 144 | 0 | 0 |
| Native Linux API | 1 | 0 | 0 |
| Frontend unit | 128 | 0 | 0 |
| Browser shell | 90 | 0 | 0 |
| Browser chat | 29 | 0 | 0 |
| Browser agents | 14 | 0 | 0 |
| Browser operations | 15 | 0 | 0 |
| Browser workflows | 14 | 0 | 0 |
| Browser intelligence | 16 | 0 | 0 |
| Browser projects | 14 | 0 | 0 |

Native worker: five real Docker/Hermes scenarios verified, comprising three successful runs and two expected security denials. The five terminal/filesystem handlers, network/credential confinement, forbidden host write and cross-run file isolation are covered. These denials are passing assertions, not test failures.

Both backend platforms executed 1,691 identities: all 1,688 baseline identities plus three deterministic authority-release security regressions. JUnit identities match the selection manifest, with no missing/duplicate cases; every SKIP identity and reason matches its previous platform run. The 144 PostgreSQL cases pass without SKIP. All 24 historical migrations are byte-equivalent after Git line-ending normalization. Frontend units remain 128; automated browser coverage increases from 190 to 192 by absorbing the two former manual empty-project tests. The populated Projects case also retains the removed manual harness's bilingual persistence/accessibility checks.

Existing SKIPs are explicitly gated live model/runtime checks and unavailable Windows launcher/installed-runtime checks on Linux. Dedicated native checks execute the real installed Windows Hermes and isolated Linux Hermes separately. No new SKIP, weakened assertion, changed security deadline, quality-gate change or backend test deletion is introduced.

Upstream Starlette/Authlib emit httpx deprecation warnings during backend imports. Warning filters are unchanged; these warnings are visible in the retained suite logs. The clean npm install also emits existing whatwg-encoding/eslint deprecation warnings; locked versions are not upgraded during this cleanup. The advisory result below is distinct from upstream support status. Vite also reports a 735.55 kB minified application chunk above its existing 500 kB warning threshold; the threshold is not changed.

### Commands actually executed

From the application root, with live inference disabled:

```powershell
$env:ARYN_RUN_LIVE_MODEL_TESTS = '0'
uv run --frozen --extra dev ruff check .
.local/quality-tools/actionlint.exe -color=false
uv lock --check --offline
uv run --frozen --extra dev python scripts/check_repository.py
uv run --frozen --extra dev pytest -m 'not postgresql' --backend-shard=1/1 --collect-only -q
uv run --frozen --extra dev pytest -m 'not postgresql' --backend-shard=1/1 -n 3 --dist worksteal -q --tb=short --durations=25 --timing-report=.local/cleanup-recheck-windows/backend-timings.jsonl -o faulthandler_timeout=120 --junitxml=.local/cleanup-recheck-windows/backend.xml
uv run --frozen --extra dev python -m tests.native_worker_check --manifest .local/native-worker/manifest.json
uv run --frozen --extra dev python -m build --wheel --no-isolation --outdir .local/cleanup-recheck-review-package .local/cleanup-packaging-source/aryn
.venv/Scripts/python.exe -I .local/check_cleanup_package.py
```

Docker executes the following commands over a frozen read-only snapshot of 490 tracked/nonignored application files, containing the final implementation; ignored environment files, databases, profiles and local evidence are excluded. Linux/backend/native API have no network. PostgreSQL has a private disposable network, synthetic CI credentials, no host database port, and separate scoped product writers. Owned containers/network are removed after verification; user infrastructure is untouched.

```sh
PYTHONPATH=/work pytest -m "not postgresql" --backend-shard=1/1 -n 3 --dist worksteal -q --tb=short --durations=25 --timing-report=/results/backend-timings.jsonl -o faulthandler_timeout=120 --junitxml=/results/backend.xml
PYTHONPATH=/work pytest tests/postgresql -q --tb=short --junitxml=/results/postgresql.xml
ARYN_TEST_HERMES_SOURCE=/opt/hermes ARYN_TEST_HERMES_PYTHON=/usr/local/bin/python PYTHONPATH=/work pytest tests/integration/test_hermes_9router_binding.py -q --tb=short --junitxml=/results/native.xml
```

The cached verification images and immutable IDs are recorded in `.local/cleanup-verification-images.json`. Native API dependency-environment links are created only inside its disposable container; global Hermes/9Router installations and configuration are not changed.

From `apps/web` using the pinned Node binary:

```sh
npm test -- --reporter=json --outputFile=../../.local/cleanup-recheck-frontend.json
npm run format:check
npm run lint
npm run typecheck
npm run build
npm run test:e2e
npm run test:chat:e2e
npm run test:agents:e2e
npm run test:operations:e2e
npm run test:workflows:e2e
npm run test:intelligence:e2e
npm run test:projects:e2e
npm audit --json --ignore-scripts
```

An initial Operations browser invocation was intentionally interrupted before any Docker suite ran, to replace broad working-tree copying with the audited source snapshot. Its partial log is retained; the replacement complete Operations invocation passes all 15 cases. All browser suites, including Projects and its retained bilingual assertion, were rerun after the Core authority fix; those complete rechecks are reported above.

### Initial failures and verified repairs

The first PostgreSQL run completed with 143 PASS / 1 FAIL / 0 SKIP. The unchanged lost-owner recovery test exposed an OperationalError during engine disposal: a fenced owner still issued pg_advisory_unlock on a terminated connection that the driver had not classified invalidated. Core now skips SQL unlock after fencing, always attempts physical session invalidation and close, and removes its registry entry in a finally block. Unexpected physical invalidation failures still propagate after cleanup. An old engine remains permanently fenced; a new engine must acquire its own authority. The existing PostgreSQL assertions and kill operation are unchanged.

Three added deterministic security cases all fail against the historical ownership module and pass against the repaired module. They cover lost ownership before/during close, stale-engine denial, explicit replacement acquisition, and cleanup/registry release when physical invalidation raises. Full Windows/Linux, PostgreSQL, native and browser suites are then rerun; their final results are the table above.

The first isolated Linux native API run completed with 0 PASS / 1 FAIL because its manually assembled image had discarded upstream build identity. The revision assertion is retained. The corrected owned image uses the official Hermes scripts/write_install_stamp.py output, derived from the clean installed revision and verified Git source-archive revision. It records docker distribution and external update ownership. No global Hermes file/configuration is modified and no runtime revision is invented.

The diagnostic [PostgreSQL 16 signaling contract](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-ADMIN-SIGNAL) explains why sending a termination signal and completed backend shutdown differ. The repair addresses Core cleanup itself; it does not add sleeps or alter the original PostgreSQL recovery test.

### Static, dependency and packaging evidence

Ruff, actionlint, repository hygiene, frozen uv resolution, frontend format/lint/typecheck/build and Git whitespace checks pass. AST review covers 283 Python files and 1,635 internal module references with no unresolved internal target. TypeScript compiler symbol review covers 143 source files/402 exported declarations and reports zero remaining unused exports. All 19 remaining frontend runtime dependencies have source/configuration consumers; development tooling and CLI consumers are retained. Eight environment bootstrap examples and 33 literal runtime/environment inputs were reviewed; none is removed without evidence.

The unused Tabs dependency is removed from package/lock/build configuration. npm also refreshes optional bundled WASM metadata in the lockfile; no existing dependency version is upgraded. A clean isolated npm installation, unit run and build verify that success does not depend on the deleted Tabs package remaining in the original node_modules.

The clean source copy uses an isolated Git initialization (no staging/commit) to keep the enclosing .local ignore rule from excluding Tailwind source scanning, then executes `npm ci --ignore-scripts --offline --no-audit --no-fund`, `npm test -- --reporter=json --outputFile=../cleanup-frontend-clean-unit.json` and `npm run build`. The removed `node_modules/@radix-ui/react-tabs` path is asserted absent before running the tests/build.

The npm advisory scan reports zero vulnerabilities. The existing pip-audit evaluator checks 88 exact-version third-party distributions (89 installed distributions including the local editable project) using cached PyPI advisories dated 17 October 2026; zero vulnerabilities and zero network connections are reported. This is an offline cache audit, not a fresh Python advisory lookup.

Gitleaks scans the current source snapshots of all three repositories. The raw scan finds exactly two unchanged synthetic security-test fixtures: `tests/security/test_core_persistence_security.py:195` and `tests/security/test_rbac_authorization_boundary.py:247`. Exact local fingerprints are reviewed against unchanged baseline bytes; the reviewed scan passes. No global/repository allowlist or broad exclusion is added.

The wheel contains all 155 current product Python files, verified byte-for-byte; no production legacy provider/test artifact is present. Imports from the extracted wheel pass without source-tree imports or network access; unconfigured models and fallback fail closed. Wheel SHA-256: `e3343833e9f71e01a6bc487b881b29afcd28c3b0a75c976f334fffc2ee36001a`.

The 481 final non-Markdown source/configuration/test files, including the repaired authority cleanup and its three security regressions, are bound to implementation fingerprint `63440befd95c9c43b829e4b7434a93a3dba57f5fea674a75e50b3ff31f4b3594`. The complete backend, PostgreSQL, native and browser rechecks use this repaired implementation; subsequent documentation edits do not change it. All 23 document transfers and the Nginx extraction are reverified; 22 destination links resolve against local repositories and there are no broken local Markdown links.

### Timing and readiness

| Backend | JUnit suite seconds | Aggregate setup | Aggregate call | Aggregate teardown |
| --- | ---: | ---: | ---: | ---: |
| Windows | 844.50 | 579.38 | 1897.97 | 19.07 |
| Linux | 882.21 | 579.23 | 1984.93 | 17.75 |

Aggregate phases overlap across three workers and therefore exceed suite duration. The pytest CLI reports 847.21 seconds for Windows and 882.21 seconds for Linux; the table uses each JUnit testsuite duration. Timings, JUnit and selection manifests are retained locally. Formal CI still uses its unchanged Linux runner and four Windows shards/completeness gate. The baseline Linux CI job completed in 511 seconds (8 minutes 31 seconds), within its unchanged 20-minute limit. The successful 14/14 baseline CI and Validated Delivery Artifact attest baseline SHA only; the owner authorized cleanup publication to main; fresh commit-bound CI must verify this delivery.

Status: implemented and offline verified; the owner authorized commit/push to `main`. Fresh CI must be evaluated on the resulting application commit, separately from baseline CI and offline evidence. Live model/provider, hosted authentication/network/deployment and the imported Nginx example are not newly live verified. No deployment, secret-manager/account modification or real model credential use occurs; there is no production-readiness claim.

Review evidence is retained under ignored `.local/cleanup-*` and `.local/cleanup-recheck-*`: test summary, all suite logs/JUnit, source/import/export/discovery integrity checks, dependency/secret audits, image IDs, packaging integrity and per-file disposition. These are local review artifacts, not uploaded user data.

## Deleted source files and exact disposition

All report contents remain retrievable at the baseline commit. Transferred documents additionally have verified local destination copies and provenance.

| Source file | Technical reason / destination |
| --- | --- |
| `STATUS.md` | Obsolete implementation inventory; current README, engineering contracts and commit-bound CI preserve useful status/evidence. |
| `apps/desktop/.gitkeep` | Empty, unregistered scaffold with no product/test/build consumer; actual Core modules and supported domains remain. |
| `apps/web/VALIDATION.md` | Historical frontend validation snapshot; maintained unit/browser suites and this verification replace its status claims. |
| `apps/web/e2e/projects-empty-live.spec.ts` | Both admin/viewer tests and every viewport/theme/permission/accessibility assertion migrate to automated Projects discovery. |
| `apps/web/e2e/projects-live.spec.ts` | Manual external-host duplicate; governed populated Projects tests retain flows and absorb its bilingual persistence assertion. |
| `apps/web/playwright.projects-live.config.ts` | No package/CI consumer; its manual preseeded-server setup is superseded by automated disposable Projects hosts. |
| `apps/web/scripts/capture-chat-readiness.mjs` | Unregistered ad hoc capture script; maintained Chat/browser suites generate screenshots and validate API/Core behavior. |
| `apps/web/scripts/capture-home.mjs` | Unregistered manual capture script; automated Home viewport/theme/accessibility matrix owns this coverage. |
| `apps/web/scripts/capture-live.mjs` | Unregistered external preconfigured-host capture script; disposable governed browser servers replace manual setup. |
| `apps/web/scripts/verify-live-chat.mjs` | Unregistered duplicate live-host Chat probe; maintained isolated Chat/conversation suites cover the application contract. |
| `apps/web/src/components/ui/tabs.tsx` | No import/dynamic consumer; Projects uses its own accessible navigation. Tabs-only dependency and CSS are removed together. |
| `apps/web/src/hooks/use-media-query.ts` | No import/dynamic consumer; responsive behavior uses maintained CSS and is exercised across five browser widths. |
| `docs/9router-gateway.md` | Verified transfer to `aryn-docs/engineering/aryn/9router-gateway.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/agent-factory-canvas.md` | Verified transfer to `aryn-docs/engineering/aryn/agent-factory-canvas.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/agent-factory-contracts.md` | Verified transfer to `aryn-docs/engineering/aryn/agent-factory-contracts.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/agent-factory-studio-shell.md` | Superseded shell implementation report; Factory canvas/contracts are retained in aryn-docs and regression tests. |
| `docs/bench-engine.md` | Verified transfer to `aryn-docs/engineering/aryn/bench-engine.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/bench-relay-brief-v1.md` | Verified transfer to `aryn-docs/engineering/aryn/bench-relay-brief.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/chat-conversation-management-validation.md` | Historical conversation QA report; conversation contracts and current positive/negative lifecycle tests remain. |
| `docs/chat-conversation-management.md` | Verified transfer to `aryn-docs/engineering/aryn/chat-conversation-management.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/chat-workspace.md` | Verified transfer to `aryn-docs/engineering/aryn/chat-workspace.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/ci-validation.md` | Superseded CI run narrative; CI contracts remain in source and successful baseline run is linked explicitly. |
| `docs/core-automations-contracts.md` | Verified transfer to `aryn-docs/engineering/aryn/core-automations-contracts.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/core-execution-hardening.md` | Verified transfer to `aryn-docs/engineering/aryn/core-execution-hardening.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/deployment-validation.md` | Historical authentication/deployment QA; product security contract and retained runtime verification preserve boundaries/blockers. |
| `docs/github-issue-connectivity.md` | Verified transfer to `aryn-docs/engineering/aryn/github-issue-connectivity.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/github-live-uat.md` | Verified transfer to `aryn-docs/engineering/aryn/github-live-uat.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/governance-history-integrity.md` | Verified transfer to `aryn-docs/engineering/aryn/governance-history-integrity.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/intelligence-recovery-contracts.md` | Verified transfer to `aryn-docs/engineering/aryn/intelligence-recovery-contracts.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/pre-batch2-residual-validation.md` | Obsolete residual-work inventory; current contracts and complete regression suites supersede its intermediate status. |
| `docs/projects-implementation-audit.md` | Duplicate project audit inventory; project-workspaces engineering reference and governed project regressions remain. |
| `docs/projects-implementation-report.md` | Verified transfer to `aryn-docs/engineering/aryn/project-workspaces.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/runs-automations-v1.md` | Verified transfer to `aryn-docs/engineering/aryn/runs-automations.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/runtime-consolidation-validation.md` | Verified transfer to `aryn-docs/engineering/aryn/runtime-consolidation-validation.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/runtime-control-plane.md` | Verified transfer to `aryn-docs/engineering/aryn/runtime-control-plane.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/secure-https-connectivity.md` | Verified transfer to `aryn-docs/engineering/aryn/secure-https-connectivity.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/studio-canvas-stabilization.md` | Historical canvas stabilization log; Factory canvas/contracts and browser regressions preserve behavior. |
| `docs/studio-files.md` | Stale source-file inventory; current application README and build/import graph describe maintained files. |
| `docs/studio-redesign-decisions.md` | Verified transfer to `aryn-docs/engineering/aryn/studio-architecture.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/studio-redesign-progress.md` | Chronological progress log; substantive architecture, requirements and interactions are transferred separately. |
| `docs/studio-redesign-traceability.md` | Verified transfer to `aryn-docs/engineering/aryn/studio-requirements.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/studio-redesign-ux.md` | Verified transfer to `aryn-docs/engineering/aryn/studio-interactions.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/studio-redesign-validation.md` | Historical redesign QA snapshot; maintained shell/Home browser matrix and frontend tests retain assertions. |
| `docs/studio-validation.md` | Historical Studio QA snapshot; current regression suites and retained security/runtime contracts preserve evidence. |
| `docs/system-governance-validation.md` | Historical governance QA narrative; Core contracts, signed-history regressions and all migrations remain. |
| `docs/uat-bench-model-validation.md` | Historical model/Bench QA narrative; dynamic gateway/Bench contracts and current provenance regressions remain. |
| `docs/workflow-builder-v1.md` | Verified transfer to `aryn-docs/engineering/aryn/workflow-builder.md`; source commit/blob and copy/destination hashes preserved. |
| `docs/workflow-execution-contracts.md` | Verified transfer to `aryn-docs/engineering/aryn/workflow-execution-contracts.md`; source commit/blob and copy/destination hashes preserved. |
| `modules/commercial/.gitkeep` | Empty, unregistered scaffold with no product/test/build consumer; actual Core modules and supported domains remain. |
| `modules/core/divisions/.gitkeep` | Empty, unregistered scaffold with no product/test/build consumer; actual Core modules and supported domains remain. |
| `modules/core/organizations/.gitkeep` | Empty, unregistered scaffold with no product/test/build consumer; actual Core modules and supported domains remain. |
| `modules/core/projects/.gitkeep` | Empty, unregistered scaffold with no product/test/build consumer; actual Core modules and supported domains remain. |
| `packages/ui/.gitkeep` | Empty, unregistered scaffold with no product/test/build consumer; actual Core modules and supported domains remain. |
| `services/worker/.gitkeep` | Empty, unregistered scaffold with no product/test/build consumer; actual Core modules and supported domains remain. |
| `tests/evaluation/.gitkeep` | Empty, unregistered scaffold with no product/test/build consumer; actual Core modules and supported domains remain. |

The destination repositories also remove `aryn-docs/engineering/.gitkeep` and `aryn-infra/deployment/cloud/.gitkeep` because their verified content now makes those placeholders redundant.
