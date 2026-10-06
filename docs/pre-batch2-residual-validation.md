# Residual pre-Batch-2 — 7 Oktober 2026

Branch: `development`, mulai dari `d7bea51`. Scope hanya residual Execution,
completion Bench, konfigurasi, launcher dan coupling database internal 9Router.
Tidak ada perubahan Core authority, Hermes runtime, instalasi gateway 9Router,
exact-model enforcement, evidence/governance Bench, approval/publish, assignment,
idempotency, ownership run, immutable versioning, atau pekerjaan Batch 2.

## Bug dan perubahan

1. `/runs` tanpa `hasil` sebelumnya mengambil `data.runs[0]`, sehingga selector
   bisa memilih B sementara canvas menampilkan historical A. Sekarang **NEW
   EXECUTION** mengikat canvas ke published version/assignment pilihan. Inspector
   berisi selector, assignment/inline assignment, prompt, consent dan Run. Canvas
   tidak memuat output lama; node/edge idle sampai event actual run diterima.
2. **HISTORICAL RUN** hanya aktif melalui `?hasil=<run_id>`; canvas dan Inspector
   DETAIL / OUTPUT / TRACE hanya memakai assignment/version/run historis. Form
   baru tidak disisipkan ke Inspector historis. Tombol **Eksekusi baru** kembali
   ke mode baru; pilihan terakhir dapat dipakai tanpa mengganti canvas historis.
   Run baru selesai memilih URL `?hasil=<new_run_id>` dan result/versi miliknya.
   Historical ID yang hilang tidak memakai run atau versi lain sebagai fallback.
3. Bench frontend sebelumnya membaca `res.id`, padahal runner menghasilkan
   `evaluation_id`. JSON response dan SSE `bench.completed` sekarang mempunyai
   `evaluation_id`, `version_id`, serta `evaluation` persis dari record tersimpan
   dengan `verified` hasil verifier server yang sudah ada. Field result existing
   tetap tersedia. API menahan completion runner sampai persistence dan usage
   berhasil; kegagalan persistence menghasilkan `bench.error`, tanpa completion.
   Frontend memvalidasi kesesuaian ID/version, langsung memilih evaluation baru,
   dan menyelaraskan `/bench?versi=<version_id>&evaluasi=<evaluation_id>` sebelum
   snapshot refresh. Result event tersedia selama snapshot belum diperbarui;
   snapshot authoritative kembali diprioritaskan bila record sudah tersedia.
   4/4 verified = LULUS; <4/4 = GAGAL; 4/4 unverified = TIDAK TERVERIFIKASI.
4. `packages/config.py` adalah source of truth `ARYN_ENV`, `ARYN_STUDIO_HOST`,
   `ARYN_STUDIO_PORT`, `ARYN_RUNTIME_BASE_URL`, `ARYN_9ROUTER_BASE_URL`, dan
   `ARYN_9ROUTER_API_KEY`. Development defaults hanya didefinisikan di satu tabel;
   konstruksi non-development memerlukan endpoint eksplisit. GatewaySettings,
   runtime adapter, API dan launcher memakai resolver tersebut. Whitespace dan
   trailing slash endpoint dinormalisasi konsisten; loopback/URL validation tetap
   berlaku. Gateway key tetap opsional untuk gateway tanpa autentikasi.
5. `scripts/aryn-config.ps1` memuat environment dan memanggil resolver Python.
   Ketiga launcher tidak mendefinisikan default endpoint sendiri. `production`
   dengan endpoint kosong ditolak sebelum service start. CLI port override tetap
   eksplisit, dan runtime override divalidasi kembali. Ketiganya mendukung
   `-CheckOnly`; combined check tidak start service, build atau inference.
   `API_SERVER_KEY` dibuat acak jika belum ada, diwariskan dalam proses dan
   tidak ditulis ke atau dibaca dari `.env`. Resolver tidak mencetak secret.
6. `_active_gateway_providers()` dan seluruh pembacaan DB internal 9Router
   dihapus. Tidak diperlukan compatibility fallback. API discovery existing
   tetap memakai verified source dan timestamp freshness; state provider aktif
   dan alias tidak dapat menaikkan katalog `unknown` menjadi `available`.

## Regresi dan bukti eksekusi

| Gate | Hasil |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest -q` | 269 PASS, 5 SKIP, 90,81 detik |
| `npm.cmd test` | 57 PASS, 9 file |
| `npx.cmd tsc --noEmit` | PASS |
| `npm.cmd run build` | PASS |
| `npm.cmd run test:e2e` | 14 PASS, 2,4 menit; termasuk axe, tema dan mobile/tablet |
| Combined launcher `-CheckOnly -NoBrowser -SkipInstall -SkipBuild` | PASS; native Hermes compatible, confinement verified, tanpa inference |
| Runtime `-CheckOnly -Port 8649` dengan runtime/gateway env override | PASS; tanpa inference |
| Launcher tests: shared random auth, runtime failure, seluruh missing endpoint production, override, check-only dan secret output | 17 PASS dalam pytest |
| `git diff --check` | PASS |
| `git grep` literal port/default pada `packages services scripts` | Hanya defaults di `packages/config.py` |

Vitest menguji mode baru, selector B/canvas B, historical A tetap A setelah
pilihan B/URL berbeda, completion run baru, pending idle, completion Bench tanpa
snapshot refresh, stream terfragmentasi, ID ambigu dan stream tanpa completion.
Backend menguji JSON/SSE completion yang identik dengan record snapshot,
persistence failure, default centralized, production fail closed, endpoint
normalization, allowlist environment, secret output, dan discovery tanpa SQLite.
Playwright memakai API/Core/SQLite aktual dengan runtime double terisolasi.

## Hardcode residual yang dipertahankan

- Loopback allowlist dan host bind native Hermes merupakan batas confinement.
  Tidak diubah menjadi konfigurasi jaringan bebas.
- `packages/config.py`: default development Studio 8710, runtime 8642,
  gateway 20128/v1. Ini satu-satunya definition default pada kode aplikasi.
- `.env.example`, README dan dokumentasi: contoh endpoint lokal yang eksplisit.
- `tests/`: URL/port fixture dan skenario negatif; test live existing juga masih
  menggunakan endpoint loopback eksplisit. Bukan default aplikasi production.
- Playwright/test server: port 8711 terisolasi dari Studio pengguna.

## Limitations dan gate berikutnya

- Lima live test di-skip karena runtime auth/live opt-in tidak tersedia. Tidak
  ada inference provider berbayar atau klaim model live lulus. Model catalog-only
  tetap diblokir sampai API memberikan evidence availability yang valid.
- Studio tetap aplikasi development loopback, bukan autentikasi/deployment
  production. Validasi `ARYN_ENV=production` membuktikan fail closed konfigurasi,
  bukan dukungan deployment production.
- Trace runtime per-node belum tersedia; audit Core tetap ditampilkan. Katalog
  provider aktif tanpa evidence tidak boleh dijadikan availability authoritative.
- Resolver launcher memerlukan Python dengan dependency konfigurasi (Pydantic)
  tersedia; pada repository ini virtual environment sudah tersedia.
- Warnings existing: deprecation Starlette/httpx, Alembic path separator, dan
  JS bundle Vite >500 kB. Tidak ada dependency/config yang diubah untuk menutupinya.

Berhenti setelah commit development untuk audit final dan UAT: periksa mode
baru/historis, run A/B, completion Bench/URL, production missing endpoint,
readiness gateway dan secret boundary. Jangan mulai Batch 2 otomatis.
