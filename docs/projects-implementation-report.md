# Projects ARYN — laporan implementasi lokal

Branch: `development`. Baseline: `e00056e59df05fb86fd780f21aac09ef34ca9e81`. Implementasi dan validasi diselesaikan pada working tree lokal sebelum pengguna mengizinkan commit, push ke `development`, dan pemantauan CI. Tidak ada merge atau perubahan pada `main`.

## Audit dan keputusan

Audit awal tersedia pada [projects-implementation-audit.md](D:/ARYN/aryn-labs/aryn/docs/projects-implementation-audit.md). Direktori referensi semula tidak ada. Delapan lampiran pengguna diperiksa; HTML dibuka di browser dan seluruh screenshot dibandingkan. Salinan referensi kini disimpan di `.local/projects-validation/design-references`, yang diabaikan Git dan tidak menjadi bagian dokumentasi source produk. Toolbar demonstrasi, data ilustrasi, dan App Shell prototype tidak diterapkan pada produk.

Fondasi yang dipakai kembali: App Shell, workspace selector, session authentication, CSRF/Origin, effective permissions, identity binder Core, audit bertanda tangan, TanStack Router/Query, tokens, i18n, dan jalur verification untuk assignment, run claim, workflow artifact, serta Bench. Tidak ada desain ulang Home, Chat atau App Shell.

Gap awal: halaman Projects masih scaffold; tidak ada API create/edit metadata proyek, tujuan proyek, generation, atau receipt idempotency. Core memiliki definisi workflow, run, assignment, division, membership, artifact dan audit yang bisa diproyeksikan. Backend belum mempunyai lifecycle archive yang aman atau registry hasil universal untuk semua format.

## Perubahan

- Frontend `apps/web/src/features/projects`: list ringkas, empty state berdasarkan izin, search/pagination, dialog Create/Edit, workspace detail dengan lima route, ringkasan adaptif, daftar pekerjaan/tim/hasil/aktivitas, serta drawer detail yang bisa dibagikan melalui URL dan dibuka kembali setelah refresh. Konten mengikuti proporsi reference, tokens existing, dan ID/EN. Focus, satu tab aktif, scope switching dan cancellation private query diperiksa.
- `WorkspaceProvider` memakai workspace context terbaru sesudah create dan membatalkan query proyek lama. Perubahan AppShell/AppSidebar hanya memperbaiki judul halaman serta indikator navigasi pada deep link Projects; tidak ada perubahan tampilan shell.
- Backend `modules/core/projects.py`, `packages/contracts/projects.py`, `services/api/projects.py`: create berotorisasi organisasi tanpa memerlukan project ID; update memerlukan project scope dan generation. Keduanya hanya untuk human organization admin, dengan validasi, recheck izin, CAS, idempotency receipt bertanda tangan, audit atomik, dan sanitized errors.
- `services/api/project_reads.py`: katalog read-only di atas data domain existing, dengan cursor bertanda tangan yang terikat user/org/project/filter. Chat turns privat, Bench execution internals dan input workflow artifact dikecualikan dari daftar pekerjaan/hasil. Assignment berbeda dari blueprint; status unknown tidak diubah menjadi berhasil/gagal.
- Migration additive `024_project_metadata`: `projects.description`, `projects.generation`, dan `project_mutations`. Receipt dilindungi dari perubahan/penghapusan/replace oleh ORM dan database; PostgreSQL juga menolak TRUNCATE. Downgrade yang membuang receipt berisi data ditolak.
- Tes API/Core/SQLite/PostgreSQL/OIDC, komponen dan browser ditambahkan. Assertions migration-head existing diperbarui karena revision bertambah; fixture migration Chat kembali merepresentasikan skema lama dengan benar. Tidak ada security assertion yang dihapus. CI mendapat satu langkah E2E Projects di samping gate existing.

## Kontrak API

| Method dan path | Perilaku |
| --- | --- |
| `GET /api/projects?q=&limit=&cursor=` | Daftar proyek yang dapat dibaca, pagination, dan effective `can_create` |
| `POST /api/projects` | `{name, description?, idempotency_key}`; respons 201 setelah Core menyimpan |
| `GET /api/projects/{id}` | Metadata, generation dan effective `can_edit` |
| `PATCH /api/projects/{id}` | Nama/tujuan + `expected_generation` dan `idempotency_key`; konflik 409 |
| `GET /api/projects/{id}/project-resources/{work|team|results|activity}` | Projection scoped, `q`, `format` hasil, `kind`, `active_only` pekerjaan, limit/cursor |
| `GET /api/projects/{id}/project-resources/detail/{kind}/{id}` | Detail, referensi asal, status dan preview teks yang didukung |

Nama 2–120 karakter satu baris, tujuan maksimum 2000 karakter, field authority tambahan ditolak. Identitas/org/project ditentukan server. Cursor palsu, filter tidak didukung/duplikat, permintaan lintas tenant, session/CSRF/Origin tidak sah dan edit stale ditolak. Create/Edit tidak mengubah budget, policy, tool grants, status agent, approval atau execution.

## Visual dan bukti nyata

Ukuran 1920/1440/1024/768/390px, dark/light diperiksa dengan screenshot browser. Konten dalam max-width 1376px termasuk padding desktop 32px, sehingga lebar isi maksimal 1312px. Heading 28px (25px mobile), row proyek 82px, resource sekitar 62–64px, tabs dengan satu underline aktif, drawer opsional dan layout mobile satu kolom mengikuti reference.

Penyimpangan yang ditemukan dan diperbaiki: screenshot tertangkap saat skeleton, kontras warning/success Light Mode, urutan heading, tab Ringkasan ikut aktif pada subroute, label peninjauan/penugasan yang belum diterjemahkan, section provenance kosong, posisi chevron, dan empty state terlalu rendah. Empty state kini memakai ukuran dan spacing prototype. Status/environment yang tidak ada pada kontrak sengaja tidak ditambahkan untuk meniru data contoh reference.

Validasi produk nyata memakai Studio dengan `testing=False`, configured Hermes adapter, API dan Core sebenarnya, serta SQLite persisten terpisah. Organisasi dimulai tanpa proyek. Proyek **Validasi Projects** dibuat melalui UI, diubah menjadi **Validasi Projects Tersimpan**, dan dibuka kembali setelah refresh. Riwayat create/update terverifikasi dapat dibuka melalui drawer. Tidak ada model inference atau mutasi pada database pengguna yang diperlukan untuk validasi ini.

Screenshot populated workspace/Hasil menggunakan **lingkungan pengujian terisolasi**: agent/version/assignment, Bench dan workflow artifact dibuat melalui Core dengan runtime double. Itu bukti wiring, governance, viewer dan rendering, bukan bukti keluaran model live pelanggan. Screenshot real Studio dibedakan dengan prefix `live-`; seluruh evidence akhir disimpan di `.local/projects-validation/screenshots`.

### Perbandingan dengan referensi

Toolbar `ARYN / DESIGN REFERENCE` dikeluarkan dari perbandingan posisi vertikal. Shell existing, judul/menu yang telah diterjemahkan dan data aktual memang berbeda dari ilustrasi; hierarchy, list, spacing, underline tab, drawer dan breakpoint mengikuti konten prototype.

| Referensi | Implementasi yang diperiksa | Kesimpulan |
| --- | --- | --- |
| Empty Desktop | Studio nyata, admin kosong, 1440 dark | Icon 74px, judul terpusat dan satu CTA. Min-height 540px/66dvh serta spacing dikoreksi agar sepadan tanpa toolbar demonstrasi |
| List Desktop | Studio nyata satu proyek dan test Core beberapa proyek | Baris 82px, search, tujuan dan tanggal nyata; status lifecycle/filter status contoh tidak ditampilkan karena kontrak belum memilikinya |
| Workspace Desktop | Populated Core test workspace, 1440/1920 dark | Decision/work di atas; assignment/results dua kolom. Semua section kosong disembunyikan; tujuan/status contoh tidak disalin |
| Hasil Desktop | Populated Core test results, 1440 dark/light | Search, filter format dinamis dan list kompak; warna Light Mode memenuhi pemeriksaan axe |
| Hasil Detail Desktop | Detail Website dari workflow artifact, 1440 dark | Drawer 610px opsional, metadata/provenance; viewer unavailable eksplisit, tanpa HTML embed palsu |
| Mobile | Populated Core test overview, 390 dark/light | Satu kolom, tabs muat pada container, row compact; drawer full-width, Escape/focus dan overflow diperiksa |

Contoh screenshot Studio nyata:

![Empty state Studio nyata](D:/ARYN/aryn-labs/aryn/.local/projects-validation/screenshots/live-empty-admin-1440-dark.png)

![Proyek nyata tersimpan setelah Create/Edit dan refresh](D:/ARYN/aryn-labs/aryn/.local/projects-validation/screenshots/live-list-1440-dark.png)

Contoh visual resource pada lingkungan pengujian Core terisolasi:

![Ringkasan populated di lingkungan pengujian](D:/ARYN/aryn-labs/aryn/.local/projects-validation/screenshots/populated-overview-1440-dark.png)

![Hasil Light Mode di lingkungan pengujian](D:/ARYN/aryn-labs/aryn/.local/projects-validation/screenshots/populated-results-1440-light.png)

![Drawer Hasil Desktop di lingkungan pengujian](D:/ARYN/aryn-labs/aryn/.local/projects-validation/screenshots/result-detail-desktop-dark.png)

![Ringkasan Mobile di lingkungan pengujian](D:/ARYN/aryn-labs/aryn/.local/projects-validation/screenshots/populated-overview-390-dark.png)

Semua ukuran/tema dan lima tab tersedia pada direktori screenshot lokal yang sama. Salinan referensi ada di `.local/projects-validation/design-references/` untuk perbandingan lokal. Tidak ada snapshot populated yang dianggap bukti inference pelanggan.

## Hasil gate

Seluruh angka berikut berasal dari perintah yang dijalankan lokal pada Windows sebelum commit/push. Hasil CI GitHub untuk SHA yang dipush harus diperiksa terpisah dan tidak disimpulkan dari hasil lokal ini.

| Gate | Hasil aktual |
| --- | --- |
| Frontend formatting, lint, TypeScript dan production build | Lulus; pemeriksaan TypeScript juga dilakukan oleh build |
| Frontend unit/component | 88 lulus pada 11 file, termasuk 8 kasus Projects; diulang setelah koreksi visual/terjemahan terakhir |
| Backend offline lengkap, empat partisi CI Windows | 949 lulus, 5 skip eksplisit, 0 gagal/error dari 954 kasus |
| Projects API/Core/SQLite + OIDC/security | 23 lulus; juga tercakup dalam backend offline lengkap |
| PostgreSQL 16.13 nyata, role non-owner | 113 lulus pada suite lengkap; 2 kasus Projects lulus sesudah penambahan kasus katalog. Total 114 kasus unik karena satu kasus diulang |
| Projects browser melalui API/Core | 12 lulus; create/edit, lima tab, refresh, switching, detail dan visual/accessibility. Matriks populated diulang setelah koreksi terakhir |
| Studio nyata, `testing=False` | 3 browser tests lulus: zero-project admin, zero-project viewer, persistence dan bilingual. Diulang setelah koreksi empty state |
| Chat regression browser | 29 lulus; runtime pengujian terisolasi, bukan klaim inference live |
| Home/App Shell regression browser | 89 kasus lulus dalam suite awal; satu kasus navigasi memiliki heading ganda. Heading diperbaiki lalu kasus tersebut lulus pada rerun terarah |
| Ruff, repository hygiene, actionlint, lockfile dan diff whitespace | Lulus |
| Dependency audits | Python: 73 distributions tanpa advisory; npm: 0 vulnerabilities |
| Gitleaks | Riwayat Git dan snapshot source working tree diperiksa dengan redaction; tidak ada leak |

Lima skip bukan PASS: tiga tes model berbayar/live memerlukan opt-in; dua probe Hermes memerlukan `API_SERVER_KEY` yang tidak tersedia pada environment tes lokal. Tidak ada inference model yang diklaim dari validasi Projects. Gate offline/native-adapter menggunakan boundary pengujian yang tersedia dan tetap mempertahankan assertions confinement.

Data unit/component memakai fixture hanya dalam tes. Browser populated menjalankan API, Core, database, signed evidence dan workflow domain sungguhan dalam lingkungan terisolasi dengan runtime double. Studio `testing=False` menggunakan adapter terkonfigurasi tanpa mengirim inference. Create/Edit UI nyata telah diperiksa terpisah, termasuk sebelum organisasi memiliki proyek.

Negative cases mencakup non-admin, cross-user/org/project, CSRF, Origin, revocation, invalid controls, duplicate key dengan payload berbeda, replay identik, stale generation, concurrent edit, cursor/filter tampering, private Chat run exclusion, unverified evidence dan SQL append-only protections. Unknown execution outcomes dipertahankan.

Kegagalan awal fixture migrasi diperbaiki dengan merepresentasikan revision 022 secara akurat dan memperbarui expected head/tables untuk additive revision 024. Kegagalan accessibility/route diperbaiki pada heading, kontras dan focus/tab state. Security checks dan assertions tidak dilonggarkan.

Bukti XML lokal: `.local/projects-offline-{1..4}.xml`, `.local/projects-targeted.xml`, `.local/conversation-crud-postgresql-final.xml`, dan `.local/projects-postgresql-final.xml`. Dependency audit: `.local/projects-python-audit.json` dan `.local/projects-node-audit.json`.

## Batas kemampuan yang tetap jujur

- Tidak ada hard delete/archive. Semantik admission, retensi dan dampaknya pada run/evidence/audit belum tersedia; tidak ada cascade baru.
- Tidak ada status lifecycle proyek yang dikarang. `Local` hanya muncul saat context menyatakan mode development, bukan klaim model/provider lokal.
- Nama manusia dan division membership manusia belum tersedia. UI hanya menampilkan project membership nyata dan role; organization admin tidak otomatis dimasukkan sebagai anggota tim.
- Viewer hanya teks dari kontrak yang didukung. HTML/Website, evaluasi dan format lain memakai metadata/asal yang dapat diperiksa. CSP dan X-Frame-Options tidak dilonggarkan; tidak ada iframe, arbitrary embed atau storage baru.
- Output run adalah captured execution output; verification run menyatakan claim/provenance yang diverifikasi, bukan tanda tangan isi output atau persetujuan rilis. Workflow artifact diverifikasi terhadap history, digest dan byte; status review tetap berasal dari run yang sah. Hasil tidak otomatis dianggap approved deliverable.
- Relay existing menyediakan incident demo disposable; data itu tidak ditampilkan sebagai masalah pelanggan pada Projects. Fitur nyata Relay memerlukan kontrak non-demo yang sah.
- Agent Factory/Workflow Builder frontend masih scaffold. Tidak ditambahkan tombol pembuatan yang memberi kesan builder sudah bekerja, tidak ada builder kedua atau publish/execute otomatis.
- Native inference dan arbitrary dataset/media/code/external-change viewers bukan kemampuan baru yang diklaim oleh pekerjaan Projects ini.

## Daftar file working tree

Seluruh tes browser disatukan di `apps/web/e2e/`. Konfigurasi tetap memisahkan target server, sehingga tes live tidak masuk ke CI offline. Referensi desain tersimpan hanya di `.local/projects-validation/design-references/`, yang diabaikan Git. Daftar di bawah memuat file source yang berubah/baru; perpindahan Chat mempertahankan isi tes existing.

Validasi sesudah pemindahan: formatting, lint, typecheck (kini mencakup semua file tes browser), build, repository hygiene dan actionlint lulus. Discovery mempertahankan 134 kasus tanpa duplikasi: 90 Home/Shell, 29 Chat, 12 Projects dan 3 live. Tiga smoke E2E terarah lulus untuk keyboard search, Chat multi-turn/resume, serta Projects Create/Edit/lima tab/refresh/accessibility. Tes live tidak dikirim ulang dan tidak dihitung sebagai eksekusi baru pada perapian folder ini.

- `.github/workflows/quality.yml`
- `apps/web/e2e/chat.spec.ts`
- `apps/web/e2e/conversation-crud.spec.ts`
- `apps/web/e2e/projects-empty-live.spec.ts`
- `apps/web/e2e/projects-live.spec.ts`
- `apps/web/e2e/projects.spec.ts`
- `apps/web/package.json`
- `apps/web/playwright.chat.config.ts`
- `apps/web/playwright.config.ts`
- `apps/web/playwright.projects-live.config.ts`
- `apps/web/playwright.projects.config.ts`
- `apps/web/src/app/providers/WorkspaceProvider.tsx`
- `apps/web/src/app/router/index.tsx`
- `apps/web/src/app/shell/AppShell.tsx`
- `apps/web/src/app/shell/AppSidebar.tsx`
- `apps/web/src/features/projects/ProjectWorkspace.tsx`
- `apps/web/src/features/projects/ProjectsPage.tsx`
- `apps/web/src/features/projects/components/ProjectCollection.tsx`
- `apps/web/src/features/projects/components/ProjectDialog.tsx`
- `apps/web/src/features/projects/components/ProjectOverview.tsx`
- `apps/web/src/features/projects/components/ProjectQueryError.tsx`
- `apps/web/src/features/projects/components/ProjectResourceDrawer.tsx`
- `apps/web/src/features/projects/components/ResourceRows.tsx`
- `apps/web/src/features/projects/hooks/useProjects.ts`
- `apps/web/src/features/projects/lib/api.ts`
- `apps/web/src/features/projects/lib/presentation.ts`
- `apps/web/src/features/projects/projects.css`
- `apps/web/src/features/projects/tests/projects.test.tsx`
- `apps/web/src/i18n/index.ts`
- `apps/web/src/i18n/projects.ts`
- `database/migrations/versions/024_project_metadata.py`
- `database/project_protection.py`
- `database/schema.py`
- `docs/chat-workspace.md`
- `docs/projects-implementation-audit.md`
- `docs/projects-implementation-report.md`
- `modules/core/permissions/engine.py`
- `modules/core/projects.py`
- `packages/contracts/projects.py`
- `services/api/project_reads.py`
- `services/api/projects.py`
- `services/api/studio.py`
- `tests/integration/test_conversation_crud.py`
- `tests/integration/test_conversations.py`
- `tests/integration/test_projects_api.py`
- `tests/integration/test_schema_migration_compatibility.py`
- `tests/postgresql/test_agent_editor_persistence.py`
- `tests/postgresql/test_automation_persistence.py`
- `tests/postgresql/test_hosted_persistence.py`
- `tests/postgresql/test_intelligence_persistence.py`
- `tests/postgresql/test_projects_persistence.py`
- `tests/postgresql/test_workflow_persistence.py`
- `tests/postgresql/test_workspace_persistence.py`
- `tests/projects_browser_server.py`
- `tests/security/test_projects_authentication.py`
