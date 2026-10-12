# Dedicated ARYN Agent Factory Studio Shell

12 Oktober 2026. Repository `D:\ARYN\aryn-labs\aryn`, branch `development`,
HEAD `2f4f845`. Pekerjaan ini memperluas Agent Factory yang sudah ada di working
tree. Perubahan lokal tersebut dipertahankan. Tidak ada commit, push, merge,
pergantian branch, perubahan `main`, atau penghapusan perubahan pengguna.

## 1. Audit implementasi terbaru

Audit dilakukan sebelum perubahan, mencakup router, AppProviders, WorkspaceProvider,
ShellProvider, AppShell, AgentEditor, AgentCanvas, NodeLibrary/registry,
AgentInspector, PreviewPanel, LifecyclePanel, kontrak frontend, stylesheet,
Working Copy/layout API, Core preview, dokumentasi dan tes existing.
Kedua screenshot terbaru dibuka dengan image viewer: tampilan ARYN existing
dan referensi Dify. ARYN tokens, artwork logo, Inter dan komponen UI menjadi
sumber desain. Tidak ada branding/node/warna Dify yang disalin.

Temuan utama:

- Seluruh route sebelumnya berada di bawah `AppShell`. Editor ikut menerima
  dashboard sidebar, Top Bar dan footer. Header editor, tab dan canvas topline
  menambah tinggi yang tidak diperlukan; library mengurangi lebar canvas.
- Canvas, tujuh definisi node, inspector, history graph, generation CAS,
  preview Core, Bench dan governed lifecycle sudah berfungsi dan digunakan kembali.
- Save masih manual. Layout privat per actor dan Working Copy mempunyai CAS
  terpisah; published version immutable. Shell tidak memerlukan endpoint,
  database, autentikasi, permission atau runtime baru.
- Guard sebelumnya hanya membandingkan draft valid/layout. Teks JSON invalid
  yang hanya tersimpan di form belum ikut melindungi navigation.
- Perbandingan viewport memakai `JSON.stringify`; urutan `zoom,x,y` dari zoom
  berbeda dari respons server `x,y,zoom`. Save berhasil tetapi label dapat
  tetap menyatakan perubahan belum disimpan. Kini nilai numeriknya dibandingkan.

Fondasi Home/Projects/Topbar ada pada HEAD yang sama dan tidak didesain ulang.
Integrasi katalog dan project context existing tetap dipakai.

## 2. Struktur layout dan komponen bersama

AppProviders tetap satu dan berada di atas router. RootLayout berisi Outlet,
shared GlobalSearch/ResourceDetailsDialog dan navigation focus yang bertahan
saat berpindah shell. Dua pathless layout routes:

| Layout route | Komponen | Halaman |
| --- | --- | --- |
| `dashboard` | `AppShell` | Home, Chat, Projects, katalog Agen dan halaman Dashboard lainnya |
| `studio` | `StudioShell` | `/agents/$projectId/$blueprintId` |

URL editor tidak berubah. Dashboard sidebar/Top Bar tidak dirender pada Studio;
tidak ada pemeriksaan nama halaman untuk menyembunyikannya melalui CSS.
Missing routes tetap mempunyai Dashboard recovery. Error/loading editor
mempunyai jalur kembali ke katalog.

Komponen di `apps/web/src/app/studio/`:

- `StudioShell`: route container, main landmark, skip link, document title/focus.
- `StudioWorkspace` dan `StudioNavigation`: satu header, rail ikon dengan tooltip,
  area kerja, notices dan theme toggle dari ShellProvider existing.
- `CanvasControls`: tampilan tambah, undo/redo, zoom dan fit. Implementasi graph,
  viewport/history dan port validation tetap di AgentCanvas.
- `StudioLibrary` dan `StudioLibrarySearch`: popover nonmodal berjangkar pada
  tombol, search/categories, Escape, outside pointer capture dan focus return.
  Nonmodal memungkinkan drag-and-drop ke canvas. Registry tetap milik Agent Factory.
- `StudioInspector`: panel kanan 360 px (330 px pada desktop kecil), scroll
  independen, close/reopen. Pada lebar <=900 px menjadi modal drawer dengan
  backdrop, background inert, focus trap dan Escape. Children selalu mounted
  sehingga local form text dan input pengujian tidak dibuang ketika ditutup.
- `useStudioDrawer`, `studio.css`, dan terjemahan `studio` Indonesia/English.

AgentEditor tetap memiliki draft, graph, source version, layout, concurrency,
validation, permissions dan execution state. Header menampilkan nama blueprint,
proyek pemilik, Working Copy, manual save state serta published version dari
lifecycle bila tersedia. Versi/evaluasi/publishing diakses melalui mini-navigation;
seluruh tindakan governed memakai LifecyclePanel existing.

## 3. File yang berubah dalam tahap Studio Shell

File baru:

- `apps/web/src/app/router/RootLayout.tsx`
- `apps/web/src/app/studio/StudioShell.tsx`
- `apps/web/src/app/studio/StudioWorkspace.tsx`
- `apps/web/src/app/studio/StudioLibrary.tsx`
- `apps/web/src/app/studio/StudioInspector.tsx`
- `apps/web/src/app/studio/CanvasControls.tsx`
- `apps/web/src/app/studio/useStudioDrawer.ts`
- `apps/web/src/app/studio/studio.css`
- `apps/web/src/i18n/studio.ts`
- Dokumen ini.

File existing yang disesuaikan:

- `apps/web/src/app/router/index.tsx`: pathless Dashboard/Studio layouts.
- `apps/web/src/app/shell/AppShell.tsx`: Outlet/children; overlays dipindah ke root.
- `apps/web/src/features/agents/AgentEditor.tsx`: komposisi Studio, verified
  project alignment, invalid form guard dan semantic viewport comparison.
- `apps/web/src/features/agents/AgentCanvas.tsx`: memakai shared controls;
  anchor tombol diteruskan ke library. Engine/node/edge logic dipertahankan.
- `apps/web/src/features/agents/NodeLibrary.tsx`: shared search/header UI.
- `apps/web/src/features/agents/agents.css`: hapus layout editor Dashboard yang
  sudah tidak digunakan; card node, edges, inspector form dan katalog dipertahankan.
- `apps/web/src/i18n/index.ts`: registrasi terjemahan Studio.
- `apps/web/src/test/shell.test.tsx`: deep-link layout/error/return regression.
- `apps/web/e2e/agents.spec.ts`: Studio, persistence, focus, ownership, screenshots.

Tidak ada perubahan backend/Core baru pada tahap ini. File backend yang sudah
dirty dari implementasi Canvas sebelumnya tetap dipertahankan.

## 4. Fungsi dan governance yang dipertahankan

Input, Agent, Output, Constraints, Tool policy, Budget dan Evaluation tetap berasal
dari registry existing. Tools/Knowledge/Memory tidak diaktifkan. Tidak ada template,
marketplace, grant dari koneksi, auto-publish atau runtime simulator baru.

Node geometry, typed ports, SVG curves, pan, zoom, minimap, pointer drag,
library drop, delete, graph undo/redo dan dynamic inspector tetap menggunakan
implementasi existing. Save/refresh memulihkan graph, viewport dan konfigurasi.
Conflict mempertahankan local changes serta menawarkan export dan reload.
Keluar dari Studio memakai navigation/before-unload guard; membuang perubahan
memerlukan pilihan eksplisit pengguna. Save state tidak mengklaim autosave.

Owning project berasal dari blueprint/Working Copy backend, bukan dari selector.
Deep link baru menyelaraskan shared project selection setelah envelope organization,
project dan identity blueprint lolos pemeriksaan. Respons ownership yang salah
ditolak sebelum mengganti project context. Kembali ke katalog mempertahankan
proyek yang sudah diverifikasi.

PreviewPanel, consent, idempotency, model/budget policy, tool confinement,
signed audit projection dan lifecycle tetap melalui API/Core existing.
Input accepted, Agent dispatched dan terminal result berasal dari event Core;
policy nodes tidak dinyalakan sebagai langkah runtime. Menutup panel tidak
menghentikan polling atau mengganti node/koneksi. Published payload hash tetap
utuh setelah Working Copy baru disimpan.

## 5. Screenshot nyata dan execution evidence

Screenshot berikut berasal dari aplikasi yang dirender di Chromium, bukan
mockup gambar. Environment memakai API/Core dan SQLite nyata dengan inference
**IsolatedTestRuntime** berlabel `test/model-a`; bukan run provider produksi
atau output pengguna.

![Desktop Studio](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/studio-desktop.png)

![Mobile Studio](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/studio-mobile.png)

Evidence tambahan:

- [Mobile inspector](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/studio-mobile-inspector.png)
- [Desktop floating library](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/studio-floating-library.png)
- [Mobile library](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/studio-mobile-library.png)
- [Light mode](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/canvas-1440-light.png)
- [English](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/canvas-english.png)
- [Core dispatched](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/canvas-core-dispatched.png)
- [Core completed](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/canvas-core-completed.png)
- [Lifecycle](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/canvas-lifecycle.png)
- [Verified Core events](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/core-events.json)
- [DOM layout metrics](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/studio-layout-metrics.json)

Persisted event sequence `input.accepted → agent.dispatched → run.completed`
berasal dari `core_audit`, dengan sequence 1/2/3, actual model `test/model-a`,
terminal status `completed` dan `execution_claim_verified: true`. Browser test
menahan isolated runtime sesudah actual Core dispatch, memeriksa Agent/Input edge
running serta policy/Output idle, lalu melepas runtime dan memeriksa completion.
Ini membuktikan wiring actual Core events, bukan inferensi provider live.

## 6. Perbandingan layout sebelum/sesudah

Pada layar 1600 × 1000, DOM canvas Studio dengan inspector terbuka berukuran
1184 × 907,1 px, header 68 px dan rail 56 px. Library floating tidak mengubah
bounding box canvas. Inspector ditutup memberi tambahan lebar canvas.
Screenshot ARYN sebelum pada lampiran mempunyai sidebar Dashboard 240 px,
Top Bar, header/tab/topline dan library kiri; canvas tampak sekitar 766 × 658 px.
Ukuran sebelum merupakan pembacaan screenshot referensi, bukan pengukuran DOM.

| Aspek | Sebelum | Sesudah |
| --- | --- | --- |
| Navigasi | Dashboard sidebar + Top Bar | Rail Studio 56 px; 48 px mobile |
| Header | Breadcrumb, judul, tabs, canvas topline | Satu header 68 px |
| Library | Panel kiri mengurangi canvas | Popover dekat tombol, overlay mobile |
| Inspector mobile | Bagian di bawah canvas | Drawer dengan scroll/focus sendiri |
| Canvas | Mengikuti tinggi workspace Dashboard | Mengisi sisa viewport Studio |
| Node/eksekusi | Komponen ARYN dan Core existing | Komponen/authority yang sama |

[Screenshot sebelum dari lampiran pengguna](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/before-dashboard-reference.png).
Perbandingan dengan Dify dilakukan pada struktur ruang editor, panel dan mekanisme
library. Card, typography, icons, semantic colors dan execution authority tetap ARYN.

## 7. Hasil pengujian

| Command | Hasil aktual |
| --- | --- |
| `npm run build` | TypeScript dan Vite berhasil; final build 7,74 detik |
| `npm run lint` | Berhasil, max warnings 0 |
| `npm run format:check` | Semua file frontend sesuai Prettier |
| `npm test -- --maxWorkers=2` | 95 passed, 12 files; final run 27,56 detik |
| `npm run test:agents:e2e` | 14 passed; final run 51,2 detik |
| `npm run test:chat:e2e` | 29 passed; final run 3,4 menit |
| `npm run test:e2e` | 90 passed; Home/Dashboard final run 1,8 menit |
| `npm run test:projects:e2e` | 12 passed; full regression 3,8 menit |
| Focused Projects setelah shared navigation focus refactor | 2 passed; mobile keyboard dan deep link/project selector, 11,2 detik |
| Python API/Core/security subset di bawah | 68 passed, 44,18 detik |
| `git -c core.safecrlf=false diff --check` | Bersih |
| Live PostgreSQL / live provider inference | Tidak dijalankan; tidak diklaim PASS |

Python command: `.venv\Scripts\python.exe -m pytest -q --tb=short`
untuk `tests/integration/test_agent_canvas.py`,
`tests/security/test_agent_security_and_governance.py`,
`test_rbac_authorization_boundary.py`, `test_tenant_isolation_ownership.py`,
`test_projects_authentication.py` dan `test_workspace_authentication.py`.

Focused Projects command: `npx playwright test --config playwright.projects.config.ts
--output test-results/projects-studio-final -g 'project deep link|Projects 390px dark'`.
Ringkasan machine-readable: [verification.json](D:/ARYN/aryn-labs/aryn/.local/studio-shell-evidence/verification.json).

Browser coverage: scratch creation, valid/invalid typed ports, pointer drag,
library drag/drop/delete, undo/redo, viewport pan/zoom, configuration, save/refresh,
Working Copy/layout conflicts dua sesi, actual Core event order, policy nodes idle,
candidate/Bench/baseline/hash approval/publication/assignment, immutable published
hash, project filtering/switching, deep links, Dashboard return/focus,
rejected mismatched blueprint ownership, invalid local JSON navigation guard,
explicit leave, retained inspector fields, floating library search/Escape/outside
click, mobile focus trap, Indonesia/English dan dark/light pada 1440/768/390.
Axe tidak menemukan pelanggaran pada state yang diuji, termasuk drawer terbuka.

Initial verification menemukan role drawer yang salah, assertion serialisasi JSON
yang terlalu ketat dan viewport dirty comparison yang bergantung urutan properti;
semuanya diperbaiki. ESLint juga menangkap kebutuhan memisahkan hook dan RootLayout
ke modul tersendiri. Satu batch yang menjalankan beberapa browser suites dan unit
secara bersamaan mengalami timeout saat menunggu create/save/preferensi locale
(Agents 2, Chat 1, unit 3). Rerun final dengan beban lebih rendah lulus seluruhnya,
tanpa menaikkan timeout atau melemahkan assertion produk.

TEMP/TMP pengujian diarahkan ke `.local/tmp`. Browser dan Python signing tests
memakai approved elevated execution untuk batas filesystem/process Windows;
database tetap disposable. Tidak ada inference live atau database produksi.

## 8. Gap dan kesiapan Workflow Builder

- Granular tool-call/token telemetry, waiting-review execution, direct cancel dan
  replay player tetap mengikuti batas backend existing; shell tidak mengarangnya.
- Live inference ke provider, hosted IdP/production environment dan live PostgreSQL
  tidak diuji dalam tahap frontend ini. Automated browser menggunakan isolated inference.
- Save Working Copy dan layout tetap dua CAS existing, bukan transaksi atomik tunggal.
- Automated keyboard/axe/pointer/responsive diuji; physical touch device dan
  screen-reader manual belum termasuk validasi ini.
- Vite tetap memberi warning chunk aplikasi >500 kB dan annotation dependency Zod.
- Shell/panel/library/controls sudah dapat dipakai bersama. Workflow Builder belum
  diimplementasikan. Agent graph/registry/schema/runtime tetap domain-specific;
  Workflow memerlukan adapter, typed port rules dan kontrak orkestrasi tersendiri
  sebelum menggunakan canvas engine. Tidak ada otoritas eksekusi baru.
