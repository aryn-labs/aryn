# Studio redesign delivery evidence

## Agent editing and manual operations delivery

Current audit source: `40df9d1f894b257df3a277c4623466d6d03541dc`, equal to origin/development with a clean tree. Dependency workflow [37837626257](https://github.com/aryn-labs/aryn/actions/runs/37837626257) completed-success, 14/14 jobs. Push permission was verified. AGENTS.md, STATUS.md, PRD v1.2, Prompt 02, these four redesign documents, API/contracts, existing positive/negative evidence and CI were reviewed before editing. Earlier workspace evidence below is historical, not CI evidence for this delivery. Normative PDFs remain absent according to aryn-docs/DOCUMENT_INDEX.md; supplied PRD/source references do not substitute for reading missing PDFs.

Current implementation source: `2ca9dca575a2cfcc95505547e4426fe95e7e97b4`, pushed normally to origin/development. [ARYN Quality 37882643080](https://github.com/aryn-labs/aryn/actions/runs/37882643080) is terminal **completed / success, 14/14 jobs PASS**; [exact workflow metadata](evidence/studio/agent-ci.json) includes every job and validated artifact. The evidence-only closure workflow is independently checked before the final report. No change to main, production deployment, paid inference, runtime tool grants or scheduler occurred.

### Implemented behavior and source

- Agent Registry is scoped, filtered and paginated. Agent Detail retains actual Core lifecycle controls and verified known-good rollback; a paginated version registry reaches older versions. Version Detail is immutable and shows canonical configuration, exact hash, actual receipt references and complete field comparison, with object-key order ignored. Source: `features/factory.tsx`, `features/version-detail.tsx`, `features/resource-browser.tsx`, `services/api/workspace_reads.py`.
- Agent Builder edits all eight semantic sections through React Flow nodes, typed inspector and a complete keyboard form. Server catalog supplies model availability. Save persists one scoped shared working copy; undo, discard, explicit reload/restore and generation conflict retain user input. Candidate creation is separate and delegates canonical format 3 to existing Factory/Core. Fixed connections represent definition relationships; no execution gesture exists. Published payloads remain immutable. Source: `features/agent-builder.tsx`, `lib/agent-editor-types.ts`, `contracts/agent_builder.py`, `modules/agent_factory/editor.py`.
- Layout positions/viewport persist separately per actor with independent generation. Layout has no prompt fields and cannot create a version or change a canonical hash. Draft/candidate writes revalidate Core permissions in the transaction and audit atomically. Tombstones advance generation on discard to reject stale writers. SQLite/real restricted-writer PostgreSQL tests cover persistence and concurrency.
- Bench retains actual scenario/grader/evidence verification, signed baseline comparisons, critical regression failure despite a good aggregate and exact-hash human approval. Its history is paginated; canonical evaluation detail and legacy links work. Approval queue displays exact hash/evaluation/scope and authenticated actor receipts; no read response grants authority. Governance uses paginated actor/resource/search filters and lazy sanitized audit detail. Source: `bench.tsx`, `approval-queue.tsx`, `governance-browser.tsx`, existing Core/Bench services unchanged.
- Operations now lists actual assignments, published versions and recent runs, with actual runtime readiness and Core budget/reservation. Its manual action opens Core execution for the exact assignment. `/runs` is paginated/filtered history, `/runs/new` starts a manual run, `/runs/:id` is captured Execution Console. Legacy `?hasil`/`?penugasan` links remain. Historical selection overrides unrelated mutable version/assignment selectors; unknown consumption, held reservation, unavailable cost and stop acknowledgement are distinct from confirmed cancellation. Direct turns do not manufacture node traces. Source: `operations.tsx`, `run-history.tsx`, `runs.tsx`, `studio.tsx`.
- Scoped cache keys, AbortSignal, mutation scope capture and permission checks continue to apply. 401/403 hide cached resources, missing detail returns a clear 404 without a false canvas/configuration, and unsaved editor changes guard navigation/project switching. Full snapshot is used only by Settings compatibility; canonical histories and selected lifecycle views use bounded reads.

### API and additive persistence

All paths below are under `/api/projects/:project`; actor, role and organization are resolved by existing Core identity.

| Endpoint | Typed behavior and bound |
|---|---|
| GET /blueprints/:id/working-copy | WorkingCopyView; generation 0 for absent draft; scoped authorized read |
| POST /blueprints/:id/working-copy | WorkingCopyInput; full AgentDraft, expected generation; field-path errors without echoing input; version:create |
| POST /blueprints/:id/working-copy/discard | GenerationInput; guarded tombstone, no immutable version deletion |
| POST /blueprints/:id/working-copy/versions | GenerationInput; fresh available-model discovery and reauthorization; atomic canonical candidate |
| GET/POST /blueprints/:id/editor-layout | LayoutView/LayoutInput; at most eight unique semantic positions, bounded coordinates and zoom, per-actor generation |
| GET /lifecycle | LifecycleProjection; limit 1–50, default 25; scoped blueprint/version/evaluation/assignment/run selection; only selected canonical configuration/run output loaded |
| GET /resources/approvals | Existing ResourcePage with authenticated actor/hash/evaluation metadata, no publication eligibility claim from inventory alone |
| GET /resources/{versions,assignments,evaluations} | Adds blueprint_id filter bound into existing scoped HMAC cursor |
| POST /runs/:id/stop | Strict empty StopInput; StopReceipt uses actual Core RunResult; cancellation_confirmed only for terminal cancelled |

Migration `017_agent_editor` follows `016_workspace_structure`, adding empty working-copy and actor-layout tables plus scoped indexes. It neither backfills nor alters signed historical evidence, memberships, grants or runtime routes. Both table counts are checked before any downgrade drop; populated drafts/layout refuse destructive downgrade. Latest-head assertions in migration/hosted/workspace PostgreSQL tests advance to 017 while retaining prior assertions. Candidate creation accepts an existing transaction in Factory so candidate and audit roll back together.

### Observed validation

| Command / scope | Observed result |
|---|---|
| uv lock --check --offline; python -m ruff check .; python scripts/check_repository.py | PASS; dependency locks/governance/CI configuration unchanged |
| python -m pytest -m 'not postgresql' -q --junitxml=.local/backend-editor.xml | 754 passed, 5 skipped, 37 PostgreSQL deselected; 651.22 seconds; before five additional editor negative/bounded-history/activation tests |
| python -m pytest tests/postgresql -q --junitxml=.local/postgresql-editor.xml | 37 passed; 93.67 seconds; disposable PostgreSQL 16.13 digest pinned; actual restricted writer, no SQLite fallback |
| python -m pytest tests/integration/test_agent_editor.py tests/integration/test_workspace_api.py -q | 43 passed, including all 20 editor tests, 59.26 seconds; activation-pointer tampering withholds verified manual action even when the version is known-good |
| python -m pytest tests/integration/test_core_execution_contract.py tests/integration/test_bench_regression_api.py tests/integration/test_agent_editor.py tests/integration/test_schema_migration_compatibility.py -q | 34 passed before the final activation-pointer test, 58.84 seconds |
| npm.cmd run format:check; npm.cmd run build; npm.cmd test | PASS; 92 tests / 16 files; bundle main 495.30 KB / 155.47 KB gzip after navigation blocking, features lazy loaded |
| npm.cmd run test:e2e (ARYN_TEST_PYTHON=.venv/Scripts/python.exe) | 27/27 PASS, 0 failure/flaky/skip, 5.6 minutes after JSON/navigation correction; Operations lifecycle and large navigation included |
| gitleaks git . --redact; actionlint | PASS on repository history/workflow; final source artifact scan is also required by existing CI |

Five full-backend skips retain the existing requirement for owner-authorized live model opt-in (three) or local Hermes API key (two). Two existing Authlib/FastAPI dependency deprecation warnings remain; no paid inference was used. Intermediate browser failures were corrected and rerun: responsive action wrapping, paginated audit status height and missing historical run assertions; those failed runs are not claimed PASS. A local browser invocation without ARYN_TEST_PYTHON failed fixture startup; the documented Windows invocation uses `.venv/Scripts/python.exe` and then passed.

Positive/negative evidence includes all nested draft fields save→reload→immutable candidate, layout/hash independence, published immutability, stale generation/tombstone, forbidden capabilities/fallback/unknown suite, viewer/revoked membership, cross-project scope/cursor, audit transaction rollback, safe validation errors and active version beyond the first history page. Existing full regressions retain critical Bench regression, tampered receipts, stale exact-hash approval, rollback consistency, actual model mismatch, unknown usage/cancellation/idempotency, JSON/SSE/cache parity and rollback-during-preflight captured provenance. No previous acceptance assertion was removed to make the new design pass.

### Visual, source and performance evidence

R02 filtered semantic tables, R03 typed React Flow sections and non-canvas alternative, R05 actual captured observability, R06 readiness/attention and R09 keyboard/focus/reflow/contrast are mapped in UX/traceability. Browser editor evidence checks 1440/768/390 in both themes, keyboard form completion, axe and page-level overflow. Existing polish checks cover lifecycle, Bench, history, Operations and governance in both themes, responsive inspector and reduced motion. Axe is automated evidence, not full WCAG certification. Final synthetic screenshots and browser performance attachments are preserved under `docs/evidence/studio`; no customer data or credentials are included.

The reproducible API benchmark now measures every relevant paged resource plus selected Agent Detail and captured Console. Dataset large retains 200 blueprints, 1,000 historical runs, 5,000 signed audits and 200 divisions, plus one actual golden lifecycle (four Bench scenarios, approval/publication/assignment/manual run); it does not fabricate signed captured claims for seeded histories. Initial modified-source, 10-sample Windows SQLite/TestClient P95: summary 55.56 ms, run page 12.46 ms, audit page 13.23 ms, version page 115.89 ms, Agent Detail 369.81 ms, captured Console 446.08 ms; concurrent backend checks affected these samples. Clean-source repetition and browser timings will be recorded separately. Development thresholds remain summary ≤2,000 ms and usable navigation ≤3,000 ms; these are not production SLA claims.

### Clean-source performance repetition

[API benchmark](evidence/studio/agent-api-performance.json) was repeated from clean source `2ca9dca575a2cfcc95505547e4426fe95e7e97b4` with source_modified=false and 20 samples for each endpoint/dataset, after local test suites finished. Environment and dataset definitions above are unchanged. This fixture stresses historical run/audit volume; it contains one actual published AgentVersion and is not a claim about thousands of published versions or production load.

| API P95 ms | Small | Large |
|---|---|---|
| Summary | 26.42 | 39.20 |
| Blueprint / version page | 9.66 / 119.06 | 7.62 / 131.22 |
| Assignment / evaluation page | 110.44 / 19.04 | 117.62 / 16.56 |
| Approval / audit / run page | 9.84 / 11.35 / 9.01 | 9.10 / 8.65 / 8.92 |
| Agent Detail / captured Console | 316.91 / 322.53 | 327.13 / 413.74 |
| Legacy full snapshot (Settings) | 582.78 | 4,114.04 |

[Latest browser attachments](evidence/studio/agent-browser-performance.json), captured after JSON/navigation correction before commit, show large workspace navigation P50/P95 214.16/363.32 ms and summary 54.75/68.42 ms. Factory/Governance/Runs/Approvals/Operations each had one additional navigation sample, 951.53–999.93 ms. All configured development thresholds passed. Sample variability is expected; these measurements do not imply provider performance, production SLA or a fixed speedup.

### Editor input preservation verification

Initial implementation `7bfab885dd65b23c0146e08acbae989764b33e2c` was pushed normally and [ARYN Quality 37881263892](https://github.com/aryn-labs/aryn/actions/runs/37881263892) completed-success, 14/14 jobs, including collection/coverage gates and validated delivery artifact build. Windows partitions collectively executed 764 cases: 758 passed and 6 explicit skips. Linux executed the same 764-case collection: 741 passed and 23 explicit skips. Linux additional skips require Windows PowerShell; the main backend jobs also lack the configured native Hermes interpreter, whose separate mandatory Native Hermes Boundary job passed. PostgreSQL, frontend and all three browser shards passed. This is exact implementation evidence, not the workspace dependency workflow.

Final review additionally corrected incomplete JSON input retention and navigation: drafts preserve unparsed text across semantic sections/form mode, include it in dirty state and explicit reload/restore, and reject save/candidate until valid. RouterProvider/useBlocker handles browser Back/Forward as well as in-app links; beforeunload and project guard remain. Scrollable sidebar navigation is keyboard-focusable. Two editor browser tests and all 92 frontend tests passed after this correction, including actual Back confirmation. The full local browser repeat also passed 27/27 (5.6 minutes); final corrective/closure workflows are verified separately before reporting completion. The earlier successful CI does not establish this later correction's result.

### Residuals and boundary

1. Normative PDFs are unavailable; document-specific conformance remains unverified. PRD/repository ST mapping and tested product behavior are recorded independently.
2. Settings retains the legacy full signed snapshot and its large-history cost. Agent/history/audit/Operations routes use bounded reads; layout/draft do not weaken integrity verification.
3. Direct-turn per-node trace, provider cost/entitlement and real provider hard caps remain unavailable unless supplied by actual evidence. Stop acknowledgement does not settle unknown consumption or prove cancellation.
4. IdP/TLS/VPS production UAT, paid provider integration, installer/commercial program remain external. Executable workflows/outputs, Brief, Relay and schedules remain subsequent scope; no enabled implementation is claimed here. Hosted production readiness remains BLOCKED.

### Verified delivery

Both implementation commits (`7bfab885dd65b23c0146e08acbae989764b33e2c` and corrective source `2ca9dca575a2cfcc95505547e4426fe95e7e97b4`) were normally pushed to development and independently received terminal 14/14 successful workflows. Source and origin/development equality were checked after each push; main remains `630cbc96d728a49a64247ad2b88978529a7cbbad`. Final source workflow checks full Linux/Windows collection and disjoint coverage, actual restricted PostgreSQL, all browser shards, frontend, security/configuration, mandatory Native Hermes and validated delivery artifact. No assertions or required checks were removed or ignored.

Final source CI test artifacts: Linux 741 passed / 23 skipped; Windows four partitions collectively 758 passed / 6 skipped, zero errors/failures across the same 764-case collection. Skip reasons retain live opt-in, absent local API key/native interpreter and Linux's missing Windows PowerShell; the dedicated native check passed. PostgreSQL 37, frontend 92 and browser 27 all passed. Local commands, earlier failure corrections and benchmark provenance above remain distinct from CI evidence.

Validated review artifact `aryn-delivery-2ca9dca575a2cfcc95505547e4426fe95e7e97b4`, ID `11595009726`, digest `sha256:74fcdcffc424742a3e90bec0acb876341282aefe560dd3ef3224b7c685489323`, was built/scanned by that successful workflow; it is not a production deployment. Metadata and all four redesign documents accompany synthetic visual/API/browser evidence. Test PostgreSQL container was stopped and removed after persistence checks. New file/code naming remains professional, without phase/MVP/stage labels.

**READY FOR PROMPT 03** for the tested Agent Factory/Bench/manual Operations scope. The evidence-only closure commit is also pushed and its exact workflow checked to terminal before the final user report; that report identifies the final remote HEAD and closure CI. Residuals above remain, and hosted production readiness stays BLOCKED.

## Historical workspace delivery evidence

Implementation source: `80bac7dfa59bd27a6ac1e7e5493f11285b625b2d`. Current source workflow: [ARYN Quality 37835952417](https://github.com/aryn-labs/aryn/actions/runs/37835952417); terminal outcome is recorded in delivery evidence. Subsequent evidence-only commits do not change this source.
Audit source: `3a8ddb69b855ea37d1a33721c6c57a02f14ad881`; local and origin/development equal, clean tree, push permission verified. Baseline ARYN Quality run [37791265032](https://github.com/aryn-labs/aryn/actions/runs/37791265032) completed-success. Baseline evidence is not evidence for the new implementation.

## Audit

Existing UI/backend: React Flow representation in components/canvas and agent-flow; navigation/data loading in studio.tsx; Workspace/Snapshot in lib/types.ts; API and signed snapshot in services/api/studio.py; Core identity/permissions/history/usage/workflows; Agent Factory/Bench contracts and PostgreSQL restricted-writer tests. Existing snapshot loads full histories and verifies all versions/assignments/runs on each polling refresh; STATUS.md records accumulated-data browser latency. Divisions have no model; assignment division_id is an optional historical field. Existing auth is explicit Local or hosted OIDC; browser cannot supply authority.

UI redesign: grouped shell, summary Overview and scoped Projects/Divisions. New backend/contracts: scoped read model, authenticated pagination, division domain with conflict handling and additive schema/index migration. External program: installer/Tauri, real Ollama/BYOK, entitlement/payment, IdP/TLS/VPS operations remain outside this delivery.

Normative PDFs listed by PRD are not present in this workspace. aryn-docs/DOCUMENT_INDEX.md marks them not uploaded. Official-ID mapping below derives from the supplied PRD and existing repository references; no unavailable PDF section is claimed read or satisfied. PRD v1.2 and Prompt 01 were read from the user-supplied Downloads directory and not altered.

## Hasil implementasi

Fondasi workspace diimplementasikan pada branch development. Source implementasi `80bac7dfa59bd27a6ac1e7e5493f11285b625b2d` telah dipush normal ke origin/development. ARYN Quality pada source ini terminal completed / SUCCESS, 14 dari 14 jobs PASS. Working tree bersih pada benchmark clean-source; remote development sama dengan source setelah push. Commit penutup memperbarui evidence saja; workflow commit penutup juga diperiksa sampai terminal sebelum laporan akhir.

- Shell memiliki lima kelompok navigasi PRD, breadcrumb, proyek aktif, sesi Local/Hosted, tema, status API/runtime/model yang berasal dari pemeriksaan aktual, dan navigasi mobile dengan pengelolaan fokus. Feature modules dimuat secara lazy; bundle utama turun dari sekitar 715 KB / 221 KB gzip menjadi 431 KB / 135 KB gzip.
- Overview membaca summary scoped, bukan snapshot penuh. Inventaris recorded dibedakan dari governance eligibility; candidate review dan item latest menjalankan verifikasi evidence. Attention membuka run bermasalah terbaru atau approval. Sumber, definisi, scope, refreshed_at dan zona waktu terlihat. Cost/entitlement yang belum terbukti tetap unavailable/unknown.
- Projects memiliki list berfilter, urutan, cursor dan detail. Division nyata dapat dibuat/diedit hanya oleh human organization admin melalui Core; CAS generation, transaksi/audit atomik dan conflict mempertahankan input. Tidak ada role/membership division baru atau perubahan assignment history.
- Pergantian proyek membatalkan reads, membuang cache scoped, menutup selection/dialog dan menggunakan mutation scope yang ditangkap. 401/403 menyembunyikan cache; error lain dapat memperlihatkan data terakhir dengan label stale. Local/Hosted identity tetap server-owned.
- Deep-link existing tetap tersedia, termasuk /runs?hasil=:id, dan /runs/:id ditambahkan. Route future mempunyai penjelasan Belum tersedia tanpa aksi fitur aktif. Builder baru, executable workflow, Brief/Relay dan Automation belum dikerjakan.

## API dan persistence

| Endpoint | Kontrak dan batas |
|---|---|
| GET /api/workspace/context | Identity/proyek efektif; maksimal 100 pilihan, tanpa menunggu runtime discovery |
| GET /api/workspace/status | Status runtime/model aktual; organization-bound, revalidation setelah await |
| GET /api/projects/:project/summary | Typed WorkspaceSummary, inventory SQL, evidence bounded, effective permissions, budget/usage |
| GET /api/projects/:project/resources/:resource | Typed ResourcePage; projects/divisions/blueprints/assignments/runs/versions/evaluations/audits; limit 1–100; newest/oldest; filter whitelist; cursor HMAC expiring dan terikat actor/scope/filter/sort |
| GET /api/projects/:project/resources/:resource/:id | Typed ResourceItem, scoped lookup; output run hanya untuk captured claim/provenance terverifikasi; audit payload disanitasi |
| POST /api/projects/:project/divisions[/:id] | DivisionInput / DivisionUpdate; create atau expected_generation edit; effective Core division:manage; audit di transaksi yang sama |

Legacy /workspace dan /snapshot tetap kompatibel. Migration `016_workspace_structure` sesudah 015 menambahkan tabel division kosong dan index read scoped. Upgrade/downgrade/re-upgrade kosong diuji; downgrade dengan division tersimpan ditolak sebelum data terhapus. Tidak ada signed-history/evidence backfill. Snapshot mempertahankan referensi ORM selama projection agar verifikasi tidak membaca ulang tiap row; test memastikan seluruh 200 audit tetap diverifikasi dengan satu audit SELECT.

## Pengujian lokal

| Command | Hasil yang diamati |
|---|---|
| uv sync --frozen --extra dev; uv lock --check --offline | PASS, lock tidak berubah |
| uv run --frozen --extra dev ruff check . | PASS |
| uv run --frozen --extra dev python scripts/check_repository.py | PASS |
| uv run --frozen --extra dev pytest -m 'not postgresql' -q | 739 passed, 5 skipped, 35 PostgreSQL deselected; tiga skip memerlukan live-model opt-in, dua skip memerlukan local Hermes API key; 577,79 detik; 2 existing dependency deprecation warnings |
| uv run --frozen --extra dev pytest tests/integration/test_workspace_api.py -q | 23 passed setelah koreksi deep-link attention |
| uv run --frozen --extra dev pytest tests/postgresql -q | 35 passed, 2 existing dependency deprecation warnings; PostgreSQL 16.13 pinned disposable, restricted writer generated per test |
| npm.cmd run format:check; npm.cmd run typecheck; npm.cmd test; npm.cmd run build | PASS; 90 tests pada 15 files |
| npm.cmd run test:e2e | 25 passed, 0 failed, 0 flaky; 5,5 menit; isolated HTTP API/DB/runtime tiap test |

Negative coverage meliputi anonymous/expired sessions, revoked membership pada commit, hosted issuer/session mappings, cross-tenant/project, forged actor/role/body, stale/concurrent generation, duplicate/unknown query, bounds/sort/filter/cursor tamper, literal wildcard, captured claim tamper dan withheld result. Existing golden lifecycle, Bench baseline/regression, known-good rollback, unknown outcomes, native/runtime confinement dan launcher contracts tetap termasuk suite regression. Koreksi assertion head migration 015→016 mengikuti additive schema, tanpa menghapus acceptance.

## Responsive, keyboard dan accessibility

Browser memeriksa Overview, Projects dan division detail pada 390/768/1440 px di dark/light, axe tanpa violations, keyboard skip/navigation/modal/Escape/focus return, reduced motion dan reflow tanpa page horizontal overflow. Pengujian tambahan membuktikan division survive reload/edit, conflict tetap menyimpan input, paging/filter, delayed project response, stale/403/offline/401 dan future deep-links. Axe adalah pemeriksaan otomatis, bukan klaim sertifikasi WCAG menyeluruh.

Screenshot baseline dan 18 screenshot hasil tersedia di [evidence Studio](evidence/studio/README.md), termasuk [desktop dark](evidence/studio/overview-1440-dark.png), [tablet light](evidence/studio/overview-768-light.png), [mobile light](evidence/studio/overview-390-light.png). Semuanya memakai fixture sintetis, tanpa production credential/log.

## Performance

Windows 11 build 26300, Python 3.12.12, SQLite disposable dan FastAPI TestClient; runtime/model isolated, tanpa inference berbayar. Dataset small: 20 blueprint, 50 historical runs, 200 audit signed, 10 division. Dataset large: 200 blueprint, 1.000 historical runs, 5.000 audit signed, 200 division; benchmark API menambahkan satu golden lifecycle nyata (4 Bench scenario, approval/publication/assignment/captured run). Historical runs tidak diberi captured evidence palsu. Tiap API metric mempunyai 20 samples; browser navigation 10 dan summary 20. Development thresholds: summary P95 ≤2.000 ms dan navigation sampai konten usable P95 ≤3.000 ms. Ini bukan production SLA.

| Dataset / transport | Summary P50 / P95 ms | Snapshot P50 / P95 ms | Project list P50 / P95 ms |
|---|---|---|---|
| Small, sebelum strong ORM references | 25,66 / 39,55 | 1.001,80 / 1.456,02 | 14,37 / 23,17 |
| Large, sebelum strong ORM references | 42,38 / 96,62 | 7.368,90 / 10.938,94 | 7,08 / 9,67 |
| Small, setelah optimasi | 44,37 / 53,59 | 822,00 / 1.127,81 | 15,00 / 19,11 |
| Large, setelah optimasi | 50,79 / 60,32 | 4.284,42 / 8.613,32 | 14,95 / 22,04 |
| Small, clean commit 80bac7d | 22,14 / 25,45 | 409,53 / 497,88 | 7,23 / 7,92 |
| Large, clean commit 80bac7d | 24,47 / 30,72 | 3.246,10 / 3.555,01 | 7,11 / 10,22 |

Browser large dataset: navigation P50 **238,10 ms**, P95 **440,30 ms**; real HTTP summary P50 **49,82 ms**, P95 **62,76 ms**. Kedua threshold PASS. [JSON browser](evidence/studio/browser-performance.json) dan [API sebelum](evidence/studio/workspace-performance.json)/[sesudah](evidence/studio/workspace-performance-optimized.json) mencatat provenance sebagai uncommitted implementation di atas SHA audit. Gates lain berjalan bersamaan; perbandingan sample ini tidak menjanjikan faktor percepatan tetap. [Benchmark clean commit](evidence/studio/workspace-performance-committed.json) mencatat source_sha 80bac7d dan source_modified=false; lokal bebas dari suite concurrent pada pengulangan ini. Benchmark dapat diulang dengan `uv run --frozen --extra dev python -m scripts.benchmark_workspace --samples 20 --output .local/workspace-performance.json`.

## Traceability dan sisa kendala

Seluruh 38 ST-ID dipetakan satu per satu pada [traceability](studio-redesign-traceability.md). Scope workspace memverifikasi ST-DATA-01–05, bagian API ST-BN-04/ST-OP-03, alias ST-OP-02, attention ST-OP-04 dan distinction ST-OP-01; remaining UI/domain acceptance memiliki owner 02–05. R01/R02/R06/R09 diterapkan pada [UX](studio-redesign-ux.md). Future contracts design-only tersedia di [decisions](studio-redesign-decisions.md).

1. Full signed legacy snapshot pada large dataset masih lambat. Overview/Projects tidak memakainya; halaman lifecycle existing tetap kompatibel. Migrasi halaman berikut ke bounded reads perlu dilanjutkan tanpa mengurangi evidence verification.
2. Normative PDFs belum tersedia. Pemetaan official IDs mengikuti PRD dan repo; owner perlu melampirkannya untuk audit dokumen spesifik.
3. Cursor berlaku sampai satu jam dan invalid setelah API process restart; refresh daftar menghasilkan cursor baru. Selector cepat menampilkan maksimal 100 proyek; daftar Projects tetap paginated.
4. Real IdP/TLS/VPS UAT, provider hard total/cost cap, managed money reservation, distributed scheduler/workers, payment/entitlement, installer dan production operations tetap program eksternal. Hosted production readiness tetap BLOCKED.

## GitHub Actions dan delivery

[ARYN Quality 37835952417](https://github.com/aryn-labs/aryn/actions/runs/37835952417) terminal **completed / success** pada source `80bac7dfa59bd27a6ac1e7e5493f11285b625b2d`: backend Linux dan empat partisi Windows, frontend, PostgreSQL, security/configuration, actual Native Hermes Boundary, tiga shard browser, Required Quality Gates dan Validated Delivery Artifact semuanya **14/14 PASS**. [JSON metadata terminal](evidence/studio/ci-implementation.json) mencatat SHA, timestamps dan setiap job; bukan klaim dari YAML atau CI baseline. Gate existing memverifikasi complete collection dan disjoint coverage semua partisi Windows.

Review artifact `aryn-delivery-80bac7dfa59bd27a6ac1e7e5493f11285b625b2d`, ID 11575758247, digest `sha256:2f7f6e8098c187a921989b79e0cfa7bd492c55b04eb1c332b7b0437a9b12c11b`, dihasilkan workflow yang sama. Artifact adalah build candidate dengan SHA/hash, bukan production release/deployment. Daftar perubahan source lengkap tersedia pada [commit implementasi](https://github.com/aryn-labs/aryn/commit/80bac7dfa59bd27a6ac1e7e5493f11285b625b2d).

File utama: `apps/web/src/studio.tsx`, `features/overview.tsx`, `features/projects.tsx`, `lib/api.ts`, `lib/workspace-types.ts`, `workspace.css`; `services/api/studio.py`, `services/api/workspace_reads.py`, `modules/core/workspace.py`, `modules/core/permissions/engine.py`, `packages/contracts/workspace.py`; `database/schema.py` dan migration 016; scoped API/security/migration/PostgreSQL/browser/component tests, deterministic dataset dan benchmark script. Empat dokumen redesign dan screenshot/performance evidence menyertai source. Penamaan baru tetap profesional, tanpa nama fase/MVP/stage.

Remote main diverifikasi tetap `630cbc96d728a49a64247ad2b88978529a7cbbad`. Tidak ada production deployment, paid inference, unrestricted tool grants atau native scheduler. Seluruh acceptance scope workspace selesai, dengan residual di atas dan future contracts tetap design-only.

**READY FOR PROMPT 02.** Hosted production readiness tetap BLOCKED; status tersebut tidak berubah oleh delivery workspace.
