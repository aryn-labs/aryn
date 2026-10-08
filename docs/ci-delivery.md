# CI, PostgreSQL verification and delivery

CI runs on `development` pushes, pull requests targeting `development`/`main`, and
workflow dispatch. It does not merge, release, deploy or modify either branch.
`development` is the integration branch; promotion to stable `main` requires an
owner-reviewed PR. Actual validation evidence is in [CI validation](ci-validation.md).

## Reproducible quality gates

Python 3.12.12 (`.python-version`), uv 0.12.0 and `uv.lock` fix application, test,
lint, PostgreSQL driver and build dependencies with package hashes. The setuptools
build backend is exact-pinned; CI builds without resolving another build environment.
`uv lock --check --offline` rejects manifest/lock drift. Node 22.23.3 LTS
(`.node-version`) and `npm ci --ignore-scripts` use the committed npm lockfile.
The reviewed dependency set builds/tests successfully without lifecycle scripts.

| Stable check | Scope |
|---|---|
| Backend Quality (ubuntu-24.04) | Ruff and full offline backend suite |
| Backend Quality (windows-2025) | Same suite, including Windows launcher/OS ownership contracts |
| Frontend Quality | Prettier, unit/components, TypeScript and Vite |
| PostgreSQL Integration | Real PostgreSQL 16.13, role separation, migrations and concurrency |
| Security and Configuration | actionlint, source hygiene, full Git secret scan, dependency audit and inventory verification |
| Native Hermes Boundary | Exact native source/dependency lock, actual HTTP route dispatch, network-denied SDK doubles and dependency audit |
| Browser E2E (1/3), (2/3), (3/3) | Chromium, one worker per shard, fresh API/Core/database/authority per test |
| Required Quality Gates | Requires every preceding check to succeed; failures, cancellation and skipped jobs cannot pass |
| Validated Delivery Artifact | Push/dispatch only; builds and scans the review artifact after all required gates |

Every action uses a full immutable commit SHA. Workflow token permissions are
`contents: read`, checkout credentials are not persisted, and PR execution never
receives production secrets. There is no `pull_request_target`, privileged follow-on
workflow, write token, automatic dependency merge or deployment step.
SHA pinning follows [GitHub's secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use).

The backend suite includes all existing BN-06, AF-07, migrations 013–015, signed
history, immutable version, regression/approval/publication/rollback, budget/usage,
owner/fencing/recovery, captured provenance, OIDC/CSRF and runtime boundary assertions.
Live model tests remain opt-in and CI fixes the opt-in to `0`. Missing live runtime
credentials remain explicit skips. The dedicated native runtime check cannot skip
when its source/interpreter is configured; it does not submit paid inference.

## Lint and security policy

Repository-owned Ruff configuration gates `E4`, `E7`, `E9`, `F`, `B` across all Python
source, scripts and tests. Historical unused imports/duplicate imports, unused results,
single-line compounds and Bugbear findings were corrected without removing assertions.
Only two entry points exempt `E402`: `scripts/hermes-9router.py` and
`tests/hermes_gateway_check.py` must set the isolated native import path before imports.
There are no wildcard exclusions or blanket correctness ignores.

An earlier workstation-wide lint configuration produced 1,116 findings, including
modernization (`UP`), import ordering (`I`), unused unpacked variables (`RUF059`) and
other style/design rules. Those additional rules are **not** claimed clean and are
not this repository's current policy. Expand the policy through reviewed changes;
the current correctness gate has zero findings. Full frontend source/E2E/config
formatting is enforced; formatting does not redesign Studio or change its contracts.

Gitleaks 8.30.1 and actionlint 1.7.12 binaries are downloaded from official releases,
then checked against committed SHA-256 values before execution. Gitleaks scans all
fetched Git history with redacted findings. `.gitleaksignore` contains exactly two
reviewed historical fingerprints of synthetic test keys, not path/global exclusions.
Delivery files and extracted wheel are scanned separately with no artifact exception.

Python/Native Hermes audits block **any known vulnerability**, reject unverified
third-party packages and verify complete installed distribution inventories. First-party
editable `aryn`/`hermes-agent` may be identified as scanner skips; their source is
covered by tests/review. An empty or incomplete scanner result cannot pass. npm audits
report all severities and block high/critical findings. Low/moderate findings must be
documented/reviewed; current scans have none. Advisory-service failure also fails the
gate. These are point-in-time scans, not proof of absence of undiscovered vulnerabilities.

## PostgreSQL authority and transaction evidence

The disposable service image is digest-pinned. `ARYN_TEST_POSTGRES_ADMIN_URL` is only
for test provisioning and deliberate attacks; it is not the product database URL.
Tests create independent random databases, a migration owner, and a non-owner runtime
writer. Product operations use the writer, never the superuser. Explicitly selecting
`tests/postgresql` without a live PostgreSQL URL fails; SQLite fallback is prohibited.

The writer has CONNECT/USAGE and scoped application table permissions, but no schema
CREATE, owner membership, role/database creation, replication, bypass-RLS, server-file
access, history UPDATE/DELETE/TRUNCATE/TRIGGER or Alembic version mutation. The owner
alone runs DDL. Enabled PostgreSQL history triggers are verified, and even owner DML
is tested against populated protected tables. A compromised owner/superuser capable
of changing DDL remains outside the claimed persistence boundary.

Live tests cover fresh migration chain through `015_authentication_boundary`, full
empty downgrade/re-upgrade, populated 015↔014 roundtrip preserving signed history/run
evidence, visibility and NOWAIT row locking, atomic failed publication, concurrent
publication/idempotency, baseline CAS, rollback CAS/idempotency, reservation admission,
concurrent settlement, replayed assignment pointers, unavailable/corrupt commitments,
single authority advisory locking, stale owner fencing and unknown-outcome recovery.
Signed offline OIDC provider tests also run through actual PostgreSQL sessions,
membership revocation, cross-scope APIs, CSRF/logout, governance and captured run/SSE.

Two real PostgreSQL issues were reproduced and fixed:

- Completion read a run before locking the budget, allowing two workers to see
  `usage_settled=false`. Write transactions now refresh and `FOR UPDATE` the run
  before terminal/settlement decisions. SQLite retains `BEGIN IMMEDIATE`.
- Baseline acceptance locked membership before blueprint, while publication locked
  blueprint first. Approval/publication/assignment now acquire commit-time Core
  authorization locks before resource locks. A deterministic barrier regression
  verifies absence of the former deadlock and rejection of an approval made stale
  by a concurrent accepted baseline.

The independent commitment protocol remains unchanged: prepare durable intent,
application transaction commit, finalize commitment. Ambiguous/pending state fails
closed. CI stores are disposable and separate from the PostgreSQL container; SQL
writer restrictions are proven. CI **does not** prove VPS filesystem ACLs, backup
freshness, host compromise resistance or distributed worker safety. Single execution
authority remains mandatory. Install the hosted driver with `uv sync --frozen
--extra postgresql`; migrations must use the separate owner while the application
uses the restricted writer. No new database migration was necessary.

## Browser and native isolation

Playwright installs Chromium and OS dependencies. Fully-parallel sharding divides
individual cases even though there is one spec file; each shard has one worker.
The automatic test fixture starts a real Studio API/Core process with a new SQLite
database, signing key, independent commitments and owner lock for **each** test.
Its environment is whitelisted; runtime and provider calls use isolated doubles.
There is no product reset endpoint or inherited dataset. Existing security assertions
and 5-second visibility assertions were retained; timeout inflation/retries do not
mask failure. Server startup still has its original 30-second bound.

Failed browser runs retain test traces, screenshots and isolated server diagnostics
for 7 days. Backend/PostgreSQL/native JUnit and dependency reports also retain for 7
days. Artifacts contain synthetic test data only; do not reuse this fixture with
production credentials. The strategy removes prior-test growth from CI; it is not
a claim that large production snapshots have been performance-qualified.

Native Hermes source is `937f23db2d707cde1c87337fde3aafee514d117c` from
`NousResearch/hermes-agent`, with its own frozen dependency lock on Python 3.14.0.
CI verifies the **actual** application's route/middleware dispatch and listener,
including forbidden native routes with a valid internal key, not merely a separate
allowlist constant. SDK calls are HTTP doubles with outbound socket connections
denied; native jobs, cron, admin/session ingress, fallback and arbitrary tools remain
unavailable. Local installed Hermes uses managed dependency paths: auditing only its
base interpreter can miss that inventory and is not claimed a complete runtime scan.
The CI materialized environment must pass explicit inventory verification.

## Safe artifacts and repository settings

`aryn-delivery-<exact SHA>` contains a Python wheel (verified by importing its extracted
files, including implicit namespace packages), production Studio static build,
`pyproject.toml`, both locks, Alembic config, README and build metadata with file hashes,
Python version, workflow run/attempt and tested commit. CI rejects modified source or
SHA mismatch. Local dirty-source checks are labelled `source_modified=true` and are
not represented as a delivered clean commit. Explicit file allowlists exclude local
databases, keys, commitments, runtime credentials, logs and repository configuration.
These artifacts are review candidates, **not** production releases, SLSA attestations,
VPS installers or Windows installers. They retain 14 days; a successful job also
produces GitHub's artifact digest. `aryn-infra` will own actual deployment.

The repository owner should configure branch rules for `development` and `main`:
require PR review (at least one reviewer), dismiss stale approvals, require approval
after the most recent push, require `Required Quality Gates` and all platform/security
checks above, require conversations resolved, block force pushes/deletion and disallow
admin/direct-push bypass for stable `main`. Require checks from GitHub Actions, enable
up-to-date checks/merge queue only after validating the chosen workflow event contract.
Do not enable merge queue yet: `merge_group` is not configured in this workflow.
Stable `main` should only accept reviewed promotion PRs; this work does not change settings.

At initial audit, both branches had protection disabled. Source cannot enforce GitHub
Settings. Dependabot config targets `development` for weekly Actions, uv and npm PRs,
with three open PRs per ecosystem and no auto-merge. Dependabot configuration and
dispatch UI activation depend on the default branch containing the configuration;
the owner must land it through a controlled PR, not an agent change to `main`.
Target-branch version updates do not replace default-branch security updates; see
[Dependabot options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference).
Future release preparation must use manual approval in `aryn-infra`; there is no
production environment or deployment workflow in this repository.

## Local commands

```text
uv sync --frozen --extra dev
uv lock --check --offline
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev pytest -m "not postgresql" -q
uv run --frozen --extra dev pytest tests/postgresql -q
uv run --frozen --extra dev python scripts/install_quality_tools.py
uv run --frozen --extra dev python scripts/check_repository.py
uv run --frozen --extra dev pip-audit --skip-editable --format json --output .local/python-audit.json
uv run --frozen --extra dev python scripts/check_dependency_audit.py .local/python-audit.json
npm ci --ignore-scripts --prefix apps/web
npm test --prefix apps/web
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
npm run format:check --prefix apps/web
npm run test:e2e --prefix apps/web
uv run --frozen --extra dev python scripts/build_delivery.py
```

Use `.local/quality-tools/gitleaks[.exe] git . --redact --log-opts=--all` and
`.local/quality-tools/actionlint[.exe]` for platform-native tools. On Windows set
`ARYN_TEST_PYTHON` to the absolute verified environment interpreter for browser tests.
For a disposable local PostgreSQL service, use the workflow's pinned image with a
loopback-only port mapping and explicit provisioning URL. Never use a production DB
for these destructive fixture/migration tests. `build_delivery.py` requires fresh
ignored output/verification directories and never silently deletes an existing artifact.
