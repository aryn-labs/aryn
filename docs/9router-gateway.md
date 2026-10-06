# ARYN: Hermes runtime, gateway model 9Router

Audit dan implementasi pada branch `development`, mulai dari
`c3dbd87368bbf9c22293b409ffd2ff84861fbc6d`. Tidak ada perubahan pada `main`,
Batch 2, Brief/Relay, instalasi/config provider 9Router, atau hardening Hermes.

## Akar masalah

1. Studio memakai katalog/default Nous statis. Kehadiran model pada daftar
   tersebut tidak membuktikan model dapat dijalankan. Router lama juga memiliki
   interface credential provider dan konfigurasi fallback.
2. Adapter membaca autentikasi dari `.env` Hermes, yang bisa berisi credential
   provider. Readiness runtime dan model belum dipisahkan dari gateway baru.
3. Hermes OpenAI-compatible endpoint dapat mengembalikan model yang diminta
   sebagai metadata response. Echo tersebut bukan bukti model aktual provider.
4. Run tersimpan belum memiliki field gateway, backend runtime, provider aktual,
   dan actual model terpisah. Metadata historis tidak boleh dikarang saat migrasi.

## Arsitektur dan batas credential

**Studio → ARYN API → Core → HermesRuntimeAdapter → Hermes native API/AIAgent
→ transport 9Router → provider.** Hermes tetap execution engine. ARYN tidak
melakukan inference sendiri dan tidak membaca/mengelola provider API key.

`services/runtime/hermes_9router.py` mengikat native `APIServerAdapter` dan
`AIAgent` dari instalasi Hermes yang ada. Model dan parameter berasal dari versi
Core, toolset harus sudah kosong, dan semua panggilan SDK memakai endpoint
gateway yang ditentukan. `.env` loader Hermes dinonaktifkan pada proses khusus
ini; file instalasi dan konfigurasi Hermes tidak diubah. Bootstrap menghapus
environment bernama `*_API_KEY` selain key 9Router tanpa membaca nilainya.

Transport membuang header SDK/config, lalu menyertakan hanya gateway auth
opsional. SDK Hermes menggunakan sentinel publik, sehingga credential gateway
asli hanya diketahui transport. Response upstream disaring sebelum masuk
Hermes: error body, credential, tool calls, response model berbeda, completion
tidak lengkap, dan usage inkonsisten ditolak. Rejection dilatch per turn untuk
mencegah retry/fallback melakukan panggilan model tambahan.

Receipt per request menangkap `requested_model`, `actual_model`, gateway,
backend, dan provider jika dilaporkan. Native Hermes API meneruskan receipt
terverifikasi sebagai `aryn` evidence. Worker thread mendapatkan receipt secara
eksplisit; request bersamaan tidak berbagi evidence. Run asynchronous menyimpan
receipt pada native durable run status. Core dan Bench tetap memverifikasi exact
model; echo-only response dari runtime lama ditolak.

Native `/aryn/gateway` membutuhkan runtime auth dan melaporkan binding endpoint
serta enforcement. Hermes lama yang belum memakai launcher ini gagal pada gate
binding. Browser hanya memanggil API Studio; CSP `connect-src 'self'` tetap aktif.

## Discovery dan fail closed

ARYN server membaca **GET `${ARYN_9ROUTER_BASE_URL}/models`**. Tidak ada katalog
Nous/default model di Studio. Response disaring menjadi `model_id`,
`display_name`, `gateway=9Router`, availability dan alasan. Kegagalan discovery
menghapus snapshot lama; model substitusi/fallback tidak digunakan. Combo dan
route non-LLM ditolak untuk governed execution.

Endpoint resmi 9Router bisa menghasilkan daftar dari tabel/default ketika
provider discovery tidak tersedia. Karena itu listing saja berstatus `unknown`.
`available` membutuhkan evidence eksplisit: `availability_verified=true`, source
`provider_discovery` atau `runtime_probe`, serta `availability_checked_at` berupa
Unix seconds dengan umur 0–60 detik. Tidak ada endpoint pemberian evidence dari
browser. Penolakan model oleh provider dilatch `unavailable` selama proses API
berjalan. Preflight selalu menyegarkan discovery; cache listing bukan izin run.

Residual pre-Batch-2 (7 Oktober 2026): pembacaan `_active_gateway_providers()`
terhadap database internal 9Router telah dihapus. `providerConnections.isActive`
dan alias provider bukan public contract dan bukan bukti exact-model availability.
ARYN tidak membaca database tersebut untuk credential atau availability.
Discovery API existing tetap digunakan; tidak ada probe/fallback/katalog yang
direka. Katalog tanpa evidence availability yang memenuhi pemeriksaan di atas
tetap `unknown` dan gagal pada preflight Bench/Run. Instalasi yang sebelumnya
dianggap tersedia hanya dari state provider lokal kini akan diblokir. Ini tidak
mengubah instalasi/config 9Router atau exact-model enforcement.

Seluruh default endpoint development didefinisikan hanya di `packages/config.py`.
`GatewaySettings` mengambil settings tersebut dan tidak membaca environment/default
sendiri. Ketiga launcher memakai resolver terpusat; non-development tanpa
konfigurasi endpoint lengkap ditolak sebelum start. `API_SERVER_KEY` tetap
process-only, acak jika belum ada, diwariskan ke Runtime/Studio, dan diabaikan
saat membaca `.env`. Lihat [hasil regresi residual](pre-batch2-residual-validation.md).

Pemeriksaan lokal read-only tanggal 6 Oktober 2026 menghasilkan gateway
terhubung, discovery valid, **49 kandidat, semuanya `unknown`**. Versi 9Router
lokal tidak memberi evidence readiness yang dibutuhkan pada `/v1/models`.
**Bench/Run live tetap diblokir.** Ini bukan PASS inference live. Tidak ada
inference probe berbayar, bypass availability, atau perubahan konfigurasi provider.

Readiness dipisah menjadi API Studio, ARYN Runtime, gateway, binding runtime ke
gateway, dan selected model. Bench memeriksa dependency sebelum empat skenario;
unavailable/unknown menghasilkan nol dispatch. Semantics evidence tetap:
4/4 verified = Lulus; gagal/skor <100% = Gagal; passing unverified = Tidak
Terverifikasi. Historical evaluation tetap tersedia untuk dibaca.

## Kontrak dan data

- Workspace API menyediakan `gateway`: koneksi, validitas discovery, reason dan
  `runtime_binding_verified`; daftar model berasal dari discovery server.
- RunResult menambah `requested_model`, `actual_model`, `gateway`,
  `runtime_backend`, `provider`. Audit completion menyimpan metadata yang sama
  beserta token dan Core run ID. Raw runtime response tidak diekspos.
- Migrasi `009_gateway_provenance` menambah nullable `actual_model`, `gateway`,
  `runtime_backend`, `actual_provider` pada `run_states`. Model existing tetap
  requested model. Data lama tidak dibackfill dengan provenance buatan.
- Hash/version, signature Bench, approval, publikasi, assignment, budget,
  atomic idempotency claim, ownership dan recovery tetap memakai Core existing.
- API menolak input yang mengandung credential runtime/gateway yang diketahui,
  termasuk JSON escaped. Error, discovery, metadata, dan response runtime
  disanitasi; credential tidak dimasukkan ke audit/DB/frontend/log aplikasi.

## Environment dan menjalankan aplikasi

`.env.example` hanya berisi:

```dotenv
ARYN_ENV=development
ARYN_9ROUTER_BASE_URL=http://127.0.0.1:20128/v1
ARYN_9ROUTER_API_KEY=
```

Environment dibaca server-side, bukan otomatis dari `.env`. Gateway key boleh
kosong jika 9Router tidak memerlukan auth. Jika diperlukan, berikan melalui
environment server; jangan memasukkannya ke frontend, database, Git atau log.
`API_SERVER_KEY` adalah auth **runtime**, terpisah dari provider/gateway key.
Launcher membuat key runtime acak sementara jika belum ada, tanpa menampilkan
atau menyimpannya. Launcher `start-aryn.ps1` memulai runtime dan Studio dalam satu proses PowerShell induk agar keduanya menerima autentikasi yang sama.

1. Jalankan instalasi 9Router yang sudah ada; jika belum aktif, `9router
   --no-browser` dari terminal tersendiri. Jangan ubah provider/config key.
2. Hentikan Studio lama melalui launcher existing. Hentikan Hermes lama melalui
   mekanisme yang digunakan untuk menjalankannya, bila masih memakai port 8642.
   Launcher baru menolak port terpakai dan tidak membunuh proses lain otomatis.
3. Jalankan launcher bersama:

```powershell
Set-Location D:\ARYN\aryn-labs\aryn
$env:ARYN_ENV = 'development'
$env:ARYN_9ROUTER_BASE_URL = 'http://127.0.0.1:20128/v1'
# ARYN_9ROUTER_API_KEY kosong untuk instalasi gateway tanpa auth.
.\scripts\start-runtime-9router.ps1 -CheckOnly
.\scripts\start-aryn.ps1
```

Runtime berjalan loopback 8642; Studio http://127.0.0.1:8710. Launcher runtime
memverifikasi kompatibilitas/confinement, menggunakan interpreter instalasi
Hermes, menjalankan background tersembunyi dan mengecek binding sebelum menyatakan
siap. Jika kebijakan PowerShell memblokir script, buka satu sesi dengan
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-aryn.ps1`.
Menjalankan runtime dan Studio melalui dua proses PowerShell terpisah dapat
kehilangan runtime auth sementara; Studio akan menampilkan alasan autentikasi
yang belum dikonfigurasi atau ditolak. UI memakai nama Model Gateway; identitas
9Router tetap tercatat pada kontrak dan dokumentasi teknis.

```powershell
.\scripts\stop-studio.ps1
.\scripts\stop-runtime-9router.ps1
```

Stop runtime hanya menargetkan PID/start time/command milik launcher. Penghentian
proses bukan bukti cancel berhasil; Core recovery tetap mencatat outcome unknown.
Runtime/Studio yang sedang berjalan saat audit tidak diganti atau dimatikan.

## Validasi otomatis

Semua model call otomatis memakai test double. Uji instalasi Hermes memakai
native engine dan HTTP SDK double dalam subprocess dengan HOME/config terisolasi;
tidak menggunakan database konfigurasi provider pengguna.

Hasil final yang benar-benar dijalankan:

| Gate | Hasil |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest -q` | **217 PASS, 5 SKIP**, 45,27 detik |
| Vitest pada file khusus commit | **33/33 PASS**, 6 file |
| Vitest working tree, termasuk test popup pengguna | **34/34 PASS** |
| `npx tsc --noEmit` dan `npm run build` | **PASS** |
| Playwright pada salinan khusus commit | **14/14 PASS**, 2,3 menit |
| axe seluruh halaman, dark/light, mobile/tablet, reduced motion | **PASS**, dalam Playwright |
| Native Hermes + SDK double: direct, concurrency, async durable evidence, mismatch, secret rejection | **PASS**, dalam pytest |
| Runtime launcher `-CheckOnly`, tanpa inference | **PASS** pada instalasi lokal |
| SQLite migration, foreign-key/integrity checks; PostgreSQL SQL offline | **PASS**, dalam pytest |
| Discovery/readiness, exact model, API/audit/DB/log secret leakage, no browser runtime access | **PASS**, dalam regression suites |

5 SKIP: tiga model-live test membutuhkan opt-in pemilik; dua pemeriksaan runtime
live memerlukan auth yang tidak tersedia pada environment sesi audit. Opt-in
membutuhkan `ARYN_RUN_LIVE_MODEL_TESTS=1` serta `ARYN_LIVE_MODEL` eksplisit;
variabel tersebut tidak ditambahkan ke contoh environment dan tidak diaktifkan
saat audit. Tidak ada default model pada test live.

Vitest/build/Playwright juga dijalankan pada salinan source khusus commit di
`.local/gateway-verification-0b6e00b8`, menggunakan Core/API/test database asli
repository dan runtime double. Salinan mengecualikan perubahan UI pengguna yang
belum di-commit; working tree pengguna tidak ditimpa. Satu assertion drag awal
membandingkan seluruh inline style dan gagal karena React Flow berpindah dari
hidden ke visible saat init. Tes diperbaiki agar menunggu node visible lalu
membandingkan transform node; pemeriksaan drag/connection read-only tetap aktif.

Warnings tersisa: deprecation Starlette/httpx, konfigurasi Alembic path separator,
dan ukuran JS bundle Vite >500 kB. Tidak ada error gate. Tidak ada perubahan
package/dependency untuk menyembunyikan warnings tersebut.

Bukti Playwright khusus commit: `.local/gateway-verification-0b6e00b8/apps/web/playwright-report`.
Command standar tetap sama dengan bagian pengujian pada `docs/studio.md`.

Referensi primary source yang diaudit:
[Hermes native API](https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server.py),
[konfigurasi model Hermes](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/configuring-models.md),
[9Router models endpoint](https://raw.githubusercontent.com/decolua/9router/master/src/app/api/v1/models/route.js).
Implementasi disesuaikan juga dengan source instalasi Hermes dan 9Router lokal.

## Tindak lanjut UAT: label dan autentikasi runtime (6 Oktober 2026)

UI memakai nama **Model Gateway** pada topbar, Pengaturan, canvas, dan pesan
kegagalan. Identitas 9Router tetap benar pada metadata run/kontrak dan dokumentasi
teknis. Tidak ada perubahan routing, schema, governance, atau credential boundary.

Saat pemeriksaan awal, proses Hermes hidup dan `/health` merespons, tetapi
readiness/binding ARYN belum terverifikasi. Launcher terpisah dapat kehilangan
`API_SERVER_KEY` sementara ketika dipanggil melalui proses PowerShell berbeda.
`start-aryn.ps1` memulai kedua layanan dari induk yang sama. API membedakan
`runtime_authentication_missing` dan `runtime_authentication_rejected`, tanpa
menampilkan key; runtime yang sehat tetapi belum terautentikasi tidak diklaim siap.

Sesudah pemeriksaan nol run aktif, layanan milik launcher dimulai ulang bersama.
Workspace aktual menunjukkan `runtime.ready=true`, `tools_confined=true`, seluruh
toolset nonaktif, serta binding gateway terverifikasi. Database lokal tetap
tersimpan: `PRAGMA integrity_check=ok`, nol pelanggaran foreign key. Endpoint
model gateway `/v1/models` kemudian timeout; katalog kosong dan Bench/Run tetap
fail closed. Runtime siap tidak dijadikan bukti bahwa gateway/model tersedia.

Regresi native Hermes awal menemukan probe metadata yang belum terisolasi dari
jaringan. Test kini memakai HTTP double untuk probe metadata dan SDK model,
serta memblokir socket keluar; pengecualian hanya socketpair internal asyncio
Windows. Penamaan sesi otomatis Hermes dapat mengirim request model tambahan;
jalur tersebut dinonaktifkan hanya pada proses khusus ARYN, tanpa mengubah
instalasi atau konfigurasi Hermes. Native integration tetap memeriksa exact model,
concurrency, evidence durable async, penolakan mismatch/secret dan jumlah panggilan.

Validasi akhir: backend **221 PASS, 5 SKIP** (54,40 detik); Vitest source khusus
commit **34 PASS**, working tree **35 PASS** termasuk popup pengguna; TypeScript
check dan production build **PASS**; Playwright/axe **14 PASS** (2,8 menit).
Test launcher memeriksa autentikasi sementara bersama, penerusan opsi, dan bahwa
Studio tidak dimulai setelah runtime gagal. Tidak ada inference live yang diklaim
PASS. Tidak ada push/merge ke main atau perluasan Batch 2.

## Residual limitation dan satu sesi UAT

- Inference provider live belum diuji dan tidak diklaim lulus. Current catalog
  unknown memblokir Bench/Run sampai ada evidence readiness authoritative.
- Prefix/alias 9Router bisa berbeda dengan canonical model response provider.
  ARYN sengaja menolak perbedaan tersebut; tidak melakukan normalisasi atau
  menyembunyikan fallback. Provider yang tidak melaporkan actual model ditolak.
- Bukti bergantung pada laporan model gateway/provider. Tidak dapat membuktikan
  identitas model bila gateway/provider mengembalikan metadata palsu.
- Binding memakai API internal native Hermes; upgrade Hermes perlu compatibility
  check dan regression native integration. Tidak ada trace runtime terstruktur
  untuk direct turn; audit Core tetap tersedia.
- Schema SQLite upgrade dan SQL PostgreSQL diuji; tidak ada integrasi PostgreSQL
  Cloud/live database. Stop/restart masih bisa menghasilkan outcome unknown
  untuk inference yang sudah diterima provider, tanpa retry otomatis.

UAT bersama: periksa runtime/gateway secara terpisah di Pengaturan, lihat katalog
aktual di Factory, pastikan unknown/unavailable memblokir Bench dan Run, serta
buka historical evaluation/run dan audit tanpa kehilangan data. Lifecycle live
passing sampai publikasi membutuhkan readiness evidence yang valid dan izin
inference eksplisit; jangan meluluskan gate hanya untuk mencoba UI. Setelah
commit batch ini berhenti untuk audit/UAT, tanpa otomatis memulai Batch 2.

## File dalam perubahan gateway

File existing Inspector hanya menyertakan nomenklatur dan metadata gateway.
Perubahan lokal pengguna pada full-text Inspector, CSS, dan test popup dipertahankan
dan tidak dimasukkan dalam commit ini.

- `.env.example`
- `README.md`
- `apps/web/e2e/studio.spec.ts`
- `apps/web/src/components/agent-flow.tsx`
- `apps/web/src/components/canvas/canvas-builders.ts`
- `apps/web/src/components/canvas/canvas-inspector.tsx`
- `apps/web/src/components/shared.tsx`
- `apps/web/src/components/version-form.tsx`
- `apps/web/src/features/factory.tsx`
- `apps/web/src/features/overview.tsx`
- `apps/web/src/features/runs.tsx`
- `apps/web/src/features/settings.tsx`
- `apps/web/src/lib/studio-state.ts`
- `apps/web/src/lib/types.ts`
- `apps/web/src/studio.tsx`
- `apps/web/src/test/gateway-readiness.test.tsx`
- `apps/web/src/test/studio-context.test.tsx`
- `apps/web/src/test/studio-fixtures.ts`
- `database/migrations/versions/009_gateway_provenance.py`
- `database/schema.py`
- `docs/9router-gateway.md`
- `docs/studio.md`
- `modules/core/workflows/coordinator.py`
- `packages/contracts/model.py`
- `packages/contracts/runtime.py`
- `packages/model_adapters/providers/gemini.py`
- `packages/model_adapters/providers/nous.py`
- `packages/model_adapters/router.py`
- `packages/model_adapters/gateway.py`
- `packages/runtime_adapters/hermes/adapter.py`
- `scripts/hermes-9router.py`
- `scripts/start-runtime-9router.ps1`
- `scripts/stop-runtime-9router.ps1`
- `services/api/studio.py`
- `services/runtime/__init__.py`
- `services/runtime/gateway_transport.py`
- `services/runtime/hermes_9router.py`
- `tests/e2e/test_smoke_end_to_end.py`
- `tests/gateway_fixtures.py`
- `tests/hermes_gateway_check.py`
- `tests/integration/test_9router_studio.py`
- `tests/integration/test_agent_lifecycle_workflow.py`
- `tests/integration/test_schema_migration_compatibility.py`
- `tests/integration/test_hermes_9router_binding.py`
- `tests/integration/test_hermes_adapter_integration.py`
- `tests/integration/test_studio_api.py`
- `tests/live_gateway.py`
- `tests/security/test_9router_boundary.py`
- `tests/security/test_9router_discovery.py`
- `tests/security/test_9router_exact_model.py`
- `tests/security/test_runtime_provenance_verification.py`
- `tests/security/test_hermes_security_gates.py`
- `tests/security/test_uat_model_availability.py`
- `tests/studio_runtime.py`
- `tests/unit/test_gemini_status_audit.py`
- `tests/unit/test_model_router.py`
