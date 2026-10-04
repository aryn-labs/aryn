# ARYN Studio — pengujian lokal

ARYN Studio berada di `apps/web`; API aplikasi berada di `services/api`. Implementasi memakai React, TypeScript, Tailwind CSS, pola komponen shadcn/ui berbasis Radix, Lucide, dan FastAPI. Factory, Bench, identity, permission, approval, budget, dan audit tetap menggunakan layanan repository yang ada.

## Menjalankan di Windows PowerShell

Prasyarat: Python 3.11+ dan Node.js 22.14+ tersedia pada PATH. Dari repository:

```powershell
Set-Location D:\ARYN\aryn-labs\aryn
.\scripts\start-studio.ps1
```

Launcher membuat `.venv`, memasang dependensi dari package lock, membangun frontend, menjalankan API di `127.0.0.1:8710`, lalu membuka browser. Jika eksekusi skrip dibatasi oleh kebijakan PowerShell, gunakan proses sekali jalan tanpa mengubah kebijakan mesin:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-studio.ps1
```

Buka **http://127.0.0.1:8710**. Setelah instalasi awal, gunakan `-SkipInstall -SkipBuild` untuk menjalankan hasil build yang sudah ada. `-NoBrowser` menonaktifkan pembukaan browser, `-Port 8712` memakai port loopback lain. Launcher menolak port yang dipakai proses lain. Hentikan dengan:

```powershell
.\scripts\stop-studio.ps1
```

API dapat dijalankan di terminal secara langsung setelah build:

```powershell
.\.venv\Scripts\python.exe -m services.api --port 8710
```

`apps/web` menyediakan mode Vite untuk pengembangan tampilan; operasi terpadu dan pengujian pengguna menggunakan build yang dilayani FastAPI pada origin yang sama. Tidak diperlukan layanan publik, proxy Hermes dari browser, atau konfigurasi CORS permisif.

## Mencoba vertical slice

1. Buka **Agent Factory**, buat blueprint, lalu simpan versi. Blueprint dan versi merupakan data berbeda. Versi baru tidak menimpa konfigurasi lama.
2. Pilih model yang terdaftar dan instruksi sistem. Studio saat ini hanya mendukung agent teks tanpa tool runtime. Temperature dan batas output diteruskan ke adapter.
3. Jalankan **Bench**. Dialog mengungkap penggunaan penyedia model jarak jauh melalui Hermes dan memerlukan pilihan eksplisit pengguna. Suite berisi empat skenario tetap; request browser tidak dapat mengganti skenario atau menyuntikkan skor.
4. Buka setiap hasil skenario untuk melihat respons aktual, model, token, durasi, dan alasan kegagalan. Skor harus 100%; kegagalan terakhir membatalkan kelayakan hasil lama.
5. **Tinjau dan setujui** dengan catatan keputusan. Core mengikat approval ke SHA-256 konfigurasi. Hash dari tinjauan browser harus cocok dengan database. Persetujuan hanya diizinkan untuk admin manusia development yang aktif.
6. **Publikasikan versi**. Core memeriksa evaluasi dan approval. Versi yang dipublikasikan tidak dapat diubah.
7. Buka **Penugasan**, beri peran dalam proyek aktif. Versi harus dipublikasikan dan blueprint harus cocok dengan induk versi. Penugasan tidak memindahkan blueprint antarproyek.
8. Buka **Eksekusi**, isi instruksi riset dan konfirmasikan pengiriman ke model pilihan. Core memeriksa izin, penugasan, model, dan preflight budget sebelum Hermes.
9. Lihat output asli, model aktual, status, token input/output/total, hasil tersimpan, serta audit Core. Refresh halaman mempertahankan data. Request duplikat dengan kunci yang sama tidak mengeksekusi ulang; kunci yang dipakai untuk input lain ditolak.

## Keamanan dan ruang lingkup

Alur operasional: **Web → ARYN API → ARYN Core → Hermes Runtime Adapter → Hermes**. Bench menggunakan Factory dan runner yang ada dengan adapter teks terbatas. Semua toolset Hermes harus nonaktif sebelum evaluasi maupun eksekusi Studio. Studio tidak mengubah hardening Hermes dan tidak membuka host tools.

API hanya mendengarkan loopback. Host harus cocok dengan alamat launcher; permintaan dari IP lain ditolak. Tidak ada endpoint penerbitan identity binding untuk browser. Server memiliki signing key acak per proses dan membuat konteks Core untuk principal development tetap yang diprovisikan pada organisasi/proyek lokal. Keanggotaan tersimpan pada DB; restart tidak mengembalikan membership yang dicabut.

Sesi lokal memakai cookie acak HttpOnly/SameSite Strict dengan expiry delapan jam. Semua endpoint API setelah bootstrap memerlukan sesi. Mutasi memerlukan origin yang tepat dan token CSRF sesi. Input identity/roles/security context dari browser tidak diterima. CSP membatasi koneksi ke origin Studio dan memblokir framing. Ini akses development untuk komputer lokal tepercaya, **bukan autentikasi produksi**; proses lokal yang sudah memiliki akses mesin berada di luar batas ini.

Kredensial Hermes dibaca di server dari `API_SERVER_KEY` atau berkas `.env` Hermes lokal yang sudah ada. Nilai ini tidak masuk bundle frontend, respons API, Git, atau antarmuka. Tidak ada formulir browser untuk secret. Respons model diperlakukan sebagai teks tidak tepercaya, tanpa eksekusi HTML. Error runtime yang ditampilkan ke browser disanitasi.

Database khusus Studio: `.local/studio.sqlite3`, diabaikan Git. Alembic menerapkan migrasi pada startup, termasuk `005_bench_provenance`. Blueprint, konfigurasi, evaluation provenance, approval, assignment, run, budget ledger, dan audit menggunakan schema/repository yang ada. Run yang tertinggal saat restart ditandai gagal; versi yang tertinggal dalam evaluasi ditandai ditolak dan dapat dievaluasi kembali.

Suite final `research-safety-1.2.0` menambahkan pengenalan penolakan dalam Bahasa Indonesia, kontraksi Inggris, dan abstensi tanggal tidak valid. Pola injection/host tetap ditolak; angka pendapatan fiktif berprefiks `$` dan `Rp` ditolak. Suite regex ini merupakan gate riset awal, bukan pembuktian keamanan lengkap atau penilaian mutu ilmiah. Hasil lama dipertahankan dengan versi evaluator masing-masing.

## Antarmuka dan batas implementasi

Ringkasan menampilkan jumlah aktual dari proyek dan aktivitas Core; tidak ada seed agent, riwayat, atau statistik buatan. Agent Factory, Eksekusi, Bench, Persetujuan, Tata Kelola, dan Pengaturan aktif. Workspace/project selector memakai proyek nyata yang dapat dibaca principal. UI berbahasa Indonesia, dengan semantic tokens dark/light, font Geist/Geist Mono, sidebar collapsible, pencarian tabel, loading/error/empty/disconnected states, dialog dengan focus trap, navigasi tab keyboard, serta layout desktop/tablet/mobile.

**Belum tersedia:** layanan Brief dan Relay, login produksi/multiuser, host tools, Gemini live, Ollama, dan trace Hermes terstruktur untuk direct turn. Audit Core tersedia; Studio tidak mengarang trace yang tidak disimpan runtime. Pengaturan menampilkan budget proyek dan ledger token; tarif biaya dan budget uang tidak diklaim terukur. Model katalog yang belum disediakan Hermes akan menghasilkan penolakan nyata; tidak ada fallback otomatis. Manajemen proyek/organisasi dan pengaturan kredensial belum menjadi UI mutation.

Jika Hermes tidak tersedia, kredensial salah, atau toolsets aktif, indikator menjelaskan ketidaksiapan dan server memblokir Bench/Run. Factory dan data tersimpan tetap dapat digunakan. Detail readiness Hermes dapat degraded walaupun jalur teks dapat dipakai; Studio tidak mengklaim runtime keseluruhan bebas masalah.

## Pengujian dan traceability

```powershell
Set-Location D:\ARYN\aryn-labs\aryn
.\.venv\Scripts\python.exe -m pytest -q
Set-Location apps\web
npm.cmd run build
npm.cmd test
npm.cmd exec playwright -- install chromium
npm.cmd run test:e2e
npm.cmd audit
```

Browser tests memakai API HTTP, Core, dan SQLite aktual pada **port 8711** dengan `tests/studio_runtime.py` sebagai test double yang ditandai pengujian terisolasi. Tidak ada mock runtime di layanan production/local Studio pada port 8710. Tes tidak mengubah database pengguna. Intersepsi respons hanya dipakai untuk menguji penolakan/koneksi terputus. Bukti screenshot browser ditulis ke `.local/evidence`; laporan Playwright berada di `apps/web/playwright-report`.

| Persyaratan pengguna | Bukti otomatis |
| --- | --- |
| Bagian 4: navigasi, states, tema, responsiveness | `apps/web/e2e/studio.spec.ts` |
| Bagian 5: seluruh mutation/lifecycle, refresh, DB persistence, idempotency | `tests/integration/test_studio_api.py`, browser lifecycle test |
| Bagian 6: loopback, origin, CSRF, identity spoof, RBAC, tools confinement | `test_studio_api.py`, suite security yang sudah ada |
| Bagian 7: validasi, error, permission denial, keyboard, aksesibilitas | component tests, Playwright + axe, API negatives |
| Evaluator multilingual + pola penolakan berbahaya | `tests/unit/test_bench_localization.py` |
| Migrasi schema tetap mempertahankan data | `test_schema_upgrade_004_retains_data` |

Dokumen ARYN-PRD-001/ARCH/TECH/SEC privat belum tersimpan di checkout `aryn-docs`; indeksnya menyatakan NO. ID P0 privat tidak direka. Implementasi mengikuti AGENTS.md, SECURITY.md, contracts, dan perilaku Core aktual. Referensi desain yang ditinjau: [Linear refresh](https://linear.app/changelog/2026-03-12-ui-refresh), [Dify Workflow Studio](https://dify.ai/workflows), [Langfuse observability](https://langfuse.com/docs/observability/overview), [shadcn dashboard blocks](https://ui.shadcn.com/blocks?category=dashboard). Identitas, palette, layout, dan alur Studio dibuat untuk ARYN.

Hasil tes dan bukti live akhir dicatat di `docs/studio-validation.md`.
