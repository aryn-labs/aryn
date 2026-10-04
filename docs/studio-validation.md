# Bukti validasi ARYN Studio

Tanggal: 5 Oktober 2026, Asia/Bangkok. Baseline yang diperiksa sebelum perubahan: `033ce68b88c1c729cdf6dc463b3f35167a82e7ff` pada branch `development`. Seluruh perubahan Studio dibuat pada branch tersebut. Tidak ada operasi terhadap `main` atau push ke GitHub.

## Hasil akhir

| Gate | Hasil | Bukti yang dijalankan |
| --- | --- | --- |
| Regresi backend, contracts, security, persistence, API | PASS — 109 tes | `.\.venv\Scripts\python.exe -m pytest -q`; 15,65 detik |
| Komponen formulir React | PASS — 3 tes | `npm.cmd test`; Vitest |
| Integrasi browser HTTP/Core/SQLite | PASS — 6 tes | `npm.cmd run test:e2e`; Playwright, runtime pengujian terisolasi |
| TypeScript dan build produksi frontend | PASS | `npm.cmd run build` |
| Dependensi frontend | PASS — 0 vulnerability | `npm.cmd audit` pada `apps/web` |
| Lint Python boundary/test/migrasi baru | PASS | Ruff dengan `--isolated --select E4,E7,E9,F,I`; bukan klaim lint seluruh repository |
| Konsistensi diff | PASS | `git diff --check` |
| Aksesibilitas otomatis | PASS — 0 pelanggaran pada tampilan yang diperiksa | axe pada dark/light, mobile, evaluasi, dan audit; tidak menggantikan audit aksesibilitas menyeluruh |
| Responsivitas | PASS | Desktop 1440px, tablet 768px, mobile 390px; tidak ada overflow horizontal pada halaman yang diuji |
| Launcher Windows | PASS | Instalasi `.venv`/npm, build, start, stop, restart, reuse, listener loopback dan PID interpreter aktual |
| Siklus live Hermes melalui browser | PASS | Bench 4/4 → approval → publikasi → assignment → run selesai → refresh/persistence → audit |

Backend mengeluarkan tiga peringatan deprecation dari Starlette TestClient/httpx dan konfigurasi path Alembic. Tidak ada kegagalan tes. Browser live tidak mencatat error konsol kritis setelah reload.

Tes negatif mencakup origin/Host/CSRF/fetch metadata, identitas browser palsu, sesi berakhir, klien non-loopback, pencabutan membership setelah restart, izin viewer, toolset aktif, runtime terputus, model tidak diizinkan, versi belum lulus, hash berbeda, approval belum ada, hasil lulus lama yang dibatalkan kegagalan baru, assignment lintas blueprint/nonaktif, duplikasi request, budget input+output tidak cukup, serta respons runtime gagal yang tidak boleh dicatat selesai.

## Bukti live, bukan mock

UI menggunakan API pada `http://127.0.0.1:8710` dan Hermes yang sudah tersedia pada `127.0.0.1:8642`. Operasi dilakukan lewat formulir dan dialog Studio. Tidak ada skor atau hasil Bench yang disuntikkan untuk siklus ini. Model yang diminta dan dilaporkan runtime: `stealth/space-bunny-alpha`, provider `nous`; seluruh toolset runtime nonaktif.

| Data nyata yang tersimpan | Nilai |
| --- | --- |
| Blueprint | `Research Agent — Verifikasi Live` / `abp_d45eaf976d61403b` |
| Versi | `1.0.0` / `av_72502a81566b4643`, status `published` |
| Hash konfigurasi | `a013b7484617104ad993057af4ad2896e7de175f38040309a3446e8a4cbdb673` |
| Evaluasi final | `eval_6c2cfac6dcd54a64`, suite `research-safety-1.2.0`, skor 100%, 4/4 |
| Approval Core | `appr_71bb1eeff35b4bb7`, terikat hash versi |
| Assignment aktif | `asgn_069e1069877f4a64`, peran `Peneliti verifikasi live` |
| Run | `run_8e5afe4c8f3143c19c28e2bb39662cd3`, `completed` |
| Usage run | Input 1.298, output 102, total **1.400 token** |
| Audit run | `core.run.initiated`, `core.run.completed`, `studio.run.assignment` |

Instruksi run: “Jelaskan dalam tiga poin singkat perbedaan likuiditas dan solvabilitas untuk edukasi umum. Jangan memberi rekomendasi investasi atau mengarang data perusahaan.” Output asli model disimpan dan ditampilkan tanpa pengeditan. Ini data verifikasi implementasi lokal, ditandai demikian pada deskripsi blueprint; bukan riwayat operasional produk yang direka.

Evaluasi awal benar-benar ditolak: suite 1.0.0 memberi 25%, 1.1.0 dan 1.1.1 memberi 75%. Respons penolakan Indonesia, apostrof kontraksi Inggris, dan abstensi “did not exist” tidak dikenali evaluator lama. Perbaikan pola dilengkapi tes positif/negatif dan versi suite; threshold tetap 100% serta larangan injection, host command, dan angka pendapatan fiktif dipertahankan. Semua hasil gagal tetap tersimpan. Approval dilakukan setelah evaluasi final lulus.

Query SQLite memverifikasi status publikasi, provenance suite/model/hash, empat output evaluasi beserta usage, approval, assignment, run, dan tiga event audit. Refresh browser dan restart API mempertahankan hasil. Bukti lokal yang tidak masuk Git:

- `.local/evidence/studio-live-db.json`: hasil pemeriksaan database dan IDs.
- `.local/evidence/studio-live-result.jpg`: screenshot hasil live setelah restart/reload.
- `.local/evidence/studio-live-audit.jpg`: screenshot audit run.
- `.local/evidence/studio-dark.png`, `studio-light.png`, `studio-tablet.png`, `studio-mobile.png`: screenshot pengujian browser terisolasi.
- `.local/evidence/studio-isolated-run.png`: hasil runtime test double, berlabel pengujian terisolasi.
- `apps/web/playwright-report/index.html`: laporan browser otomatis.

## Batas yang tetap berlaku

Hermes live tersedia dan jalur teks terbukti berjalan. Readiness rinci Hermes dilaporkan `degraded` karena pemakaian disk sekitar 92,3%; ini bukan kegagalan jalur teks atau klaim kesehatan runtime penuh. Hardening Hermes tidak diubah. Token budget Core merupakan estimasi per turn dan ledger token aktual; biaya uang tidak diukur.

Brief dan Relay hanya memiliki navigasi serta penjelasan status belum tersedia. Tidak ada login produksi, manajemen multiuser/proyek melalui UI, host tools, Gemini live, Ollama, atau trace Hermes terstruktur untuk direct turn. Audit Core aktif. Suite regex Bench merupakan gate awal dan bukan pembuktian keamanan lengkap maupun penilaian mutu riset menyeluruh.

Identitas development diterbitkan server, binder internal tidak dibuka untuk browser, dan kredensial tidak dimasukkan bundle/Git. Layanan hanya loopback. Langkah berikutnya adalah pengujian pengguna terhadap Studio dan slice ini; pengembangan Brief/Relay tidak dilanjutkan.

Lihat [cara menjalankan dan arsitektur](studio.md) serta [daftar lengkap file berubah](studio-files.md).

## Pembaruan identitas visual — 5 Oktober 2026

Sidebar memakai simbol dari logo resmi yang diberikan pemilik produk. Background dihapus dengan pemrosesan piksel lokal setelah persetujuan pengguna; hasil imagegen yang memiliki artefak tidak digunakan. PNG lengkap tersimpan di `D:\ARYN\Logo Aryn Transparan.png` (858 × 707, RGBA; 468.150 piksel transparan penuh dan 127.859 piksel opak penuh). File sumber tidak ditimpa. Asset simbol tema terang mempertahankan warna asli; varian tema gelap memakai foreground terang dengan aksen biru tetap dipertahankan.

Brand berupa elemen statis tanpa tautan, handler klik, atau tab stop. Build TypeScript/Vite **PASS** dan enam pengujian Playwright **PASS** (25,7 detik). Pemeriksaan tambahan mencakup pemuatan PNG pada kedua tema, logo tanpa elemen interaktif, klik tetap di halaman Agent Factory, logo tidak menerima fokus keyboard, serta simbol tetap terlihat dan muat pada sidebar yang diciutkan dan navigasi mobile. Pengujian menjalankan API/Core/database terisolasi dengan runtime pengujian, tanpa menjalankan Bench atau Hermes live pada data pengguna untuk perubahan visual ini.

Pemeriksaan visual browser lokal `127.0.0.1:8710` menunjukkan logo tanpa bidang putih pada kedua tema. Screenshot tersimpan di `.local/evidence/studio-logo-dark.jpg` dan `studio-logo-light.jpg`. Tidak ada perubahan API, kontrak, gate Core, atau konfigurasi runtime.
