# Studio redesign delivery evidence

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
