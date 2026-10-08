# Governance history integrity dan evidence authority

Validasi 8 Oktober 2026, branch `development`, baseline audit
`4d5454ca607e833b01920aea69e864e40ad66b8c`. `main` tidak diubah, di-merge,
atau di-rebase. Dokumen ini menggantikan klaim eligibility legacy dan freshness
dalam laporan sebelumnya. Fondasi belum dibekukan untuk deployment hosted.

## Root cause

- **H1:** assignment memvalidasi chain yang masih tersedia dan membandingkannya
  dengan pointer. Baseline membandingkan pointer dengan generation terbesar yang
  masih tersedia. Menghapus suffix lalu mengembalikan pointer membuat chain lama
  konsisten lagi. Menghapus semua aktivasi dan mengganti `activation_origin`
  menjadi legacy membuka adoption. Signature membuktikan asal receipt, bukan
  bahwa receipt itu masih merupakan head terbaru.
- **H2:** absence receipt membuka fallback ke audit publication SHA-256. Tidak
  ada provenance independen untuk membedakan historical cohort dari publication
  baru yang receipt-nya dihapus. `published_at` tidak membuktikan usia publication.
- **M2:** SHA-256 audit tidak authenticated dan mengabaikan actor type, schema
  version serta causation. SQLite menghilangkan timezone pada DateTime, sehingga
  string yang dihitung sesudah persistence berbeda dari envelope awal.

## Perubahan authority pada jalur existing

Core memakai `EvidenceSigner` existing, repositories existing, dan transaction
boundary `DatabaseManager`. Tidak ada control plane, domain model pengganti,
approval baru, atau sync/layanan eksternal. Immutable AgentVersion, signed Bench,
human approval, blueprint/assignment locks, CAS, idempotency, scope tenant/project,
serta claim runtime sebelum dispatch dipertahankan.

`modules/core/history.py` menyimpan commitment di **file terpisah dari database
aplikasi**. Key tiap head mengikat kind, organization, project dan subject. Head
baseline/aktivasi mengikat ID, generation, dan hash seluruh signed receipt.
Publication receipt mempunyai commitment immutable sendiri. Lifecycle publication
menambahkan restriction monotonic untuk deprecation; mengembalikan status SQL ke
published tidak mengembalikan eligibility. Deprecation pada record unverified
hanya mencatat restriction, tidak mengesahkan publication historis.

Whole commitment document diautentikasi dengan HMAC dan namespace database;
kerusakan/penghapusan satu entry tidak diterima sebagai absence yang sah.
Signing key dan commitment berada di luar hak akses database writer. Koneksi
SQLite aplikasi memakai authorizer yang menolak ATTACH/VACUUM INTO dan SQL
file/extension functions, sehingga SQL injection tidak mewarisi filesystem access
authority process untuk membuka sidecar. Arbitrary host-side SQLite connections
tetap memerlukan ACL yang melindungi file authority. Sifat ini,
bukan checksum tambahan atau chain di database yang sama, memberikan freshness
pada threat boundary yang didukung. Replaying receipt bertanda tangan lama di
database tidak mengubah head independen.

Blueprint baru mendaftarkan baseline generation 0 **dalam transaksi penciptaannya**.
Initial assignment hanya dapat didaftarkan dari transaksi repository penciptaan
assignment. Existing rows tidak didaftarkan sebagai origin hanya karena dibaca.
Receipt lama tanpa commitment tetap unverified. Tidak ada migration backfill
signature atau synthetic approval/evaluation/comparison/publication/activation.

Jalur current baseline, registry known-good, assignment activation/rollback, dan
runtime claim memerlukan commitment yang sesuai. Chain yang valid secara lokal
tetapi terpotong, pointer usang, scope substitution, receipt yang hilang, atau head
yang tidak dapat dibuktikan memblokir tindakan yang memerlukan authority tersebut.
Republish idempotent juga memverifikasi receipt, sehingga bukan jalur bypass.
Publication metadata dicocokkan dengan signed receipt. Runtime yang sudah
memiliki claim menyimpan provenance versi saat claim; rollback tidak mengubah
in-flight run atau hasil historis.

## Commit dan kegagalan

1. Database transaction menulis receipt, pointer, dan audit atomik; perubahan
   commitment baru masih staged dan belum authoritative.
2. Sebelum database commit, independent store menyimpan intent durable setelah
   CAS terhadap seluruh head yang diamati.
3. Setelah ACK database commit, store memfinalisasi head dan menghapus intent.
   Baru sesudah ini operation dapat menghasilkan success kepada caller.

Independent store memakai SQLite transaksi `BEGIN IMMEDIATE` dan
`synchronous=FULL`; file tersebut bukan database aplikasi kedua untuk domain.
Prepare yang gagal membatalkan database transaction. Kegagalan sebelum prepare
tidak memajukan head. Rollback eksplisit membuang staging. Kegagalan/crash atau
ACK ambigu sesudah prepare meninggalkan **pending**, memblokir governance.
Tidak ada auto-recovery yang mempercayai row database untuk menghapus pending.
Database dan external store bukan transaksi distributed atomik: availability
dikorbankan untuk fail-closed pada celah commit, bukan klaim exactly-once recovery.
Pending bersifat store-wide, sehingga transient concurrency lintas blueprint
pada hosted deployment dapat ditolak dan perlu retry setelah commit selesai.

Recovery pending belum mempunyai tool otomatis. Operator harus menggunakan
evidence/backup independen yang diketahui terbaru, memeriksa transaksi dan scope,
serta memulihkan pasangan state konsisten. Jangan menghapus store/anchor, menerima
snapshot database sebagai authority, atau menandatangani ulang history lama.
Jika freshness tidak dapat dibuktikan, pertahankan read-only unverified state.

## SQLite Local dan PostgreSQL hosted

| Deployment | Enforcement dan boundary | Batas aktual |
|---|---|---|
| SQLite persistent | UPDATE/DELETE/REPLACE history ditolak oleh triggers, termasuk REPLACE konflik alternate unique identities. Koneksi aplikasi menolak ATTACH, VACUUM INTO dan SQL file/extension functions. Database-only corruption/restore yang melewati guards tetap terdeteksi melalui protected sidecar commitment dan key. Default file `<database>.aryn-history.sqlite3`, dengan `.initialized` anchor; missing file dengan anchor tidak dibuat ulang. | SQLite tidak mempunyai role privilege isolation. DDL/file owner dapat melewati triggers. Sidecar di direktori yang sama bukan perlindungan dari host/user yang menguasai file-file tersebut. |
| SQLite in-memory | Authority per engine, shared untuk manager pada engine yang sama; digunakan oleh tests/disposable sessions. | Tidak durable lintas restart; tidak diklaim sebagai deployment persistent. |
| PostgreSQL hosted | Migration-owner memasang UPDATE/DELETE dan TRUNCATE triggers. PUBLIC kehilangan mutation grants. Application writer harus non-owner, tanpa superuser/CREATEROLE/CREATEDB/replication/BYPASSRLS, schema CREATE, owner-role membership, dangerous server-file/program roles, atau UPDATE/DELETE/TRUNCATE/TRIGGER grants pada history. Pemeriksaan menolak writer yang tidak memenuhi syarat atau guards disabled. `ARYN_HISTORY_COMMITMENT_PATH` wajib menunjuk durable storage di authority host yang tidak dapat diakses SQL writer. | DDL dikompilasi offline; server/privileges/locking/multi-process PostgreSQL nyata belum diuji. Bukan production hosted PASS. |

Deployment hosted harus menggunakan migration account terpisah. Contoh policy
untuk role aplikasi yang diprovision oleh operator:

```sql
REVOKE UPDATE, DELETE, TRUNCATE, TRIGGER
ON agent_publications, assignment_transitions, bench_baselines,
   bench_comparisons, audit_events FROM aryn_runtime;
GRANT SELECT, INSERT
ON agent_publications, assignment_transitions, bench_baselines,
   bench_comparisons, audit_events TO aryn_runtime;
REVOKE CREATE ON SCHEMA public FROM aryn_runtime, PUBLIC;
```

Role/schema aktual harus disesuaikan deployment; kode tidak menciptakan role
otomatis. Operator juga harus menutup unsafe SECURITY DEFINER functions,
extensions, SQL-to-OS capabilities, dan akses jaringan/file di luar grant tabel.
Semua authority processes untuk database yang sama harus memakai **store yang
sama**, bukan sidecar per replica. Supported hosted profile saat ini memerlukan
satu authority host dengan protected local durable store; distributed replicas,
network filesystem locking dan distributed commitment service belum diverifikasi.
Filesystem ACL/volume ownership adalah prasyarat deployment, bukan sesuatu yang
terbukti dari unit test atau otomatis diamankan oleh mode `0600` di Windows.

Tidak ada klaim tahan terhadap compromised database superuser, host, governance
process, atau signing key; attacker yang dapat me-replay **database dan store/key
bersama** berada di luar boundary. Disk durability mengandalkan filesystem,
locking dan flush yang benar seperti [asumsi atomic commit SQLite](https://www.sqlite.org/atomiccommit.html).
Privilege dan trigger deployment mengikuti [PostgreSQL GRANT](https://www.postgresql.org/docs/current/sql-grant.html)
dan [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html).

## Audit baru dan compatibility

AuditLogger menghasilkan schema `2.0.0`. Envelope HMAC domain `audit_event`
mencakup event identity/type, schema, UTC timestamp dengan precision microseconds,
organization/project, actor type/ID, correlation, causation, resource, status,
dan sanitized payload. SHA-256 integrity reference tetap tersedia sebagai
diagnostic fingerprint. Repository memverifikasi signature sebelum menyimpan
envelope baru dan menormalisasi timestamp ke UTC **sebelum** SQLite persistence.
Reconstruction SQLite menginterpretasikan naive stored DateTime sebagai UTC;
PostgreSQL aware values dinormalisasi ke instant UTC yang sama. Row ID harus
cocok dengan event ID. Invalid timestamp tidak diganti dengan waktu sekarang.

`verify_authenticated_event` memerlukan HMAC; checksum legacy tidak memberikan
authority. Schema/attestation yang didowngrade ke weak format tetap unverified.
Snapshot menampilkan `authenticated` dan `integrity_limitation`. Audit v1 tetap
readable; checksum-only provenance dan timezone historis dapat tidak terverifikasi.
Weak historical audit tidak dipakai untuk publikasi/aktivasi baru. Autentikasi
envelope tidak dengan sendirinya membuktikan kelengkapan seluruh audit stream;
guards menolak deletion oleh ordinary SQL writer, dan tidak ada klaim audit
stream anti-truncation terhadap owner/superuser yang melewati DDL guards.

Migration **013_history_integrity**, revises `012_assignment_activation`, hanya
menambahkan audit attestation non-null dengan default kosong dan DB guards.
Schema metadata fresh memasang guards yang sama. Data/receipt existing tidak
diubah. Tidak ada reliable pre-receipt cohort proof dalam data lama; oleh karena
itu fallback publication legacy dihapus sepenuhnya. Legacy publication,
assignment, approval/evaluation dan run tetap dapat dibaca; registry menyatakan
`history_freshness_unverified`/`historical_access_read_only`, rollback eligibility
false. Untuk kembali mengoperasikan record yang tak dapat dibuktikan, gunakan
blueprint/version baru dengan Bench dan human review saat ini; jangan merekayasa
receipt historis atau menghapus commitment.

Downgrade 013 menghapus guards dan kolom attestation; downgrade 012 juga menghapus
publication/activation receipt seperti sebelumnya. Re-upgrade tidak merekonstruksi
signature/head yang hilang. Independent store tidak dihapus oleh migrations;
history yang berbeda setelah downgrade tetap fail-closed. Backup/recovery harus
mempertahankan database, signing key, store, anchor dan journal yang diperlukan
secara konsisten pada namespace/lokasi yang sama. Store di-ignore oleh Git.

## Bukti validasi

Hasil aktual setelah remediation:

| Pemeriksaan | Hasil |
|---|---|
| Dedicated negative + schema/activation migration suites | **47 passed**, 24 warnings; 100,41 detik. Termasuk 41 tests history/audit/file authority dan 6 migration compatibility tests. |
| Full backend `python -m pytest -q -rs --tb=short` | **621 passed, 5 skipped**, 32 warnings; 394,54 detik. Semua existing Bench, Factory, approval, regression, registry, rollback, security, migration dan runtime provenance suite disertakan. |
| Pemeriksaan terakhir flag current registry (positive + truncated baseline) | **4 passed**, 47 deselected, 2 warnings; 15,23 detik. Metadata fresh dan Alembic fresh sama-sama diuji. |
| Frontend `npm.cmd test` | **67 passed**, 12 files; 15,77 detik. |
| Frontend `npm.cmd run build` | TypeScript/Vite berhasil, 2.214 modules; existing chunk-size warning >500 kB. |
| Browser `npm.cmd run test:e2e` | **16 passed**, 0 skipped/flaky; 5,0 menit. Real HTTP/Core/SQLite, isolated runtime; includes registry rollback/provenance. |
| SQLite migration upgrade/downgrade/re-upgrade dan metadata parity | PASS dalam dedicated/full suites; downgrade tidak merekayasa receipt saat upgrade ulang. |
| PostgreSQL offline SQL | Upgrade chain ke 013 dan downgrade 013 → 012 berhasil dikompilasi; server hosted belum tersedia (Docker daemon tidak aktif). |
| Salinan database lokal existing | 009 → 013, seluruh count existing tetap: 9 blueprints, 13 versions, 19 evaluations, 4 approvals, 5 assignments, 8 runs, 84 audit events. Integrity OK, FK violations 0, fabricated/backfilled audit signatures 0. Database asli tidak dimodifikasi. |
| Focused Ruff E4/E7/E9/F dan `git diff --check` | PASS. Ini bukan klaim lint seluruh repository. |

Lima skip: tiga live model tests memerlukan owner-authorized opt-in; dua Hermes
health/capabilities tests tidak mempunyai `API_SERVER_KEY` dalam environment.
Warnings backend berasal dari Alembic path_separator dan Starlette/httpx
deprecations. Tidak ada live prompt/model submission dalam validasi ini.
Full run awal mempunyai satu kegagalan allowlist environment untuk path authority
baru; allowlist ditambah dengan nama eksplisit, tidak dengan wildcard atau
credential enumeration. Full run final di atas tidak mempunyai kegagalan.

Evidence lokal (di-ignore Git): `.local/governance-backend-complete.log`,
`.local/governance-dedicated-complete.log`, `.local/governance-registry-verified.log`,
`.local/governance-e2e-complete.log`, dan
`.local/evidence/governance-migration-validation.json`. File hasil tests tidak
mengandung key/token dan bukan pengganti authority commitment.

Negative tests: `tests/security/test_governance_history_integrity.py`. Tests
ordinary SQL guards terpisah dari storage attack helper yang secara eksplisit
melewati DDL guards untuk menguji commitment boundary. Assertions integrity,
CAS, idempotency, scope, regression dan runtime existing tetap dipertahankan.
Dua assertions lama yang mengesahkan history/receipt deletion sebagai legacy
diganti dengan denial dan read-only compatibility assertions; tidak ada PASS
legacy buatan. Allowlist environment menambah hanya path commitment eksplisit.

Covered attacks: latest/all activation deletion dan old pointer restore; latest
baseline deletion dan previous pointer restore; older signed receipt replay;
publication receipt deletion plus `published_at` tampering; publication metadata;
tenant/project substitution; audit actor/schema/causation/time/event/status/payload
tampering; canonical persistence/restart; missing/corrupt store/state/head; pending
intent; failed prepare dan failed finalize; deprecated publication resurrection;
weak audit compatibility, authenticated-to-weak audit downgrade, dan SQLite
ATTACH/VACUUM INTO/extension escape. Tests
memeriksa nol assigned runtime dispatch ketika authority gagal, dan blocked
approval/promotion pada baseline/commitment failure.

Residual: pending recovery membutuhkan operator/evidence independen; deployment
ACLs dan live PostgreSQL belum diverifikasi; no distributed authority validation;
no hostile host/superuser proof; complete audit-stream freshness di luar SQL
guards belum dibuktikan; live model inference/UAT tidak menjadi bukti suite
isolated. Publication baru tidak pernah berubah eligible lewat weak legacy audit.

Proteksi ini berfokus pada freshness signed governance history/evidence. Trusted
human identity/session, Core signing process dan policy enforcement tetap menjadi
prasyarat; ini bukan pembuktian integritas seluruh IAM/budget/configuration tables
terhadap arbitrary database corruption, maupun production authentication Studio.

## Files changed dan commit boundary

Commit dibuat lokal di `development`; SHA disertakan dalam laporan akhir chat.
Tidak ada push, merge, rebase atau perubahan `main`.

| Area | Files |
|---|---|
| Core authority/transaction | `modules/core/history.py`, `modules/core/audit/logger.py`, `database/connection.py` |
| Contracts/canonical time | `packages/contracts/core.py`, `packages/contracts/timestamps.py` |
| Persistence/schema/migration | `database/governance_protection.py`, `database/schema.py`, `database/migrations/versions/013_history_integrity.py` |
| Existing repositories | `database/repositories/agent_activation_repo.py`, `agent_repo.py`, `audit_repo.py`, `bench_regression_repo.py` |
| Existing lifecycle/API | `modules/agent_factory/service.py`, `services/api/studio.py` |
| Negative/storage tests | `tests/security/test_governance_history_integrity.py`, `tests/storage_attacks.py`, `tests/security/test_agent_rollback_authority.py`, `test_bench_baseline_authority.py`, `test_9router_boundary.py` |
| Compatibility/existing tests | `tests/integration/test_agent_registry_rollback.py`, `test_assignment_activation_migration.py`, `test_schema_migration_compatibility.py`, `tests/unit/test_agent_factory_and_bench.py` |
| Documentation | `docs/governance-history-integrity.md`, `docs/system-governance-validation.md`, `docs/agent-factory-contracts.md`, `docs/bench-engine.md`, `STATUS.md` |
| Local authority artifact exclusion | `.gitignore` |
