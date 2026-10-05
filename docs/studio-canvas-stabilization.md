# Audit dan stabilisasi canvas ARYN Studio

Tanggal: 6 Oktober 2026. Branch: `development`.
HEAD awal diverifikasi: `c8861c5072807fb778aea0debd50dda7aa34a324`; checkout bersih sebelum pekerjaan.

Pekerjaan melanjutkan Studio dan React Flow yang sudah tersedia. Identitas navy/graphite, violet, blue/cyan, Geist/Geist Mono, navigasi dan lifecycle dipertahankan. API produksi, Core, governance, contracts, schema/migrasi, runtime adapter, dan konfigurasi Hermes tidak berubah. Brief/Relay tetap placeholder; Batch 2 tidak dimulai.

## Temuan, akar masalah, dan hasil

| Area | Akar masalah | Perbaikan | Status |
| --- | --- | --- | --- |
| Ringkasan/proyek | Project ID dibandingkan dengan organization ID, lalu fallback ke proyek pertama; readiness Hermes dipakai sebagai klaim audit 100%. | Nama konteks memakai project aktif. HUD menampilkan blueprint, run, jejak Core dari snapshot proyek, versi dengan integritas valid, serta readiness aktual. Tidak ada persentase audit buatan. | PASS |
| Run historis | Canvas memakai versi dari pilihan form baru. | Lookup `run.session_id → assignment.id → version.id`, dengan kecocokan blueprint. Assignment nonaktif tetap dapat menjelaskan histori. Tidak ada fallback ke versi form atau run lain ketika histori tidak ditemukan. | PASS |
| Request pending | State mutation global dijadikan running untuk node histori. | State lokal request eksekusi baru ditampilkan melalui status agregat Core/Hermes. Histori tetap utuh; hasil baru dipilih setelah respons Core dan refresh snapshot. | PASS |
| Semantics canvas | Semua mode mewarisi affordance drag/connect. | Execution/Bench hanya baca; drag, connect, reconnect dan delete dimatikan. Pan, zoom, selection/keyboard dan inspector tetap berfungsi. Factory dapat menggeser tata letak sementara. | PASS |
| Factory inspector | Field tampak bisa diedit, tetapi readOnly; callback mengabaikan konfigurasi. | Konfigurasi sumber jelas hanya baca. “Rancang Versi Baru” membuka draft lokal untuk prompt/model/temperature/token. Save memakai endpoint create-version yang ada dan memilih versi baru, tanpa mutasi sumber/published. | PASS |
| Persetujuan | `bench_eligible` saja membuat approved dihitung kembali sebagai pending. | Predicate bersama `draft && integrity_valid && bench_eligible` pada sidebar, Ringkasan, dan Persetujuan. Approved dipisahkan sebagai sudah disetujui/siap publikasi; histori published tetap terlihat. Approved dengan bukti tidak valid ditandai, tidak dihitung sebagai pending baru. | PASS |
| Bench | Canvas mereduksi hasil menjadi passed/failed, warna skor hijau tetap, metadata fallback memakai skenario yang berbeda. | Satu fungsi status untuk halaman/canvas/inspector: passing terverifikasi hijau, gagal merah, passing unverified amber. Histori dan provenance tetap terlihat; empat ID suite aktual dipakai untuk metadata sebelum evaluasi. | PASS |
| Model/provider | Label “model tidak siap” memakai badge success. | `available` success, `unknown` warning, `unavailable` error. Sumber tetap availability backend; gate eksekusi dan larangan fallback dipertahankan. | PASS |
| Live state/motion | Request pending disebarkan ke node seolah tersedia trace per-node; SVG motion tidak berhenti oleh aturan CSS saja. | Hanya node agregat runtime mengikuti status run aktual. Tidak ada timer tahap eksekusi. SVG motion dilepas ketika prefers-reduced-motion berubah; zoom/scroll juga mengikuti preferensi. Trace Hermes dinyatakan tidak tersedia. | PASS |
| Aksesibilitas/responsive | Clickable div, heading inspector melompat, blok scroll tanpa fokus, inspector sempit, kontras success light kurang, sidebar mobile tersembunyi masih dapat menerima fokus. | Link/button semantik, roving tabs, focus return, keyboard node selection, blok scroll focusable, layout inspector bertumpuk, teal light diperkuat. Sidebar mobile mempunyai focus trap, Escape, focus return dan background inert; sidebar tertutup tidak ikut tab order. | PASS |

Temuan tambahan dalam scope: form sebelumnya mengambil assignment pertama walaupun nonaktif, sehingga option visual dapat berbeda dari state. Default kini berasal dari assignment aktif dengan published version dan integrity/governance valid. Pilihan yang menjadi tidak valid menampilkan placeholder, bukan diam-diam menjalankan assignment pengganti. Versi historis dengan integrity tidak valid diberi peringatan dan tidak diklaim sebagai bukti konfigurasi saat run berlangsung.

## Perubahan pengalaman pengguna

Ringkasan menjadi control center proyek: konteks workspace, lifecycle, agent tersimpan, readiness, perhatian approval, eksekusi terbaru dan aktivitas Core. Semua angka berasal dari snapshot yang tersedia, bukan telemetry sintetis.

Factory membuka konfigurasi utama dalam canvas pada zoom yang terbaca, dengan inspector langsung tersedia. Pusatkan menyediakan tampilan seluruh arsitektur. Posisi node hanya tata letak sementara; refresh/pemilihan versi dapat meresetnya dan posisi bukan konfigurasi agent. Konfigurasi baru hanya menjadi data setelah API create-version berhasil.

Inspector Execution menyediakan DETAIL / OUTPUT / TRACE: Core Run ID, assignment, version, model/provider, parameter konfigurasi, token, waktu, output dan audit tersimpan. Audit Core dijelaskan sebagai peristiwa aplikasi; bukan trace per-node Hermes. Bench menyediakan status scenario, skor dan provenance tanpa mengulang seluruh respons pada inspector ringkasan; respons node skenario tersedia saat node tersebut dipilih.

## File yang berubah

- Konteks dan halaman: `apps/web/src/studio.tsx`, `features/overview.tsx`, `features/runs.tsx`, `features/approvals.tsx`, `features/bench.tsx`, `features/factory.tsx`.
- Canvas: `apps/web/src/components/canvas/aryn-canvas.tsx`, `canvas-builders.ts`, `canvas-inspector.tsx`, `types.ts`, `edges/aryn-edge.tsx`, `nodes/aryn-base-node.tsx`, `nodes/custom-nodes.tsx`.
- Komponen/helper: `apps/web/src/components/version-form.tsx`, `components/shared.tsx`, `components/ui/button.tsx`, `lib/studio-state.ts`, `lib/motion.ts`, `styles.css`.
- Regression: `apps/web/src/test/studio-context.test.tsx`, `canvas-state.test.tsx`, `canvas-inspector.test.tsx`, `studio-fixtures.ts`, `apps/web/e2e/studio.spec.ts`.
- Server browser terisolasi: `tests/studio_server.py`; menambahkan proyek kosong kedua hanya pada SQLite disposable untuk menguji project switching nyata.
- Dokumentasi: dokumen ini dan `docs/studio.md`.

Nama pada daftar relatif terhadap folder induk yang disebutkan. `VersionForm` diekstrak dari implementasi Factory existing dan dipakai oleh modal serta inspector, dengan validasi yang sama. Tidak ada dependency baru.

## Bukti pengujian

Tes negatif awal berhasil mereproduksi empat kegagalan konteks dan empat kegagalan builder canvas sebelum perbaikan. Pengujian browser juga menemukan heading-order, scrollable-region-focusable dan contrast success 4,39:1 pada light/tablet; semuanya diperbaiki tanpa menonaktifkan rule axe.

| Gate | Perintah | Hasil aktual |
| --- | --- | --- |
| Backend lengkap, API/contracts, governance, ownership, idempotency, migrasi dan persistence | `.\.venv\Scripts\python.exe -m pytest -q` | 185 PASS, 3 SKIP, 9 warning; 38,43 detik |
| Frontend component/builder regressions | `npm.cmd test` | 29 PASS pada 5 file |
| TypeScript | `npx.cmd tsc --noEmit`; juga `tsc -b` dalam build | PASS |
| Build produksi | `npm.cmd run build` | PASS; ada warning ukuran bundle Vite |
| Browser HTTP/Core/SQLite terisolasi | `npx.cmd playwright test` | 12 PASS; sekitar 2 menit |
| Verifikasi ulang Execution setelah pesan missing-run diperjelas | `npx.cmd playwright test --grep="canvas: historis" --reporter=list` | 1 PASS; 8,4 detik |
| Aksesibilitas | axe melalui Playwright, tanpa pengecualian rule | 0 violation pada halaman/state yang diuji |
| Diff | `git diff --check` | PASS |

Playwright memakai API, Core, Bench runner dan SQLite aktual pada port 8711, dengan `tests/studio_runtime.py` sebagai runtime test double yang eksplisit. Tes lifecycle tidak menyisipkan PASS langsung ke database. Approval/publish/assignment/run dilakukan melalui API existing. Tes draft memeriksa versi source masih published dengan hash/prompt yang sama, sementara versi baru berstatus draft tanpa Bench/governance eligibility.

Regression browser menggunakan dua assignment/version berbeda, menahan request HTTP baru pada barrier pengujian, memeriksa histori tetap A tanpa status running sintetis, lalu meneruskan request asli dan memeriksa hasil baru B. URL run yang tidak ditemukan menghasilkan pesan yang tepat tanpa inspector konfigurasi run lain. Drag benar-benar dicoba: Factory berpindah, Execution tetap pada posisi semula. Connect affordance tidak tersedia pada Execution/Bench. Node selection, inspector tabs, save, project selector, dialog dan sidebar keyboard diuji melalui interaksi.

Matriks axe meliputi Ringkasan, Factory, Execution, Bench, Persetujuan, Tata Kelola, Pengaturan, Brief dan Relay pada dark/light. Detail Factory, hasil Bench dan Execution diuji pada tablet 768px dan mobile 390px, termasuk inspector terbuka dan draft Factory. Tidak ada overflow horizontal pada halaman yang diuji. Preferensi reduced motion diuji saat berubah pada SVG, serta pada CSS ambient dan kontrol canvas dalam browser. Page error tidak tercatat pada matriks tersebut.

Intersepsi snapshot/workspace dalam tes hanya memproyeksikan status negatif untuk tampilan; tidak digunakan untuk operasi governance. Screenshot berlabel pengujian terisolasi bukan bukti availability model provider live. Bukti lokal berada di `.local/evidence/studio-*.png`; laporan browser di `apps/web/playwright-report` (keduanya diabaikan Git). Pemeriksaan lint Python tambahan dicoba, tetapi Ruff tidak terpasang pada virtual environment; tidak diklaim PASS.

## API, database, dan batas validasi

Tidak ada endpoint, payload produksi, schema, migration, contract runtime, atau konfigurasi Hermes yang diubah. Save inspector memakai `POST /api/projects/{project}/blueprints/{blueprint}/versions`. `Run.session_id` tetap assignment ID menurut implementasi existing. Seluruh otorisasi dan pemeriksaan integrity/evidence tetap berada di Core.

Tiga tes live inference tetap skip karena memerlukan opt-in pemilik. Tidak ada request model live/berbayar dari pekerjaan ini. Suite backend yang ada memeriksa health/capabilities Hermes secara read-only; PASS pengujian runtime terisolasi tidak membuktikan availability maupun mutu output provider live. Availability unknown/unavailable masih memblokir Bench/Run. Perbaikan katalog/discovery runtime sebelumnya tidak dilonggarkan.

Trace per-node dan streaming runtime belum tersedia. Studio menampilkan status agregat request/run yang benar-benar diketahui. Canvas Factory adalah architecture/configuration workspace existing, dengan tata letak sementara; bukan arbitrary workflow graph atau penyimpanan layout. Vite masih memberi warning chunk JavaScript sekitar 684 KB (gzip sekitar 212 KB); build berhasil. Axe dan Chromium menguji state/matriks yang disebutkan, bukan jaminan seluruh kombinasi data, browser atau screen reader.

## Satu sesi UAT melalui Studio

1. Ringkasan: pilih proyek bila terdapat lebih dari satu, bandingkan blueprint/run/Jejak Core dengan halaman terkait; readiness tidak boleh hijau saat belum siap dan tidak ada klaim audit 100%.
2. Factory: buka versi published, pilih node dengan mouse/keyboard, geser tata letak dan coba Pusatkan. Konfigurasi source hanya baca. Rancang Versi Baru, ubah empat parameter, Save; bandingkan versi source dengan draft baru. Draft baru harus memerlukan Bench dan approval sendiri.
3. Execution: buka run historis A, pilih assignment B pada form. Canvas/inspector harus tetap A. Jika tersedia runtime/model yang terverifikasi dan izin pengiriman, jalankan request baru; status pending terpisah, lalu hasil aktual baru dipilih. Jika model unknown/unavailable, gate tetap memblokir. TRACE menyatakan tidak tersedia sambil menampilkan audit Core.
4. Bench/Persetujuan: buka hasil historis yang memang ada. Verified pass hijau, gagal merah, passing unverified amber dengan penjelasan evidence. Canvas hanya baca. Versi approved muncul sebagai sudah disetujui, bukan menunggu review; published terlihat pada histori.
5. Ganti tema, ukuran tablet/mobile dan preferensi reduced motion. Buka/tutup inspector, rancang lalu batalkan draft, coba Tab/Shift+Tab, pan/zoom/select dan Escape sidebar/dialog. Brief/Relay tetap jelas belum tersedia.

Tidak perlu membuat data historis palsu untuk UAT; status yang belum ada pada database pemilik sudah diuji otomatis secara terisolasi. Sesi UAT dilakukan bersama setelah commit; pekerjaan berhenti di sini.

## Menjalankan melalui Windows PowerShell

```powershell
Set-Location D:\ARYN\aryn-labs\aryn
.\scripts\stop-studio.ps1
.\scripts\start-studio.ps1 -SkipInstall
```

Launcher membangun ulang frontend dan membuka `http://127.0.0.1:8710`. Untuk instalasi dependensi awal, jalankan tanpa `-SkipInstall`. Jika kebijakan skrip memblokir:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-studio.ps1 -SkipInstall
```

Launcher/database pengguna tidak dijalankan atau direset oleh tes browser. Tidak ada push atau perubahan ke `main` dalam pekerjaan ini.
