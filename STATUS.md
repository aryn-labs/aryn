# Delivery status

**Governance foundation freeze: BLOCKED untuk hosted deployment.** Core execution hardening
melanjutkan baseline `5e9392c5f976b4725813dd98ccd8c6811472d9ae`; authoritative claim,
reservation/settlement, single process ownership dan unified result contract didokumentasikan
di [Core execution hardening](docs/core-execution-hardening.md). Provider hard total-token/cost
cap, Managed AI monetary reservation dan distributed workers belum terbukti. Disposable
live PostgreSQL contracts kini diuji; deployment PostgreSQL VPS tetap memerlukan UAT.
Historical PASS rows di bawah tetap evidence revision sebelumnya.

CI/CD melanjutkan baseline `58bde394`: reproducible uv/npm locks, pinned read-only
GitHub Actions, correctness Ruff, frontend formatting, Linux/Windows backend,
actual native Hermes boundary, disposable PostgreSQL restricted-role integration,
isolated browser E2E dan commit-bound review artifacts. PostgreSQL verification
menemukan dan memperbaiki concurrent settlement serta inverted governance lock order.
Tidak ada migration baru; chain tetap `015_authentication_boundary`. Hasil lokal dan
status Actions yang benar-benar diamati dicatat pada [CI validation](docs/ci-validation.md);
kontrak/gates/settings pada [CI delivery](docs/ci-delivery.md). Branch protection dan
production release/deploy tidak diubah. **Hosted production readiness tetap BLOCKED.**

Deployment Boundary Hardening melanjutkan `27c3f0e`: Local identity hanya pada mode development eksplisit, hosted OIDC issuer/subject mapping dan server sessions/CSRF masuk Core authority existing, dan dedicated Hermes application memakai minimal route allowlist. Migration `015_authentication_boundary` membuat auth tables kosong tanpa evidence/membership backfill. [Deployment security](docs/deployment-security.md) dan [validation](docs/deployment-validation.md) membedakan signed mocks/installed-runtime tests dari IdP/PostgreSQL/TLS/VPS/firewall UAT yang belum dijalankan. **Hosted production readiness tetap BLOCKED.**

**Governance history remediation:** Remediation history/evidence
di `development` melanjutkan baseline `4d5454ca607e833b01920aea69e864e40ad66b8c`.
Proof lama pada tabel adalah hasil pada revision sebelumnya, bukan bukti freshness lengkap.
Authority boundary, perubahan compatibility dan hasil terbaru dicatat dalam
[Governance history integrity](docs/governance-history-integrity.md). PostgreSQL live privileges,
locking, deployment ACLs dan disaster recovery belum terbukti; tidak ada klaim compromised host
atau database superuser resistance.

| Workstream | Status | Proof | Blocker |
|---|---|---|---|
| Deployment boundary H4/M6 | LOCAL / OFFLINE BOUNDARY VERIFIED; HOSTED READINESS BLOCKED | `docs/deployment-security.md`, `docs/deployment-validation.md`: explicit Local mode, hosted OIDC + PKCE issuer/subject mapping, expiring server sessions/CSRF and Core commit revalidation; migration 015 without seeded authority. Dedicated **190 passed**; final review **52 passed**; full backend **698 passed, 5 skipped**; frontend **86 passed**, TypeScript/Vite PASS; complete browser suite **17 passed** in three fresh-database groups. Actual installed Hermes confined application/listener and forbidden native routes tested with isolated model transport; focused Ruff/Prettier/whitespace PASS. | Real IdP, PostgreSQL locking/privileges, TLS/proxy, VPS/firewall/container and retention UAT unverified. Initial accumulated-dataset browser run **14 passed / 3 failed** from snapshot latency; isolated groups pass without relaxed assertions/timeouts. Runtime key grants permitted private text operations; no compromised-host or per-run cryptographic runtime fencing claim |
| Governance history integrity & evidence authority | LOCAL VERIFIED; HOSTED FREEZE BLOCKED | `docs/governance-history-integrity.md`: 8 October 2026; independent durable head/intent, SQLite file-access authorizer and UPDATE/DELETE/REPLACE guards, PostgreSQL restricted-role checks and mutation/TRUNCATE guards, fail-closed publication authority, authenticated canonical audit. Dedicated **47 passed**; full backend **621 passed, 5 skipped**; registry final check **4 passed**; frontend **67 passed**, build PASS; Playwright **16 passed**, 0 flaky. Migration upgrade/downgrade, offline PostgreSQL SQL and existing DB clone preserve evidence without backfill. | Live PostgreSQL/ACLs/distributed authority and pending recovery remain unverified; no compromised host/superuser or full audit-stream freshness claim |
| Core execution hardening H3/H5/M1/M3/M4/M5/L1/L2 | LOCAL VERIFIED WITH LIMITATIONS; HOSTED FREEZE BLOCKED | `docs/core-execution-hardening.md`: 108 dedicated passed; full backend **661 passed, 5 skipped**; frontend **83 passed**; TypeScript/Vite PASS; final serial Playwright **16 passed**. Migration 014, signed captured claims, existing-ledger reservation/idempotent actual settlement, process ownership/fencing, scoped audit, safe error/SSE, configured approval authority. SQLite process concurrency/crash and migration compatibility verified; PostgreSQL DDL offline only. | Input admission estimated and total tokens measured postflight; no hard provider total/cost guarantee or Managed AI money reservation. Unknown consumption needs evidence reconciliation. Live PostgreSQL/distributed recovery unverified. Snapshot latency under parallel test load remains a residual |
| GitHub security | NOT VERIFIED | — | Organization app access not yet available |
| Hermes adapter PoC | PASS | `tests/integration/`, `tests/security/` (Loopback 127.0.0.1, Bearer auth, tools confinement verified) | — |
| Core governance & persistence | PASS | `database/`, `modules/core/`, `tests/unit/test_persistence_repos.py`, `tests/security/test_core_persistence_security.py` (38/38 tests pass: tenant isolation, RBAC, state machine, idempotency, restart recovery, budget preflight, and DB audit scrubbing) | — |
| Agent Factory & Bench Foundation | PASS | `packages/contracts/`, `modules/agent_factory/`, `modules/bench/`, `modules/core/approvals/`, `tests/unit/test_agent_contracts.py`, `tests/security/test_version_payload_integrity.py`, `tests/unit/test_agent_factory_and_bench.py`, `tests/integration/test_agent_lifecycle_workflow.py`, `tests/security/test_agent_security_and_governance.py` (88/89 tests pass, 1 skipped: authoritative Bench suite binding, canonical integrity format enforcement, exact payload hash approval, publication, operational assignment, and live Hermes Research Agent execution) | — |
| Bench accepted baseline & regression gate (BN-06) | PASS | `docs/bench-engine.md`: 8 October 2026, dedicated baseline/regression/API/migration tests **97 passed**; full backend **523 passed, 5 skipped**; frontend **64 passed**; TypeScript/Vite build successful; Playwright **15 passed**; whitespace checks clean. Includes critical regression backend blocking, signed receipt/comparison revalidation, stale approval, tenant isolation, CAS/concurrent publication, atomic rollback, legacy evidence and Research Safety compatibility. | Live model/provider tests remain opt-in; PostgreSQL migration SQL compiled offline, live PostgreSQL concurrency not tested |
| Agent version registry & known-good assignment rollback (AF-07) | PASS | `docs/agent-factory-contracts.md`: 8 October 2026, dedicated registry/rollback/API/migration/security tests **57 passed**; migration compatibility **6 passed**; full backend **580 passed, 5 skipped**; frontend **67 passed**; TypeScript/Vite build successful; Playwright **16 passed, 0 flaky**; focused Ruff and whitespace checks clean. Includes signed publication/activation evidence, human authority, stale intent/CAS, idempotency, concurrent writers, audit atomicity, historical/in-flight run provenance, tampering rejection, assignment isolation, preserved Bench baseline and immutable version history. | Live model/provider tests remain opt-in; PostgreSQL DDL compiled offline, live PostgreSQL locking not tested; legacy evidence limitations are explicit |
| ARYN Studio local development slice | PASS | `docs/studio-validation.md`: 109 backend tests, 3 component tests, 6 browser tests; frontend build; real browser Bench 4/4, Core approval/publication/assignment, live Hermes run (1,400 tokens), persisted output and audit | Real hosted IdP/server UAT, Brief/Relay and structured direct-turn runtime trace remain unverified/unimplemented; detailed Hermes readiness is degraded due to disk usage |
| Gemini model integration | SPEC ONLY | `packages/model_adapters/providers/gemini.py`, `tests/unit/test_gemini_status_audit.py` (Model specification & payload builder verified; NOT live-integrated without live API key & network client) | `GEMINI_API_KEY` not configured; live inference requires live provider credentials and network adapter |
| Ollama local model PoC | NOT STARTED | — | — |
| Tauri packaging PoC | NOT STARTED | — | — |

Only mark **PASS** with reproducible test evidence, including failing/negative tests where applicable.

## CI/CD and PostgreSQL follow-up — 8 October 2026

The historical rows above describe their original revisions. Live disposable PostgreSQL
16.13 verification now passes **33 tests**, including restricted writer privileges,
concurrent publication/baseline/rollback, exact-once settlement, actual advisory locking,
stale owner fencing, authenticated sessions and migrations through 015. Two real
concurrency defects were fixed: run settlement row locking and Factory membership/resource
lock order. No schema migration or historical evidence rewrite was introduced.

Final local source validation: **712 backend passed / 5 live opt-in skipped**, **86 frontend
passed**, **17 isolated browser E2E passed**, TypeScript/Vite, configured Ruff, Prettier,
dependency/secret scans and review artifact generation PASS. GitHub-hosted execution and
clean exact-commit delivery are **UNVERIFIED until actual workflow completion**. See
[CI delivery contracts](docs/ci-delivery.md) and [actual validation evidence](docs/ci-validation.md).
Real IdP, VPS TLS/proxy/runtime networking, production PostgreSQL operations and durable
commitment storage ACL/backup verification remain blocked; this is not production readiness.
