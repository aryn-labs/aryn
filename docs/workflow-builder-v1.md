# ARYN Workflow Builder V1 — implementation and verification

Tanggal verifikasi: 12 Oktober 2026. Scope mengikuti lampiran “ARYN — WORKFLOW BUILDER V1” dari pengguna. Inferensi pengujian memakai runtime terisolasi yang diberi label eksplisit; API, Core, izin, lifecycle, database, checkpoint, artifact, dan review yang diuji adalah implementasi aplikasi sebenarnya.

## 1. HEAD awal dan akhir

- Repository: `D:\ARYN\aryn-labs\aryn`, working tree `development`.
- HEAD audit awal: `bb57f85c95a2030cfa5bbf8ccb4674138d60aae7`.
- HEAD akhir pengujian tetap SHA tersebut. Setelah verifikasi selesai, pengguna mengizinkan commit lokal pada `development`; commit yang memuat laporan ini adalah hasil implementasinya. Push belum diizinkan. Tidak ada merge, perubahan branch, atau perubahan `main`.
- Perubahan lokal sebelumnya tetap dipertahankan: pembeda availability model Agent Inspector dan pemindahan tes Agent ke `apps/web/src/test/`.
- CI [ARYN Quality 38218616092](https://github.com/aryn-labs/aryn/actions/runs/38218616092) adalah bukti historis untuk HEAD Agent Factory/Studio. CI tersebut **bukan** bukti perubahan Workflow dalam commit lokal ini.

## 2. Audit arsitektur existing

Fondasi Projects, Home, Agent Factory, serta dedicated Studio sudah tersedia pada HEAD. `/workflows` masih scaffold frontend. Backend Workflow sudah mempunyai kontrak graph, draft CAS, graph version immutable, executor berurutan, Core claim, signed checkpoint, artifact, keputusan manusia, dan recovery. Karena itu implementasi ini memakai domain tersebut, bukan membuat runner/tabel/layanan kedua.

Dependency yang diperiksa: `packages/contracts/workflow.py`, `modules/core/workflows/`, `services/api/workflows.py`, `services/api/studio.py`, schema/migration workflow, modul Agent Factory/activation/Bench/approvals, App Router, Studio primitives, Home, Projects, Agent canvas/registry/inspector, dan test existing. Dokumen acuan backend: [workflow-execution-contracts.md](workflow-execution-contracts.md).

Temuan yang memerlukan perbaikan kecil:

1. Kontrak draft sebelumnya mensyaratkan agent pinned dan graph executable; membuat workflow dari kosong tidak dapat menyimpan konfigurasi yang belum selesai.
2. Start HTTP menunggu seluruh eksekusi sehingga browser belum mendapat run ID saat inference berjalan.
3. Checkpoint belum mencatat edge terpilih. Menebak edge dari status node dapat salah ketika dua cabang kembali ke node yang sama.
4. Lifecycle inventory bukan indeks referensi Workflow yang lengkap. Batas pagination-nya 50 dan target lama dapat tidak tercakup halaman pertama.
5. Setelah API restart, ModelRouter dapat belum memiliki catalog. Workflow admission belum melakukan discovery seperti alur API lainnya.
6. Agent dan Condition membaca JSON text envelope. Website HTML tidak dapat menjadi input text handler tersebut.
7. Pencarian JSON name perlu cast khusus PostgreSQL, sedangkan SQLite perlu JSON type coercion tanpa CAST.

Tidak ada migrasi atau backfill signed history. Perubahan admission tetap menjaga pembacaan versi historis dan digest graph existing.

## 3. Shared versus domain-specific

| Lapisan | Implementasi |
| --- | --- |
| Shared Studio | Shell, header, navigation, floating library, Inspector, drawer/focus management, theme, session, locale |
| Shared canvas presentation | `StudioCanvas.tsx`, `canvas.css`, CanvasControls; React/SVG ports, curves, drag, pan/zoom, keyboard, fit, minimap |
| Agent adapter | `AgentCanvas.tsx`; registry, schema, configuration, policy ports, preview dan lifecycle Agent existing |
| Workflow adapter | Registry, typed graph/edges, workflow Inspector, pins, draft/version state, checkpoint traversal, review/artifact panels |
| Execution authority | Existing ARYN API → Core WorkflowExecutor → existing RunCoordinator/runtime |

Canvas Agent tidak diganti dengan node Dify. Lebar, port geometry, node skin, policy behavior, dan integration Agent dipertahankan. Routing Studio tetap terpisah dari Dashboard di bawah provider/session aplikasi yang sama. Workflow tidak memberi authority melalui port visual.

## 4. File yang dibuat/diubah

Frontend baru:

- `apps/web/src/app/studio/StudioCanvas.tsx`, `canvas.css`.
- `apps/web/src/features/workflows/api.ts`, `registry.ts`, `editor-state.ts`.
- `WorkflowCatalog.tsx`, `WorkflowEditor.tsx`, `WorkflowLibrary.tsx`, `WorkflowInspector.tsx`, `WorkflowRunPanel.tsx`, `workflows.css` dalam direktori feature Workflow yang sama.
- `apps/web/src/i18n/workflows.ts`.
- `apps/web/src/test/workflow-registry.test.ts`.
- `apps/web/e2e/workflows.spec.ts`, `playwright.workflows.config.ts`.

Frontend existing yang diubah:

- `apps/web/src/app/router/index.tsx`, `app/studio/StudioShell.tsx`.
- `apps/web/src/features/agents/AgentCanvas.tsx`, `agents.css` untuk adapter/shared presentation.
- `apps/web/src/features/projects/components/ProjectResourceDrawer.tsx` untuk tautan resource yang sah ke Workflow Studio.
- `apps/web/src/i18n/index.ts`, `apps/web/package.json`.
- Ekspektasi integrasi Home dalam `features/home/tests/HomePage.test.tsx` dan `e2e/home.spec.ts`; Home product UI tidak di-redesign.
- Perubahan lokal terdahulu tetap ada di AgentInspector/i18n agents dan tes Agent yang dipindahkan ke `src/test/`.

Backend/quality/docs:

- `packages/contracts/workflow.py`, `modules/core/workflows/graph.py`, `executor.py`.
- `services/api/workflows.py`, `services/api/studio.py`.
- `tests/integration/test_workflow_builder.py`, `tests/workflow_browser_server.py` baru.
- `tests/integration/test_studio_api.py`: helper fixture menerima role unik untuk dua assignment governed.
- `tests/postgresql/test_workflow_persistence.py`, `.github/workflows/quality.yml`.
- Dokumen ini dan pembaruan [workflow-execution-contracts.md](workflow-execution-contracts.md).

Tidak ada dependency frontend baru, perubahan lockfile, database produksi, atau file evidence besar yang ditambahkan ke Git.

## 5. Workflow Catalog

`/workflows` menggunakan scoped inventory Core, pagination, pencarian nama literal, filter proyek aktif/semua proyek yang dapat diakses, serta loading/empty/error states. Tidak ada template atau kartu data dummy.

Create meminta proyek tujuan secara eksplisit dan memeriksa permission backend. Kerangka Start → Agent → Human Review → End disimpan sebagai draft dengan Agent belum terkonfigurasi. Home starting brief membuka dialog create yang nyata; tujuan singkat digunakan sebagai nama awal karena domain belum mempunyai field description/default run input.

## 6. Workflow Studio

`/workflows/:projectId/:workflowId` membuka dedicated Studio. Header memuat nama, proyek pemilik, revision, manual save, validate, serta run. Mini-navigation membuka canvas, library, versions, Inspector, dan results. Sidebar/Top Bar Dashboard tidak ikut dirender.

Canvas memiliki dotted grid, curved typed connections, selection, drag node, drag dari library, pan/zoom, fit view, minimap, undo/redo lokal, keyboard node movement/delete/connect dan keyboard pan. Inspector desktop scroll independen; mobile memakai drawer dengan focus/Escape. Library floating mempunyai search dan kategori, kemudian kembali fokus ke canvas.

Draft disimpan manual. Node positions ikut draft; pan/zoom viewport hanya bertahan selama editor terbuka dan keterbatasan ini dijelaskan di UI. Unsaved navigation/beforeunload guard, conflict state, export draft lokal, dan reload server tidak menghapus input secara diam-diam. Nilai form tetap ada ketika panel disembunyikan.

## 7. Node Registry

Enam jenis sesuai Core; registry memuat type/label/icon/category, configuration schema, Inspector key, validasi, dynamic typed ports, capability/permission requirements dan checkpoint mapping.

| Node | Perilaku yang benar-benar didukung |
| --- | --- |
| Start | Membuat artifact input text melalui Core; tepat satu |
| Agent | Assignment aktif + AgentVersion published yang pinned; atau renderer deterministik `static-document-v1` untuk content → website |
| Condition | Predicate `contains`, `equals`, `nonempty`; port yes/no; satu cabang dipilih |
| Handoff | Meneruskan artifact terverifikasi tanpa transformasi/inferensi |
| Human Review | Satu keputusan manusia atas digest terminal artifact; tepat satu |
| End | Terminal setelah review diterima; dilewati jika review ditolak |

Schema ports: text, brief, content, website. Text/brief/content adalah JSON text envelopes, bukan klaim bahwa model telah menghasilkan citations atau structured fields lain. Website adalah HTML inert dari renderer Core. Agent/Condition tidak menerima input website; Handoff/Review/End dapat mempertahankannya. Tidak ada arbitrary code/tool/webhook/MCP node.

## 8. Kontrak API/Core

Existing routes dipakai untuk read/save/validate/freeze, versions, runs, stop, review, outputs, download, project resources, dan evidence Core.

Perubahan additive/minimal:

- `DraftNode`/`DraftGraph`: bounded incomplete design state; admission selalu reparses strict executable `Graph`.
- `GET /api/projects/:project/workflows?q=...`: literal scoped name search, query/pagination bounds tetap ditolak jika invalid/duplicate.
- `GET .../workflow-targets` dan `.../workflow-targets/:assignmentId`: scoped pagination dan eligibility memakai checker pin Core yang sama. Projection hanya identity/name/role/version/model/eligibility/permissions, tanpa prompt atau credentials.
- `POST .../workflows/:id/runs` dengan `Prefer: respond-async`: durable claim 202, lalu existing executor berjalan pada task API yang dilacak lifespan. Default synchronous tetap tersedia untuk caller existing. Recovery/ownership tetap Core; ini bukan durable worker baru.
- Runtime discovery/catalog diperbarui sebelum admission, lalu context/permission diperiksa kembali setelah await. Discovery invalid menolak dispatch.
- Signed run `traversed_edges`: hanya edge yang benar-benar dipilih. Checkpoint lama tanpa field tersebut dibaca konservatif tanpa mengarang traversal.
- `GET .../workflow-runs/:id/review`: verified immutable receipt existing.
- Admission `text_envelope_required` menolak HTML untuk text-only handlers tanpa mengubah parsing/history versi existing.

Authentication/session, org/project RBAC, CSRF/Origin, approval/Bench/activation evidence, signed protected heads, confinement, budgets dan immutable versions tetap menjadi authority backend. Workflow tidak mengedit prompt/model agent published dan tidak menambahkan tool grants.

## 9. Versioning dan execution behavior

Draft revision CAS dan freeze terpisah. Freeze menyimpan graph immutable/digest/pins; layout tetap milik draft. Run memuat snapshot versi persis yang diikat run, bukan graph draft terbaru. Reference lama dapat dibaca melalui lookup scoped meskipun tidak termasuk halaman target pertama. Target berganti/inactive/stale publication ditolak Core.

Eksekusi berurutan dan bounded: maksimum 24 node/32 edge/1–8 task, satu Start/Review/End, tanpa cycles/parallel fanout. Semua jalur harus melewati Review langsung sebelum End. Browser melakukan polling checkpoint aktual, menghentikan polling terminal/error, dan menampilkan pending/running/completed/waiting_review/skipped/failed/cancelled/outcome_unknown sesuai data Core.

Animasi aktif mengikuti status task dan `traversed_edges`. Node cabang yang dilewati tidak menyala. Dua cabang yang merge tidak menyebabkan edge tidak terpilih terlihat dijalankan. Poll interval/CSS motion tidak digunakan untuk mensimulasikan success/tool calls. ID Core run direkam sebelum inference oleh callback claim existing.

Request idempotency yang responsnya hilang dipertahankan dengan input/version/key persis dalam sessionStorage scoped user/org/project/workflow. Refresh menawarkan pengecekan/kirim ulang permintaan yang sama; tidak otomatis menjalankan inference baru. API/Core tetap memutuskan penerimaan. Cancel yang belum dapat dipastikan menghasilkan outcome unknown sesuai Core, bukan success sintetis.

## 10. Human review dan artifacts

Artifact manifest, lineage, schema, digest/size, model dan Core run ditampilkan jika tercatat. Payload diperiksa backend, lalu browser membandingkan SHA-256/length sebelum preview. Download menggunakan scoped endpoint. HTML memakai `iframe sandbox=""`, inert renderer dan CSP existing; iframe dipaksa light color scheme supaya text native tetap terbaca dalam tema gelap. Script/same-origin/network authority tidak ditambahkan.

Review meminta reason dan konfirmasi terhadap digest artifact yang sedang ditampilkan. Stale digest, conflicting decision replay dan scope/role invalid ditolak. Receipt accepted/rejected immutable dapat dibuka setelah refresh. Accepted menyelesaikan End; rejected melewati End. Review tidak men-deploy atau mem-publish website.

Model/version/Core run kosong pada artifact renderer deterministik berarti langkah tersebut tidak melakukan inferensi. Artifact sebelumnya dan task evidence tetap menyediakan provenance agent sebenarnya. Total tokens ditampilkan hanya jika measured pada scoped Core resource; biaya/durasi yang belum tersedia di projection tidak direka.

## 11. Screenshot dan bukti checkpoint

Semua evidence berasal dari Chromium rendered app + API/Core/database disposable, bukan gambar generatif. Direktori `.local/workflow-builder-evidence/` di-ignore. Hasil bukan data pengguna/provider produksi.

- [Catalog empty](../.local/workflow-builder-evidence/catalog-empty.png), [catalog populated](../.local/workflow-builder-evidence/catalog-desktop.png).
- [Desktop Studio](../.local/workflow-builder-evidence/studio-desktop.png), [node library](../.local/workflow-builder-evidence/node-library-all.png), [Condition Inspector](../.local/workflow-builder-evidence/condition-inspector.png).
- [Running](../.local/workflow-builder-evidence/execution-running.png), [waiting review](../.local/workflow-builder-evidence/waiting-review.png), [completed](../.local/workflow-builder-evidence/execution-completed.png).
- [Dua agent/cabang yes](../.local/workflow-builder-evidence/multi-agent-yes-html.png), [cabang no](../.local/workflow-builder-evidence/multi-agent-no-html.png), [HTML artifact](../.local/workflow-builder-evidence/artifact-html-yes.png).
- [Mobile canvas](../.local/workflow-builder-evidence/studio-390-dark.png), [mobile Inspector](../.local/workflow-builder-evidence/inspector-390-dark.png), [light desktop](../.local/workflow-builder-evidence/studio-1440-light.png), [English](../.local/workflow-builder-evidence/studio-english.png).
- [Safe checkpoint projection](../.local/workflow-builder-evidence/core-checkpoint-waiting.json): actual workflow/version/digest, tasks/Core IDs/artifact IDs dan traversed edges dari API. Projection ini tidak menyertakan credentials, execution owner atau request hash dan bukan pengganti signature evidence database.

Proporsi memakai Studio Agent existing: header tunggal, mini-sidebar, canvas dominan, Inspector 360px, library floating. Warna/radius/icons/node card memakai ARYN; bentuk Dify tidak disalin. Pemeriksaan screenshot mengungkap dan memperbaiki preview HTML putih-pada-putih. Manual aesthetic UAT final tetap ditunda sesuai scope pengguna.

## 12. Automated tests dan CI readiness

| Pemeriksaan | Hasil aktual / evidence |
| --- | --- |
| Frontend unit | 110 passed; `.local/workflow-unit-final.log` |
| Frontend build/typecheck | Lulus; `.local/workflow-build.log` |
| ESLint / Prettier | Lulus pada final product source |
| Workflow API/Core | 46 passed; `.local/workflow-core-final.log` |
| Security suite + model router | 387 passed; `.local/workflow-security-final.log` |
| Backend offline luas | 978 passed, 5 skipped, 120 deselected; `.local/workflow-backend-final.log` |
| Workflow browser | 14 passed; `.local/workflow-e2e-final.log`; termasuk Projects resource → exact run Studio |
| HTML visual regression | 2 passed; `.local/workflow-preview-visual-check.log`; kedua cabang, warna teks, screenshot heading dan preview |
| Agent browser | 14 passed; `.local/workflow-agent-regression.log` |
| Projects browser | 12 passed; `.local/workflow-project-regression.log` |
| Chat browser | 29 passed; `.local/workflow-chat-regression.log` |
| Home+Shell browser | 90 passed; `.local/workflow-shell-home-regression.log` |
| Ruff / actionlint / repository hygiene / diff whitespace | Lulus; pemeriksaan final tidak menemukan error |
| Scoped working-tree secret scan | Gitleaks: no leaks found, 40 source/document files; `.local/workflow-secret-scan.log` |
| PostgreSQL live | Tidak dijalankan; tidak ada test admin URL dan Docker daemon tidak tersedia. SQL dialect compilation bukan live PASS |
| Provider live | Tidak dijalankan; inference memakai isolated runtime, tidak ada paid/outbound inference |

Offline luas berjalan sebelum delta terakhir discovery cold-start, PostgreSQL search cast dan text-envelope admission. Delta tersebut ditutup oleh 46 focused Core tests serta security suite akhir; hasil 978 tidak diklaim sebagai full run atas byte source akhir. Deselected adalah suite PostgreSQL. Lima skips dikonfirmasi ulang melalui `.local/workflow-live-boundaries.log`: dua live Hermes health/capability tests tidak memiliki runtime API key, serta tiga live inference/lifecycle/smoke tests memerlukan explicit owner opt-in. Tidak ada provider request yang dikirim. PostgreSQL builder/search/async/review/admission tests sudah ditambahkan; 122 PostgreSQL tests berhasil dikoleksi tetapi belum dieksekusi lokal.

CI existing tetap mewajibkan backend Windows/Linux, frontend, PostgreSQL, security, native runtime, browser, Required Quality Gates dan Validated Delivery Artifact. Browser shard 2 kini juga menjalankan Agent Factory, shard 3 menjalankan Workflow; Chat/Projects tetap di shard 1. Tidak ada gate yang dihapus/diperlonggar. Perubahan belum didorong sehingga remote CI/current delivery artifact **belum tersedia** untuk implementasi ini.

Ringkasan lokal dan SHA-256 source working tree: [workflow-builder-verification.json](../.local/workflow-builder-verification.json). Manifest ini memudahkan pemeriksaan ulang file/log; bukan signed CI attestation. Sebanyak 159 browser cases unik lulus pada suite lengkap. Dua visual checks adalah pengulangan terarah setelah pemeriksaan screenshot, tidak dihitung sebagai fitur atau kasus unik tambahan.

Axe menguji halaman induk, dua tema/tiga viewport, keyboard/focus dan drawer. Opaque iframe tidak menerima injected axe script: subtree iframe dikecualikan dari axe traversal, lalu sandbox/title/main/h1/no script/form/link/resource diperiksa terpisah oleh Playwright. Ini adalah batas pengukuran yang disengaja, bukan perubahan sandbox agar tes lolos.

## 13. Regresi ditemukan dan diperbaiki

- Save sudah berhasil tetapi dirty state tetap menyala karena urutan properti API JSON/layout berbeda: pembanding lokal canonical mempertahankan node/edge array order, menormalkan key dan posisi, dengan unit regression.
- Arrow-key pan Agent mobile hilang saat ekstraksi canvas: behavior existing dipulihkan dan original browser regression dijalankan kembali.
- Membuka Inspector pada pointerdown menginterupsi touch drag: selection dilakukan pada click setelah gesture selesai.
- Label select implicit menyertakan teks option; label Inspector kini eksplisit. Input request yang dipulihkan juga mempunyai accessible label stabil.
- Light warning text gagal contrast: foreground mengikuti token teks, warning tetap pada border.
- Catalog kosong ModelRouter setelah restart menyebabkan run gagal: reproduction test terlebih dahulu, lalu refresh discovery sebelum admission.
- Website input pada text handler dapat menghasilkan input kosong: admission menolak, draft/historical parsing tetap tersedia.
- Fixture dua assignment berbenturan role: role unik melalui existing governed lifecycle; bukan bypass assignment checks.
- Locale test harus memakai preference API existing, bukan hanya localStorage.
- Axe recursive injection macet pada script-denied iframe: batas traversal di test harness diperbaiki sambil menjaga sandbox.
- Screenshot HTML kosong dalam dark mode: iframe light color scheme, tanpa mengubah artifact/CSP.
- Vitest gagal setup pada Temp sandbox Windows: TEMP/TMP diarahkan ke direktori task writable, lalu suite 110 berhasil; keamanan production tidak dilonggarkan.

## 14. Keterbatasan

Belum dinyatakan production-ready. Belum ada live PostgreSQL execution, provider end-to-end, multi-host load/availability proof, native runtime regression ulang lokal atau external penetration review untuk perubahan ini. Hosted deployment/IdP/TLS/ACL tetap memakai prerequisites existing.

Telemetry berupa signed task checkpoints yang dipoll, bukan token/tool SSE trace. Run mungkin selesai terlalu cepat untuk setiap state singkat terlihat di layar; UI tidak memperlambat/simulasikan state tersebut. Tidak ada retry otomatis, replay inference, general DAG parallelism, arbitrary code, external tools, templates, scheduler kedua atau deployment UI.

Graph description/default run input, viewport persistence, richer structured artifacts, general multi-review flows dan detailed duration/cost projection belum mempunyai kontrak UI lengkap. WorkflowV1 hanya menjalankan published AgentVersion dari assignment aktif yang memiliki evidence sah dan tool grants kosong. Unknown model readiness tidak disamarkan menjadi available.

Backend dan frontend baru harus dimuat sebagai pasangan. Jalankan ulang proses API existing yang tidak memakai reload setelah review perubahan; task ini tidak merestart/mematikan server produksi pengguna.

## 15. Kesiapan Runs dan Automations

Fondasi kini tersedia: immutable workflow versions, governed assignment pins, durable run/task/Core IDs, selected edges, artifacts, exact review receipts, scope/revision protection dan Studio UI bersama. Projects resource drawer dapat membuka Workflow Studio pada run yang persis; task Inspector menautkan scoped Core run melalui Projects resource detail.

Halaman global Runs/Automations belum dibangun ulang di pekerjaan ini. Tahap berikutnya dapat menyajikan inventory/filter/timeline/review queue existing dan menjalankan versi workflow melalui Core Automations existing. Diperlukan desain permission/error/recovery yang sama serta live PostgreSQL/provider validation. Tidak diperlukan execution authority atau scheduler baru.
