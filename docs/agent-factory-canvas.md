# Agent Factory Canvas — audit dan implementasi

12 Oktober 2026. Working tree `development`, baseline HEAD `2f4f845`
(fondasi Home/Projects/Topbar). Tidak ada commit, push, merge, pergantian branch,
perubahan `main`, atau penghapusan perubahan pengguna.

## 1. Audit fondasi dan referensi

- Audit mencakup `modules/agent_factory`, kontrak agent/builder, Studio API,
  schema/repositories, Core coordinator/permissions/budget/audit, Bench, router,
  App Shell, Home dan Projects. Working tree bersih pada awal audit.
- Home/Projects/Topbar sudah tersedia di HEAD development. Sebelum implementasi,
  typecheck, 72 tes frontend terfokus serta 50 tes API/security fondasi lulus.
  Tidak ditemukan blocker fondasi yang memerlukan perubahan berlawanan.
- Working Copy mempunyai generation CAS; layout privat per actor. Candidate,
  immutable payload hash, Bench, baseline, approval, publication dan assignment
  mempunyai layanan dan persistence existing yang digunakan kembali.
- `AgentDraft` membatasi grants menjadi kosong, deny-by-default, tanpa network,
  file write, code execution atau fallback model. Pembatasan dipertahankan.
- Screenshot Dify dibuka melalui image viewer. Source HTML prototype dibaca
  lengkap; browser menolak pembukaan `file://` lampiran tersebut. Tidak ada
  klaim perbandingan pixel terhadap hasil render prototype. Screenshot Dify
  menjadi referensi mekanisme, source prototype referensi susunan/interaksi,
  semantic tokens/App Shell ARYN menjadi sumber desain. Timer simulasi prototype
  tidak digunakan di produk.

## 2. Arsitektur canvas dan registry

`AgentCatalog → AgentEditor → AgentCanvas / NodeLibrary / AgentInspector /
PreviewPanel / LifecyclePanel`. Canvas memakai React, pointer events dan SVG
di atas dotted grid, tanpa dependency engine baru. Satu komponen dasar node
menggunakan icon/port/summary dari registry dan warna semantic ARYN.

Registry menyimpan identity/type, label/icon/category, typed ports, configuration
schema, inspector mapping, validation, capability/permission requirements dan
event mapping. Graph hanya editor metadata untuk **satu** AgentDraft. Policy
node adalah tampilan konfigurasi, bukan langkah orkestrasi. Menghapus node atau
koneksinya tidak menghapus budget/tool policy dari kontrak agent.

Tersedia pointer drag, library drag-and-drop, seleksi, koneksi melengkung antarport
atau koneksi melalui klik/keyboard, validasi tipe/arah/duplikasi, penghapusan,
pan/zoom/fit, minimap, keyboard move/delete, dan undo/redo graph 50 langkah.
Undo/redo tidak memutar balik operasi Core atau publikasi. Save eksplisit;
konflik mempertahankan local edits dengan export JSON dan reload server.
Navigation/before-unload guard melindungi edits yang belum disimpan.

## 3. Komponen dan node nyata

| Node | Kontrak/kemampuan |
| --- | --- |
| Input | Teks pengujian; event penerimaan Core |
| Agent | Identity, role, objective, instructions, gateway model, model policy |
| Output | Text/Markdown/JSON output contract dan hasil Core |
| Constraints | Operational/disallowed rules, citation policy, execution time |
| Tool policy | Inspeksi confinement existing; grants tetap kosong |
| Budget | Token/cost/time/turn policy; eksekusi teks satu giliran |
| Evaluation | Suite/version/scenario/threshold Bench existing |

Tools, Knowledge dan Memory ditandai belum tersedia. Tidak ada handler palsu,
template library, template dummy atau grant dari port visual. Node singleton
sesuai bagian konfigurasi satu agent. Jenis baru memerlukan kontrak backend,
registry, inspector dan tests yang sesuai.

## 4. Kontrak API/Core dan persistence

- `packages/contracts/agent_builder.py`: tambahan `AgentCanvasGraph`, typed
  nodes/connections, optional `LayoutInput.graph`/`LayoutView.graph`,
  `AgentPreviewInput`, safe `AgentPreviewEvent`, `AgentPreviewView`.
- `GET /api/projects/{project}/factory/capabilities`: model yang ditemukan
  gateway, valid default draft bila model tersedia, serta tool boundary.
- `POST /api/projects/{project}/blueprints/{blueprint}/preview-runs`: consent
  eksplisit, generation Working Copy/layout, prompt dan idempotency key.
- `GET .../preview-runs/{run}`: scoped stored result dan allowlisted verified
  audit events. Raw response/execution evidence tidak diekspos oleh adapter.
- `modules/core/agent_preview.py` menangkap draft hash/generation dalam signed
  audit, memanggil claim/dispatch coordinator dan membaca ledger existing.
  Preview tidak membuat version, assignment atau publikasi.
- Coordinator menulis `factory.preview.dispatched` dalam transaksi setelah
  confinement/model/permission/deadline preflight, tepat sebelum runtime dispatch.
- Reuse `agent_working_copies`, `agent_editor_layouts`, `run_states`, `audit_events`,
  usage reservations, evidence signer dan lifecycle endpoints. Tidak ada layanan
  eksternal baru, tabel paralel, migration atau bypass governance.
- Working Copy dan layout adalah dua operasi CAS existing. Jika write kedua
  gagal, generation pertama yang berhasil dipertahankan di editor. Keduanya
  tidak diklaim sebagai transaksi atomik tunggal.

## 5. Desain dan integrasi

Reuse semantic tokens ARYN, Inter, App Shell, Project Selector dan dark/light.
Desktop mempunyai library kiri, canvas pusat dan inspector/test panel kanan;
tablet menggunakan library overlay; mobile menumpuk inspector di bawah canvas.
Bahasa Indonesia/English, visible focus, field labels dan reduced motion tersedia.

Katalog menampilkan blueprint nyata dari proyek yang diizinkan, dengan filter,
search dan pagination. Creation memilih proyek eksplisit dan menyimpan kerangka
`Input → Agent → Output`. Home guided Quick Action diterima sebagai brief.
Projects → Tim & Agen menautkan katalog; assignment drawer menautkan blueprint
canvas. Topbar sinkron dengan route. Project switching kembali ke katalog,
dengan navigation guard bila ada edits.

Lifecycle memakai kandidat, Bench, baseline acceptance, exact-hash approval,
publication dan assignment existing. Tindakan direview eksplisit; server otoritas
terakhir. Tidak ada auto-publish atau deployment runtime baru. Home/Projects
queries diinvalidasi setelah perubahan lifecycle.

## 6. Bukti animasi dan batas telemetry

Urutan tersedia: `factory.preview.accepted → factory.preview.dispatched →
core.run.completed/failed/outcome_unknown/cancelled`. View memproyeksikan
`input.accepted → agent.dispatched → run.*`, dengan signed audit ID, sequence
dan timestamp. Event tidak terverifikasi diabaikan; accepted reference yang
tidak terverifikasi membuat preview unavailable.

Highlight berasal dari verified claim dan event tersimpan. Output memerlukan
`run.completed`; policy nodes/edges selalu idle. Polling mengambil status aktual
tanpa membuat tahap dengan timer. Animasi CSS hanya berjalan selama state Core
aktif. Draft/graph yang berubah menyembunyikan highlight run lama; hasil generasi
lama diberi penanda. Restore membaca persisted run tanpa inferensi ulang.

Playwright memakai API/Core/SQLite nyata dan **inferensi test double berlabel**.
Test barrier menahan runtime setelah actual Core dispatch, memeriksa Agent/Input
edge aktif dan policy/Output idle, lalu melepas runtime dan memeriksa completion.
JSON evidence dan screenshot disimpan dari test. Ini bukti wiring event Core,
bukan bukti inferensi live ke provider.

Granular tool-call/token events, replay player, waiting-review execution dan
cancellation direct belum didukung. UI tidak mengarang tool success atau cancel.
Actual model, usage, elapsed time dan error ditampilkan bila tercatat; nilai
unavailable tidak diubah menjadi nol. Preview diagnostik tidak membuktikan
semantic instruction/output-contract compliance; Bench adalah gate terpisah.

## 7. Validasi aktual

Database disposable dan isolated runtime digunakan, tanpa submission live.

| Command (dari repository atau `apps/web`) | Hasil aktual |
| --- | --- |
| `python -m pytest -q --tb=short --ignore=tests/postgresql` | 963 passed, 5 skipped; 15m16s; API/Core/Bench/permissions/budget/security/migration regressions |
| `python -m pytest -q --tb=short tests/integration/test_agent_canvas.py` | 18 passed; final focused negative/timeout/forged evidence tests |
| `npm test` | 94 passed, 12 files |
| `npm run build` | TypeScript `tsc --noEmit` dan Vite berhasil |
| `npm run lint` | Berhasil, max warnings 0 |
| Prettier check seluruh file frontend berubah | Berhasil |
| `python -m ruff check modules services packages database tests` | All checks passed |
| `npm run test:agents:e2e` | 11 passed; actual API/Core/SQLite, isolated inference |
| `npx playwright test --config playwright.agents.config.ts --output test-results/agents-detail -g 'scratch,'` | 1 passed; tambahan screenshot output dan persisted event JSON |
| `npm run test:projects:e2e` | 12 passed; actual API/Core/SQLite |
| `npm run test:e2e` (final full rerun) | 90 passed; Home/Shell dengan API fixtures |
| `npm run test:chat:e2e` | 29 passed; actual API/Core/SQLite, isolated inference |
| `git -c core.safecrlf=false diff --check` | Bersih |
| Live PostgreSQL / live model dispatch | Tidak dijalankan; bukan PASS |

Kasus terverifikasi mencakup creation, registry search/category, valid/invalid
ports, keyboard/pointer drag, library drag-and-drop, remove/undo/redo,
save/refresh/restore, Working Copy dan layout conflict dua sesi, actual Core
dispatch/completion order, policy node tetap idle, idempotent retry, denied model,
runtime tool confinement, budget denial, consent/CSRF, actual timeout unknown,
failed/cancelled projection, forged audit rejection, scoped reads dan membership,
candidate/Bench/baseline/approval/publication/assignment, published hash tetap
utuh, project switching, English preference server, serta dark/light accessibility
pada 1440/768/390 tanpa horizontal overflow.

Initial failures diperbaiki tanpa melonggarkan authority: adapter `passed: 0/1`
Bench, explicit inspector field labels dan light-mode tab contrast. Tes scaffold
lama diselaraskan dengan Agent Catalog serta modal creation yang kini nyata.
Satu initial Home navigation mengalami `ERR_NETWORK_CHANGED`; final full rerun
90/90 lulus. Worker temp diarahkan ke `.local/tmp` karena Windows sandbox temp
tidak terbagi konsisten. Python signing/browser tests memakai approved elevated
execution untuk operasi filesystem/browser, seluruh DB tetap disposable.

Build masih memberi warning annotation dependency Zod dan chunk aplikasi
512.73 kB; build tetap berhasil. Deprecation warnings httpx/Authlib existing
tidak diperbaiki dalam scope ini. Lima skipped tests tidak diklaim sebagai PASS.

Screenshot nyata dan event JSON disalin ke `.local/agent-factory-evidence/`
(ignored local artifacts, tidak di-commit):

- [Canvas + Node Library](../.local/agent-factory-evidence/canvas-library-dark.png)
- [Actual Core dispatch](../.local/agent-factory-evidence/canvas-core-dispatched.png)
- [Completion + output](../.local/agent-factory-evidence/canvas-core-completed.png)
- [Lifecycle + assignment](../.local/agent-factory-evidence/canvas-lifecycle.png)
- [English](../.local/agent-factory-evidence/canvas-english.png)
- [Mobile light](../.local/agent-factory-evidence/canvas-390-light.png)
- [Desktop light](../.local/agent-factory-evidence/canvas-1440-light.png)
- [Persisted Core events](../.local/agent-factory-evidence/core-events.json)

Setiap screenshot menggunakan test runtime yang dinyatakan terisolasi. Model
`test/model-a` dan penggunaan token fixture tidak boleh dianggap hasil pengguna
atau bukti kualitas provider live. Stable event IDs/timestamps pada JSON berasal
dari audit Core yang diverifikasi saat dibaca API, bukan dari simulator frontend.

## 8. Gap

- Live PostgreSQL belum dijalankan: admin URL tidak dikonfigurasi, `psql`/`pg_ctl`
  tidak tersedia, Docker daemon tidak berjalan. Tidak ada SQLite fallback yang
  diklaim sebagai PostgreSQL. Locking PostgreSQL memerlukan live regression run.
- Inferensi model/provider live belum dijalankan pada delivery ini.
- Render browser lampiran HTML ditolak; source dibaca dan Dify screenshot dilihat.
  Perbandingan rendered prototype masih merupakan gap.
- Tool grants/Knowledge/Memory belum memiliki supported draft contract/handler.
- Preview direct satu giliran; belum ada token streaming, granular tool trace,
  cancel direct, graph execution workflow, deployment transport atau replay player.
- Undo/redo hanya graph. Form edits tidak masuk graph history. Autosave tidak
  diaktifkan; Save Draft eksplisit dan navigation protection tersedia.
- Model catalog live dapat berubah; creation memerlukan discovered model dan
  dispatch tetap dapat ditolak bila readiness/permission berubah.

## 9. Kesiapan Workflow Builder

Canvas interaction, visual node base, typed ports, registry pattern, inspector,
layout CAS dan verified-event projection dapat diekstrak sebagai shared primitives.
Factory graph tidak mengotorisasi workflow steps. Workflow Builder harus memakai
kontrak/handler workflow Core, multi-agent assignment identity, step evidence,
approval/budget/cancel boundaries sendiri. Tahap ini menyediakan fondasi UI dan
pola integrasi; bukan klaim Workflow Builder selesai.
