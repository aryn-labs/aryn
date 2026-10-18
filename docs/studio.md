# ARYN Studio — pengujian lokal

ARYN Studio berada di `apps/web`; API aplikasi berada di `services/api`. Implementasi memakai React, TypeScript, Tailwind CSS, pola komponen shadcn/ui berbasis Radix, Lucide, dan FastAPI. Factory, Bench, identity, permission, approval, budget, dan audit tetap menggunakan layanan repository yang ada.

Authentication memerlukan mode eksplisit. Launcher di bawah khusus `ARYN_ENV=development` / `ARYN_AUTH_MODE=local-development`; production menolak development bootstrap. Hosted memakai OIDC Authorization Code + PKCE, provisioned issuer/subject mapping, server sessions dan membership Core yang sama. Lihat [konfigurasi/trust boundary deployment](deployment-security.md) dan [validasi aktual](https://github.com/aryn-labs/aryn/blob/31491840dfbcadbb6ebc852a41ec0f64ee31aa73/docs/deployment-validation.md). Real hosted IdP/TLS/PostgreSQL/network deployment belum diverifikasi.

## Menjalankan di Windows PowerShell

Gunakan versi Python/Node dalam `.python-version` dan `.node-version`.
Hermes dan 9Router harus tersedia secara terpisah; memulai layanan tidak
memberikan izin inferensi berbayar. Dari repository:

```powershell
Set-Location D:\ARYN\aryn-labs\aryn
.\scripts\start-aryn.ps1
```

Launcher membuat `.venv` bila perlu, memasang dependensi Python/frontend,
membangun frontend, menjalankan runtime dan API di `127.0.0.1:8710`, lalu membuka
browser. Untuk reproduksi dependensi terkunci, gunakan perintah setup pada README
repository sebelum launcher dengan `-SkipInstall`. Jika eksekusi skrip dibatasi
oleh kebijakan PowerShell, gunakan proses sekali jalan tanpa mengubah kebijakan mesin:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-aryn.ps1
```

Buka **http://127.0.0.1:8710**. Setelah instalasi awal, gunakan `-SkipInstall -SkipBuild` untuk menjalankan hasil build yang sudah ada. `-NoBrowser` menonaktifkan pembukaan browser. Launcher bersama meneruskan autentikasi runtime sementara ke API tanpa menyimpan key. Jika menjalankan API secara terpisah, `start-studio.ps1 -Port 8712` memakai port loopback lain dan memerlukan environment autentikasi runtime yang sama. Launcher menolak port yang dipakai proses lain. Hentikan dengan:

```powershell
.\scripts\stop-studio.ps1
.\scripts\stop-runtime-9router.ps1
```

API dapat dijalankan di terminal secara langsung setelah build:

```powershell
.\.venv\Scripts\python.exe -m services.api --port 8710
```

`apps/web` menyediakan mode Vite untuk pengembangan tampilan; operasi terpadu dan pengujian pengguna menggunakan build yang dilayani FastAPI pada origin yang sama. Tidak diperlukan layanan publik, proxy Hermes dari browser, atau konfigurasi CORS permisif.

## Factory dan execution

Bench membedakan hasil **Lulus**, **Gagal**, dan **Tidak Terverifikasi**.
Hasil historis tetap disimpan; hanya evidence lulus yang terverifikasi dapat
dipakai untuk approval/publish. Kesiapan gateway tidak menjamin availability
model: Bench/Run memerlukan pemeriksaan model oleh runtime. Model unavailable
atau availability unknown diblokir dengan alasan yang terlihat di Studio.
Lihat [laporan UAT Bench/model](https://github.com/aryn-labs/aryn/blob/31491840dfbcadbb6ebc852a41ec0f64ee31aa73/docs/uat-bench-model-validation.md) untuk bukti
pengujian dan bukti historis sebelum migrasi gateway; perilaku gateway terbaru dijelaskan pada panduan 9Router.

1. Buka **Agent Factory**, buat blueprint, lalu simpan versi. Blueprint dan versi merupakan data berbeda. Versi baru tidak menimpa konfigurasi lama.
2. Pilih model yang terdaftar, instruksi, skills/content pins, grants dan execution environment yang tersedia. Skill text tidak memberikan permission. Temperature dan batas output diteruskan ke adapter. Native execution memerlukan trusted worker dan exact-action approval Core.
3. Jalankan **Bench**. Dialog mengungkap penggunaan penyedia model jarak jauh melalui Hermes dan memerlukan pilihan eksplisit pengguna. Suite ditentukan oleh evaluation reference versi agent; Research Safety default berisi empat skenario. Request browser tidak dapat mengganti skenario atau menyuntikkan skor.
4. Buka setiap hasil skenario untuk melihat respons aktual, model, token, durasi, dan alasan kegagalan. Skor harus 100%; kegagalan terakhir membatalkan kelayakan hasil lama.
5. **Tinjau dan setujui** dengan catatan keputusan. Core mengikat approval ke SHA-256 konfigurasi aktual, organisasi/proyek, serta evaluation ID Bench terverifikasi. Hash dari tinjauan browser harus cocok dengan database. Persetujuan memerlukan operator manusia aktif dengan permission Core yang sesuai.
6. **Publikasikan versi**. Core memeriksa evaluasi dan approval. Versi yang dipublikasikan tidak dapat diubah.
7. Buka **Penugasan**, beri peran dalam proyek aktif. Versi harus dipublikasikan dan blueprint harus cocok dengan induk versi. Penugasan tidak memindahkan blueprint antarproyek.
8. Buka **Eksekusi**, isi instruksi riset dan konfirmasikan pengiriman ke model pilihan. Core memeriksa izin, penugasan, model, dan preflight budget sebelum Hermes.
9. Lihat output asli, model aktual, status, token input/output/total, hasil tersimpan, serta audit Core. Refresh halaman mempertahankan data. Request duplikat dengan kunci yang sama tidak mengeksekusi ulang; kunci yang dipakai untuk input lain ditolak.

## Keamanan dan ruang lingkup

Alur operasional: **Web → ARYN API → ARYN Core → Hermes Runtime Adapter → Hermes → 9Router → provider**. Bench menggunakan generic engine melalui Factory. Lihat [kontrak dan validasi Bench](https://github.com/aryn-labs/aryn-docs/blob/e826deba288803d8d52d51e176be5e4d8ab0fd04/engineering/aryn/bench-engine.md). Hermes utama memakai home terpisah dan hanya mengusulkan declared tools kepada Core. Toolset discovery tidak memberikan grant atau mengaktifkan host execution.

Trusted operator dapat mengikat immutable native worker manifest melalui
`-NativeWorkerManifest` pada launcher atau `--native-worker-manifest` pada API.
Tanpa manifest, native execution tetap unavailable. Lima handler terminal/filesystem
native dapat berjalan dalam container per-run setelah exact-action human approval,
validasi grants, owner, budget dan deadline Core. Container tidak mendapat host
mount, network atau credential. Lihat [runtime control plane dan capability matrix](https://github.com/aryn-labs/aryn-docs/blob/e826deba288803d8d52d51e176be5e4d8ab0fd04/engineering/aryn/runtime-control-plane.md)
untuk batas execution dan blocker upstream yang tetap berlaku.

Pada Local development, API mendengarkan loopback. Host harus cocok dengan alamat launcher; permintaan dari IP lain atau forwarded proxy headers ditolak. Tidak ada endpoint penerbitan identity binding untuk browser. Server memiliki signing key acak per proses dan membuat konteks Core untuk principal development tetap yang diprovisikan pada organisasi/proyek lokal. Keanggotaan tersimpan pada DB; restart tidak mengembalikan membership yang dicabut. Hosted memerlukan verified OIDC dan current server session sebelum Core context dibuat; proxy loopback bukan identity, dan tidak ada provisioning development admin.

Sesi lokal memakai cookie acak HttpOnly/SameSite Strict dengan expiry delapan jam. Semua endpoint API setelah bootstrap memerlukan sesi. Mutasi memerlukan origin yang tepat dan token CSRF sesi. Input identity/roles/security context dari browser tidak diterima. CSP membatasi koneksi ke origin Studio dan memblokir framing. Ini akses development untuk komputer lokal tepercaya, **bukan autentikasi produksi**; proses lokal yang sudah memiliki akses mesin berada di luar batas ini.

Autentikasi runtime memakai environment server `API_SERVER_KEY`; launcher membuat
key sementara jika belum diberikan. ARYN tidak memindai `.env` Hermes atau membaca
provider API key. `ARYN_9ROUTER_BASE_URL` dan `ARYN_9ROUTER_API_KEY` adalah bootstrap
gateway; credential provider dikelola 9Router. Settings mendukung penggantian/revokasi
key gateway yang write-only melalui authenticated Core/CSRF routes pada binding lokal
yang memenuhi policy. Key tersimpan dalam trusted process memory, tidak dipersistenkan
plaintext atau dikirim kembali ke browser. Hosted multi-user masih memerlukan trusted
persistent credential provider dan tenant-isolated bindings. Perubahan koneksi
membatalkan catalog/readiness/evidence yang tidak cocok. Respons model tetap teks tidak
tepercaya; error runtime disanitasi. Lihat [lifecycle gateway](https://github.com/aryn-labs/aryn-docs/blob/e826deba288803d8d52d51e176be5e4d8ab0fd04/engineering/aryn/runtime-control-plane.md#credentials-and-configuration-lifecycle).

Database Local Studio: `.local/studio.sqlite3`, diabaikan Git; hosted memerlukan
explicit `ARYN_DATABASE_URL` serta pemisahan migration owner/application writer.
Seluruh 24 migrasi historis dipertahankan, termasuk identity, signed history,
execution ownership, workspaces, workflows, automations dan chat. Tidak ada approval
atau hosted membership yang direka migration. Recovery memerlukan single execution
authority: leftover runs menjadi `outcome_unknown`. Engine lama yang kehilangan
authority tetap fenced; replacement harus memperoleh authority sendiri. Versi
evaluating milik owner hidup tidak diubah; interrupted prior-owner evaluation tetap
rejected dan dapat dievaluasi kembali.

Hash konfigurasi dihitung ulang dari data aktual; bukti Bench dan approval memakai attestation internal. Key SQLite persistent tersimpan pada `.local/studio.aryn-evidence.key` dan diabaikan Git. Backup key bersama database; kehilangan atau pergantian key membuat bukti lama tidak lagi terverifikasi. Versi dengan format hash lama dan bukti tanpa attestation tetap tersedia sebagai riwayat tetapi diblokir dari lifecycle baru; buat versi baru lalu jalankan Bench dan approval. Migrasi tidak menandatangani ulang bukti lama secara otomatis.

Suite final `research-safety-1.2.0` menambahkan pengenalan penolakan dalam Bahasa Indonesia, kontraksi Inggris, dan abstensi tanggal tidak valid. Pola injection/host tetap ditolak; angka pendapatan fiktif berprefiks `$` dan `Rp` ditolak. Suite regex ini merupakan gate riset awal, bukan pembuktian keamanan lengkap atau penilaian mutu ilmiah. Hasil lama dipertahankan dengan versi evaluator masing-masing.

## Antarmuka dan batas implementasi

Canvas Factory merupakan workspace arsitektur dengan tata letak sementara.
Konfigurasi versi tersimpan selalu hanya baca. **Rancang Versi Baru** di inspector
membuka draft lokal; Save memakai API create-version existing dan tidak menimpa
versi sumber. Execution/Bench adalah canvas hanya baca dengan pan, zoom,
selection dan inspector. Run historis memakai assignment/version miliknya;
pilihan form eksekusi baru dan status pending dipisahkan dari histori.
`/runs` tanpa `hasil` membuka **NEW EXECUTION**: canvas mengikuti published
agent/version yang dipilih, Inspector berisi assignment/inline assignment,
prompt, consent, dan Run. Tidak ada output historis; node/edge idle sampai
event aktual diterima. `?hasil=<run_id>` membuka **HISTORICAL RUN** dengan
Inspector DETAIL / OUTPUT / TRACE dan konfigurasi historis hanya baca.
Gunakan **Eksekusi baru** untuk kembali ke form. Run selesai mengarahkan URL
ke `?hasil=<new_run_id>`.
Tidak ada trace per-node atau animasi tahap eksekusi yang direka.

Completion Bench JSON dan SSE memakai `evaluation_id`, `version_id`, dan
`evaluation` tersimpan dengan `verified` dari verifikasi server. Event
`bench.completed` baru diterbitkan setelah penyimpanan; frontend memilih
hasil tersebut langsung dan menyelaraskan `/bench?versi=...&evaluasi=...`
tanpa harus menunggu snapshot refresh.

`packages/config.py` menjadi source of truth environment, endpoint Studio,
runtime, dan gateway beserta auth gateway. Semua launcher memakai resolver
ini melalui `scripts/aryn-config.ps1`. Default loopback hanya untuk development;
environment lain wajib mengisi seluruh endpoint. `API_SERVER_KEY` diwariskan
melalui environment proses, dibuat acak jika belum ada, dan tidak dibaca dari
atau ditulis ke `.env`. Ketiga launcher menyediakan `-CheckOnly`; launcher
gabungan memeriksa kompatibilitas Hermes dan konfigurasi Studio tanpa start
layanan atau inference. Dependency Python konfigurasi harus tersedia agar
resolver dapat berjalan. Lihat [validasi residual pre-Batch-2](https://github.com/aryn-labs/aryn/blob/31491840dfbcadbb6ebc852a41ec0f64ee31aa73/docs/pre-batch2-residual-validation.md).

Jumlah “Perlu ditinjau” hanya menghitung draft dengan integrity valid dan
Bench eligible. Approved mempunyai state sudah disetujui/siap publikasi;
published tetap menjadi histori. Warna skor Bench dan provider mengikuti
evidence/backend: verified pass hijau, gagal merah, unverified/unknown amber.
Lihat [audit dan stabilisasi canvas](https://github.com/aryn-labs/aryn/blob/31491840dfbcadbb6ebc852a41ec0f64ee31aa73/docs/studio-canvas-stabilization.md) untuk akar
masalah, matriks regression/accessibility, residual limitation dan satu sesi UAT.

Ringkasan menampilkan jumlah aktual dari proyek dan aktivitas Core; tidak ada seed agent, riwayat, atau statistik buatan. Agent Factory, Eksekusi, Bench, Persetujuan, Tata Kelola, dan Pengaturan aktif. Workspace/project selector memakai proyek nyata yang dapat dibaca principal. UI berbahasa Indonesia, dengan semantic tokens dark/light, font Geist/Geist Mono, sidebar collapsible, pencarian tabel, loading/error/empty/disconnected states, dialog dengan focus trap, navigasi tab keyboard, serta layout desktop/tablet/mobile.

Projects, Workflows, Runs, Automations, Chat dan Settings menggunakan scope backend
yang sama. Brief menyediakan scoped evidence; Relay membatasi recovery pada
fixture/adapter yang telah diotorisasi. Itu tidak membuktikan live infrastructure
remediation. **Belum diverifikasi/terblokir:** hosted IdP/deployment, native browser/
network, persistent memory, shared native session administration, background jobs,
subagents dan raw runtime event forwarding yang belum memenuhi Core enforcement.
Fitur native config admin tertentu unsupported pada versi terpasang. Audit/usage
yang tidak tersedia dan biaya tanpa sourced evidence tidak direka. Katalog dinamis
berasal dari 9Router; unknown availability tetap memblokir Bench/Run dan tidak ada
fallback. [Panduan 9Router](https://github.com/aryn-labs/aryn-docs/blob/e826deba288803d8d52d51e176be5e4d8ab0fd04/engineering/aryn/9router-gateway.md)
menjelaskan exact-model provenance dan blocker live compatibility.

Jika Hermes tidak tersedia, kredensial salah, atau toolsets aktif, indikator menjelaskan ketidaksiapan dan server memblokir Bench/Run. Factory dan data tersimpan tetap dapat digunakan. Detail readiness Hermes dapat degraded walaupun jalur teks dapat dipakai; Studio tidak mengklaim runtime keseluruhan bebas masalah.

Bench juga menampilkan current Accepted Baseline vs Candidate, scenario/grader regressions, score serta latency/token/cost deltas dan promotion decision dari server. Admin dapat menerima verified baseline dengan reason/CAS; suite/evidence transition memerlukan intent governance eksplisit. Critical regression memblokir Factory/Core approval dan publish backend. Publication sah memajukan baseline atomik; existing publication tanpa baseline membutuhkan adoption yang diverifikasi, sehingga candidate tidak mendapat no-baseline bypass. [Kontrak dan lifecycle baseline](https://github.com/aryn-labs/aryn-docs/blob/e826deba288803d8d52d51e176be5e4d8ab0fd04/engineering/aryn/bench-engine.md#accepted-baseline-dan-regression-governance-bn-06) menjelaskan bootstrap, history, migration dan legacy limits.

## Pengujian dan traceability

[README Web](../apps/web/README.md) memuat perintah unit, lint, build dan tujuh
suite browser yang dipelihara. Shell/Home memakai isolated HTTP contracts;
suite fitur memakai API/Core/database disposable serta explicit runtime/model
doubles. Tes tidak mengubah database pengguna. Projects mencakup populated dan
empty admin/viewer pada lima viewport/dua tema, bilingual persistence, keyboard,
permission denial dan Axe. Hasil aktual dan perintah backend/PostgreSQL/native
ada pada [repository maintenance](repository-maintenance.md).

| Persyaratan pengguna | Bukti otomatis |
| --- | --- |
| Navigasi, states, tema, responsiveness | `apps/web/e2e/shell.spec.ts`, `home.spec.ts` |
| Bagian 5: seluruh mutation/lifecycle, refresh, DB persistence, idempotency | `tests/integration/test_studio_api.py`, browser lifecycle test |
| Bagian 6: loopback, origin, CSRF, identity spoof, RBAC, tools confinement | `test_studio_api.py`, suite security yang sudah ada |
| Bagian 7: validasi, error, permission denial, keyboard, aksesibilitas | component tests, Playwright + axe, API negatives |
| Evaluator multilingual + pola penolakan berbahaya | `tests/unit/test_bench_localization.py` |
| Migrasi schema tetap mempertahankan data | `test_schema_upgrade_004_retains_data` |

Dokumen ARYN-PRD-001/ARCH/TECH/SEC privat belum tersimpan di checkout `aryn-docs`; indeksnya menyatakan NO. ID P0 privat tidak direka. Implementasi mengikuti AGENTS.md, SECURITY.md, contracts, dan perilaku Core aktual. Referensi desain yang ditinjau: [Linear refresh](https://linear.app/changelog/2026-03-12-ui-refresh), [Dify Workflow Studio](https://dify.ai/workflows), [Langfuse observability](https://langfuse.com/docs/observability/overview), [shadcn dashboard blocks](https://ui.shadcn.com/blocks?category=dashboard). Identitas, palette, layout, dan alur Studio dibuat untuk ARYN.

Hasil historis tersedia pada [validasi Studio baseline](https://github.com/aryn-labs/aryn/blob/31491840dfbcadbb6ebc852a41ec0f64ee31aa73/docs/studio-validation.md)
dan [validasi governance baseline](https://github.com/aryn-labs/aryn/blob/31491840dfbcadbb6ebc852a41ec0f64ee31aa73/docs/system-governance-validation.md).
Keduanya tidak mengesahkan perubahan cleanup sekarang. Tes model live memerlukan
izin pemilik dan opt-in eksplisit; pengujian biasa tidak mengirim prompt model live.
## Version Registry dan rollback assignment

Factory detail menyediakan Version Registry dan histori aktivasi per assignment. Known-good
ditentukan server dari exact immutable publication, Bench, baseline/comparison dan Core approval;
browser tidak dapat menetapkan flag known-good. Human admin dapat mereview rollback dari publication
aktif ke publication sebelumnya, memasukkan reason, lalu mengirim reviewed version/activation dan
idempotency key. Assignment lain serta Bench baseline tidak ikut berubah.

API registry: `GET /api/projects/{project_id}/blueprints/{blueprint_id}/registry`.
Rollback intent: `POST /api/projects/{project_id}/assignments/{assignment_id}/rollback`.
Snapshot memuat eligibility, activation history dan captured run version provenance. Historical
run tanpa durable captured identity ditampilkan unavailable; current assignment tidak dipakai
untuk menebak versi lama. Lihat [Factory contracts](https://github.com/aryn-labs/aryn-docs/blob/e826deba288803d8d52d51e176be5e4d8ab0fd04/engineering/aryn/agent-factory-contracts.md#8-version-registry-dan-known-good-rollback-af-07).

## Captured execution result contract

Run JSON/SSE/cache/history memakai persisted Core RunResult. IDs/version/payload/transition
berasal dari captured claim, termasuk rollback saat preflight await. Terminal transport event
run.completed harus dibaca bersama status: failed/cancelled/outcome_unknown bukan success.
Usage unavailable ditampilkan Tidak tersedia; cost tanpa sourced evidence tetap NULL.
Old flat token/id/session aliases tetap ada; timestamp menerima UTC epoch dan historical ISO.
Public errors membawa safe code/correlation/run IDs tanpa dependency exception text. Important
SSE events dan completion reader typed. Tidak ada visual redesign. Lihat [execution hardening](https://github.com/aryn-labs/aryn-docs/blob/e826deba288803d8d52d51e176be5e4d8ab0fd04/engineering/aryn/core-execution-hardening.md).
