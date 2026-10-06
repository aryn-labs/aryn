# Perbaikan UAT Bench dan ketersediaan model

Tanggal verifikasi: 6 Oktober 2026. Branch: `development`; HEAD awal aktual
`361d24b`. Dokumen ini hanya mencakup dua temuan UAT. Desain umum Studio,
konfigurasi Hermes, toolset, dan schema database tetap dipertahankan.

## Audit dan akar masalah

1. Riwayat dan detail Bench menggabungkan `passed` dan `verified` menjadi satu
   boolean tampilan. Akibatnya hasil historis 4/4 yang kehilangan provenance
   tampil merah sebagai Gagal. Verifikasi evidence pada backend sudah benar:
   hasil tersebut memang tidak boleh digunakan untuk approval/publish.
2. `/api/workspace` mengembalikan katalog kebijakan statis Nous sebagai pilihan
   model tanpa informasi availability. Health/tool confinement membuktikan
   kesiapan gateway, bukan keberadaan model. Bench memperlakukan penolakan model
   seperti kegagalan skenario biasa dan dapat mengirim empat request yang salah.
   `/v1/models` Hermes berisi alias routing; `/api/model/options` juga dapat
   memakai inventaris kurasi/cache. Keduanya tidak membuktikan positif bahwa
   model tertentu masih dapat menjalankan inference.

Sebelum perbaikan, pengujian negatif Bench/Run unavailable menghasilkan HTTP 200
alih-alih 409 (dua tes gagal). Lima tes tampilan status juga gagal. Pengujian
penyimpanan historis sudah lulus dan mekanisme tersebut dipertahankan.

## Perilaku yang diterapkan

| Kasus | Status/tindakan |
| --- | --- |
| 4/4, skor 100%, passed dan verified | Lulus |
| 4/4, skor 100%, passed tetapi unverified | Tidak Terverifikasi, warna warning/oranye |
| Skenario gagal, skor kurang dari 100% | Gagal |
| Model unavailable | HTTP 409; Bench/Run diblokir sebelum dispatch |
| Availability unknown | HTTP 503; Bench/Run diblokir sampai ada bukti availability |
| Model ditolak sesudah preflight | Hentikan suite pada penolakan pertama; jangan dispatch skenario berikutnya |

Detail hasil unverified menjelaskan bahwa respons historis tetap tersimpan dan
tidak dapat dipakai untuk persetujuan/publikasi. Status skenario historis tidak
diubah menjadi bukti baru. Validasi governance backend tidak diperlemah.

Adapter membaca `/api/model/options` tanpa mengubah provider/model Hermes.
Inventaris yang hanya mencantumkan kandidat menghasilkan `unknown`. Model yang
tidak ditawarkan, tercatat unavailable, atau telah ditolak provider diblokir.
Discovery yang gagal/malformed menghasilkan `unknown`. Cache tampilan berlaku
15 detik; preflight meminta pemeriksaan baru pada adapter tanpa meminta Hermes
mengubah atau me-refresh konfigurasi. Penolakan provider diingat selama proses
adapter hidup. Tidak ada silent fallback maupun prompt berbayar untuk probing.

Studio menampilkan status model pada pilihan model, menonaktifkan model
unavailable, menjelaskan alasan tombol Bench/Run diblokir, dan mempertahankan
model yang sudah dipilih pada versi. Pesan tampil pada seluruh tab detail agent.

## Perubahan file dan kontrak

- Tampilan: `apps/web/src/features/bench.tsx`, `factory.tsx`, `runs.tsx`,
  `components/shared.tsx`, `lib/types.ts`, `styles.css`.
- Runtime/Core/API: `packages/contracts/runtime.py`,
  `packages/runtime_adapters/hermes/adapter.py`, `modules/bench/runner.py`,
  `modules/core/workflows/coordinator.py`, `services/api/studio.py`.
- Pengujian: `apps/web/src/test/bench-evidence.test.tsx`,
  `apps/web/e2e/studio.spec.ts`, `tests/security/test_uat_model_availability.py`,
  `tests/integration/test_studio_api.py`. Runtime double lama di
  `tests/studio_runtime.py`, `tests/unit/test_agent_factory_and_bench.py`,
  `tests/integration/test_agent_lifecycle_workflow.py`,
  `tests/security/test_agent_security_and_governance.py`,
  `tests/security/test_core_persistence_security.py`,
  `tests/security/test_rbac_authorization_boundary.py`, dan
  `tests/e2e/test_smoke_end_to_end.py` menyatakan availability terisolasi secara
  eksplisit; tidak ada bypass pada adapter produksi.
- Kontrak baru: `RuntimeModelAvailability`, `model_availability()`,
  `require_model_available()`, `ModelUnavailableError`. Field tambahan pada
  `/api/workspace.models`: `availability`, `availability_reason`,
  `availability_source`. API Bench/Run memiliki respons 409/503 baru.
- Tidak ada migrasi, penghapusan histori, atau perubahan format evidence.

## Bukti pengujian

- `.\.venv\Scripts\python.exe -m pytest -q`: **185 lulus, 3 dilewati**,
  9 warning deprecation. Tiga pengujian inference live memerlukan opt-in dan
  tidak dijalankan. Lifecycle, hash/provenance, approval/publication, ownership,
  concurrency, migrasi SQLite, dan kompilasi migrasi PostgreSQL tetap lulus.
- `npm run test` di `apps/web`: **8 lulus** dalam dua file.
- `npm run build`: **berhasil**, pemeriksaan TypeScript dan Vite.
- `npx playwright test`: **6 lulus, 2 gagal**. Kedua tes UAT baru lulus;
  warning oranye dan tiga status diperiksa di browser. Hasil dibuat melalui
  Bench sebenarnya dengan runtime double terisolasi. Proyeksi negatif UI tidak
  menulis PASS ke database dan tidak digunakan untuk approval/publish.
- Dua kegagalan Playwright adalah pemeriksaan kontras tema terang pada
  navigasi dan vertical slice. Sebelum kegagalan kontras, alur UI Bench →
  approval → publish → assignment → execution → hasil tersimpan/audit berhasil.
  Kegagalan yang sama direproduksi dengan source frontend baseline `361d24b`
  yang diekstrak ke `.local/uat-baseline-361d24b`, dibangun terpisah, serta
  dilayani dengan database disposable/runtime double: **4 lulus, 2 gagal**.
  Contoh: badge Studio memiliki rasio 4,39:1, di bawah 4,5:1. Menunggu transisi
  selesai tidak menghilangkan temuan. Aturan Axe tidak dinonaktifkan; warna umum
  tidak diubah karena berada di luar dua temuan UAT.
- Tes transport/API membuktikan unavailable/unknown menghasilkan **nol panggilan
  inference**; penolakan setelah preflight menghasilkan **satu**, bukan empat,
  request dan retry tidak dispatch ulang. Tidak ada fallback model.
- Histori evaluasi lama tetap ada; legacy evidence tidak eligible dan approval
  ditolak. Pemeriksaan SQLite `integrity_check=ok`, `foreign_key_check` kosong.
- Ruff `E4,E7,E9,F` pada file backend terkait dan `git diff --check`: lulus.

## Keterbatasan runtime lokal dan UAT

GET baca-saja pada Hermes lokal menghasilkan HTTP 200, provider `nous`,
authenticated, source `hermes`, 58 kandidat: `stealth/space-bunny-alpha`
tercantum sekaligus berada dalam `unavailable_models`; kedua ID lama
`hermes-3-llama-3.1-8b` dan `hermes-3-llama-3.1-70b` tidak tercantum.
Ketiga kandidat terdaftar ARYN karena itu diblokir. Tidak ada inference live,
perubahan Hermes, perluasan katalog kebijakan, atau klaim PASS model aktual.

Hermes saat ini belum memberikan bukti positif availability yang cukup melalui
endpoint yang diaudit. Bahkan kandidat yang tercantum hanya berstatus unknown;
Bench/Run produksi tetap diblokir. Membuat model lain tersedia memerlukan
pekerjaan terpisah pada discovery/katalog dan verifikasi yang diizinkan.

Dalam satu sesi Studio, lihat riwayat Bench lama 4/4 dan detail alasan status,
pastikan approval/publish tidak memakai hasil unverified, lalu buka versi dengan
model unavailable pada Konfigurasi/Hasil Bench dan Eksekusi untuk melihat pesan
serta tombol yang diblokir. Jangan mengedit provenance database produksi demi
membuat skenario UAT. Jalur positif penuh telah diverifikasi otomatis pada
runtime terisolasi; UAT inference aktual menunggu model yang siap dan izin.

Untuk memuat kode/build terbaru melalui Windows PowerShell:

```powershell
Set-Location D:\ARYN\aryn-labs\aryn
.\scripts\stop-studio.ps1
.\scripts\start-studio.ps1 -SkipInstall
```

Studio: `http://127.0.0.1:8710`. Reset database tidak diperlukan.
