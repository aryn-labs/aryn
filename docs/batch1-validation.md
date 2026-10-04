# ARYN — laporan Batch 1

Tanggal verifikasi: 5 Oktober 2026. Repository: `D:\ARYN\aryn-labs\aryn`. Branch awal dan akhir: `development`. HEAD awal benar-benar diperiksa dan cocok dengan baseline: `c0f46a189c63e5ae8a0fd28a7e883b72cd041972`. Working tree awal bersih. Commit implementasi terakhir: `8ba51ff`. Seluruh commit dibuat lokal; tidak ada push atau perubahan/merge ke `main`.

Batch ini memperkuat implementasi yang sudah ada. Batas Web → ARYN API → Core → Hermes Runtime Adapter → Hermes tetap berlaku. Desain, navigasi, warna, font, dan aset Studio dipertahankan. Perubahan UI hanya memakai komponen yang ada untuk kelayakan, kegagalan, model aktual, dan status yang benar. Brief, Relay, login produksi, integrasi Cloud, Ollama, dan konfigurasi keamanan Hermes tidak dikembangkan atau diubah.

**1. Audit awal dan akar masalah**

Audit membaca AGENTS.md, SECURITY.md, README, dokumentasi Studio, contracts agent/Bench/approval/Core/runtime, Factory, Bench runner dan quality gate, identity/permissions/approval/audit/budget/coordinator, repositories/schema/connection, migrasi 001–005, Hermes adapter, API, serta pengujian backend/frontend/E2E yang tersedia. Indeks dokumentasi privat dalam checkout `aryn-docs` menyatakan dokumen PRD/ARCH/TECH/SEC belum tersedia; ID persyaratan privat tidak direka.

Implementasi yang dipertahankan mencakup identity yang diterbitkan server, membership database, pemeriksaan izin proyek, loopback/Host/Origin/CSRF, model catalog tanpa fallback diam-diam, confinement tool, pemisahan blueprint/version/assignment, serta lifecycle E2E dengan Bench sebenarnya dan runtime double terisolasi.

| Pekerjaan | Akar masalah yang direproduksi sebelum perbaikan | Perbaikan dan hasil akhir | Status | Commit |
| --- | --- | --- | --- | --- |
| Agent Version Integrity | Hash mengabaikan metadata keamanan dan membulatkan temperature; lifecycle mempercayai stored hash tanpa menghitung ulang konfigurasi; konfigurasi published masih dapat diubah lewat ORM. Delapan pengujian negatif gagal sebelum perbaikan. | JSON kanonis format 2 mencakup konfigurasi lengkap dan parameter tepat. Hash dihitung ulang dari data tersimpan pada boundary lifecycle. Mutasi konfigurasi published/deprecated melalui ORM ditolak; korupsi raw SQL terdeteksi saat dibaca. | PASS | `61e4b93` |
| Bench Evaluation Integrity | Record passed/skor dipercaya tanpa validasi lengkap; suite kosong dapat memakai fallback; provenance tidak terautentikasi. Tujuh pengujian negatif gagal sebelum perbaikan. | Empat skenario suite wajib, suite hash/version, model aktual, runtime status, output, latency, dan usage diperiksa; skor dihitung ulang. HMAC mengikat bukti ke konfigurasi dan scope. Evaluasi gagal terbaru menggugurkan PASS lama. | PASS | `7efb6cb` |
| Approval & Publication Governance | Row approval tanpa bukti dapat dipakai; SYSTEM tidak dibatasi sebagai pemberi approval; approval tidak menunjuk evaluasi tepat dan transisi terpisah. Tiga pengujian negatif gagal sebelum perbaikan. | Hanya USER manusia berwenang dapat approve/publish; approval memerlukan membership admin aktif, sedangkan publikasi mengikuti izin admin/operator proyek yang ada. Approval bertanda tangan mengikat org/proyek/versi/hash/evaluation ID. Approval dan transisi approved disimpan atomik; publish mewajibkan state dan bukti terkini. | PASS | `f4f2900` |
| Execution Idempotency & Concurrency | Duplikat in-flight tetap menjalankan adapter, perubahan konfigurasi tidak membatalkan cache, dan retry timeout dapat dispatch ulang. Tiga pengujian negatif gagal sebelum perbaikan. Migrasi awal juga tidak memasang constraint unik yang sudah ada pada Base.metadata. | Claim unik disimpan sebelum dispatch; fingerprint mencakup input, konfigurasi, aktor, scope, dan mode. Duplikat memperoleh hasil tersimpan, Core ID yang sama untuk async, atau konflik in-progress. State/ledger/audit terminal atomik. Migrasi 008 memasang unique index pada database Alembic. | PASS | `0056c79`, tindak lanjut schema `c009905` |
| Run Ownership, Cancellation & Recovery | Get/cancel/trace meneruskan ID ke runtime sebelum membuktikan scope, cancel ditandai sukses walau runtime menolak, blueprint assignment tidak dicocokkan, dan trace/recovery dapat memberi kesan bukti yang tidak tersedia. Lima pengujian negatif gagal sebelum perbaikan. | Izin dan kepemilikan org/proyek diperiksa lebih dulu; mapping ID Core/runtime dipisahkan. Assignment aktif, blueprint, hash, Bench, dan approval diperiksa. ACK stop menjadi stopping; cancelled hanya dengan bukti terminal. Trace tidak didukung dinyatakan unavailable. Recovery menyimpan failed dengan outcome runtime unknown. | PASS | `8ba51ff` |

Status PASS di atas adalah hasil implementasi dan pengujian otomatis dalam batas runtime terisolasi. UAT bersama dan pengiriman model live belum dijalankan dan berstatus TERTUNDA (menunggu sesi pemilik); tidak menjadi bukti PASS live.

**2. Perubahan implementasi dan kontrak**

Canonical payload mencakup ID versi/blueprint, nomor versi, system prompt, model, grants terurut, temperature tanpa pembulatan, max tokens, dan seluruh metadata. JSON non-finite ditolak. Versi dengan hash lama/tidak cocok tetap tersimpan untuk riwayat tetapi tidak boleh dievaluasi, disetujui, dipublikasikan, atau dijalankan sebagai versi valid. Buat versi baru; migrasi tidak menandatangani ulang data lama secara otomatis.

Bench memakai `research-safety-1.2.0` yang sudah ada, tanpa memperlonggar pola atau skor 100%. Input API tidak menyediakan passed, skor, suite pengganti, maupun attestation. Hasil per skenario dan agregat diperiksa lagi ketika governance membaca database. Test double berada dalam `tests/studio_runtime.py` atau transport HTTP terisolasi; lifecycle utama menjalankan runner Bench lengkap, bukan insert PASS. Fixture UI untuk pengujian tampilan tidak memberi otoritas backend.

Approval harus cocok dengan evaluasi terkini yang ditunjuk versi, konfigurasi aktual, scope, dan manusia yang masih mempunyai kewenangan aktif. Perubahan konfigurasi, evaluasi baru gagal, pemalsuan row, atau perubahan authority menggugurkan kelayakan. Membuat row approval melalui engine saja tidak melewati state transition Factory.

RunRequest membatasi idempotency key menjadi string nonkosong maksimal 255 karakter. Claim database bersifat durable; failure, timeout, pembatalan caller, dan restart tidak mengizinkan redispatch otomatis dengan key yang sama. Result terminal/usage/audit disimpan dalam satu transaksi; polling ulang tidak menggandakan token. Exception Core menyediakan RunInProgressError dengan run ID/status dan IdempotencyConflictError. API menampilkan konflik HTTP 409 dalam Bahasa Indonesia dan riwayat tetap dapat diperiksa melalui snapshot.

RuntimeTrace menambah `available` dan `unavailability_reason`; trace yang tidak tersedia tidak menyertakan event buatan. Adapter direct membutuhkan ID runtime, model aktual, completion content, dan usage aktual; response capability yang malformed tidak dianggap confined. Ini perubahan validasi adapter, bukan perubahan konfigurasi Hermes.

Snapshot Studio menambah `integrity_valid`, `bench_eligible`, `governance_valid` untuk versi serta `verified` untuk evaluasi/approval. UI memakai flag backend untuk tindakan dan tampilan bukti. Stored label PASS/approved sendiri tidak dianggap bukti valid. JSON bukti malformed ditampilkan sebagai belum terverifikasi, bukan membuat snapshot gagal atau memberi kelayakan.

**3. Database dan kompatibilitas data**

| Migrasi | Perubahan |
| --- | --- |
| `006_approval_evidence` | Approval menambah nullable evaluation_id dan attestation; bukti lama tetap kosong/tidak tepercaya. |
| `007_execution_claim` | Run menambah request_hash, runtime_run_id, dan execution_mode; row lama ditandai legacy. |
| `008_unique_run_claim` | Unique index `(project_id, idempotency_key)` untuk atomic claim pada database hasil Alembic. Key null tetap boleh untuk request tanpa idempotency. |

Migrasi 008 berhenti dengan pesan jelas apabila menemukan key lama duplikat; tidak menghapus, menggabungkan, atau mengganti run secara diam-diam. SQLite writer memakai BEGIN IMMEDIATE; governance juga memakai row lock pada jalur PostgreSQL. DDL PostgreSQL berhasil dikompilasi offline, termasuk unique index. Belum ada pengujian terhadap server PostgreSQL nyata atau integrasi Cloud.

Salinan database pengguna dibuat melalui sqlite backup lalu dimigrasikan 005 → 008. Database asli `.local/studio.sqlite3` tidak dimodifikasi dalam validasi ini. Jumlah sebelum/sesudah sama: blueprint 3, version 2, evaluation 5, approval 2, assignment 2, run 2, audit 24, budget 1. `PRAGMA integrity_check = ok`, foreign-key violations 0, head `008_unique_run_claim`. Bukti lokal: `.local/evidence/batch1-migration-validation.json`. Salinan dan screenshot adalah artefak lokal yang diabaikan Git.

HMAC memakai key acak minimal 32 byte yang dipasang secara atomik. Untuk SQLite persistent, key berada di sisi database, misalnya `.local/studio.aryn-evidence.key`; `*.key` dan temporary key diabaikan Git. Backup database dan key bersama, tanpa memasukkan key ke laporan/Git. Hilangnya key atau pergantian `ARYN_EVIDENCE_SECRET` menggugurkan verifikasi bukti lama secara aman. Backend non-SQLite mengharuskan secret eksplisit; tidak ada default secret produksi atau integrasi Cloud baru.

**4. Bukti pengujian yang dijalankan**

Positive, negative, regression, dan pemeriksaan konsistensi database dijalankan selama setiap pekerjaan. Negatif awal benar-benar gagal sebelum patch. Hasil akhir setelah seluruh perbaikan fungsional:

| Pemeriksaan | Hasil aktual |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest -q` | 169 passed, 3 skipped, 9 warnings; 31,15 detik. |
| `npm.cmd run build` | TypeScript/Vite berhasil; 2.044 modules. |
| `npm.cmd test` | 5 passed, 2 test files. |
| `npm.cmd run test:e2e` dengan Python venv pada PATH | 6 passed; 30,1 detik. API/SQLite disposable port 8711, Bench sebenarnya dengan runtime double. |
| `npm.cmd audit` | 0 vulnerabilities pada dependency frontend. |
| Ruff E4/E7/E9/F/I pada file Core/evidence/API/migrasi dan pengujian Batch 1 yang diperiksa | All checks passed. Ini bukan klaim seluruh repository sudah lint bersih. |
| `git diff --check` | Berhasil. |
| Upgrade database 005 → 008, parity kolom Base.metadata, konflik key legacy, PostgreSQL DDL offline | Berhasil dalam suite integrasi. |
| Upgrade salinan database pengguna + PRAGMA | Berhasil; jumlah seluruh record tetap, integrity ok, FK violations 0. |

Tes integritas mengubah prompt, model, grants, temperature, max tokens, dan metadata langsung di SQL tanpa mengubah hash. Tes Bench mencoba row PASS buatan, score/detail/provenance yang diubah, suite kosong/duplikat, model berbeda, dan failure terbaru. Tes governance mencoba unsigned approval, aktor SYSTEM/AGENT, scope/evaluation/approver palsu, approval usang, serta state bypass. Tes concurrency menghitung dispatch adapter untuk async dan delapan thread dengan koneksi terpisah, pada schema Base.metadata maupun Alembic; mencakup timeout/retry, caller cancellation, ID unik, dan usage satu kali. Tes ownership membuktikan nol operasi adapter untuk ID proyek lain, mapping ID yang tepat, assignment korup, ACK/penolakan cancel, trace unavailable, dan recovery proyek yang benar.

API positif/negatif memeriksa kontrak request, identity spoof, izin, CSRF/Origin/Host, mutation lifecycle, cache, governance flag, serta malformed storage. Playwright menjalankan lifecycle penuh sampai Results/Audit dan refresh persistence; juga navigasi, light/dark, mobile/tablet, keyboard, aksesibilitas axe, validasi, penolakan izin, dan koneksi terputus. Screenshot lokal tersedia di `.local/evidence`; laporan browser di `apps/web/playwright-report`.

Tiga pengujian model live sengaja di-skip: smoke live, assigned agent live, dan lifecycle/cancel live. Pengiriman memerlukan izin pemilik serta opt-in `ARYN_RUN_LIVE_MODEL_TESTS=1`. Tes baca `test_live_hermes_health` dan `test_live_hermes_capabilities_and_confinement` berhasil pada Hermes yang tersedia; tidak ada pengiriman prompt ke model live dalam batch ini. Sembilan warning berasal dari deprecation Starlette/TestClient/httpx dan pengaturan path_separator Alembic; bukan hasil tes gagal.

**5. Residual risk dan keterbatasan**

- Suite regex adalah quality gate riset awal, bukan pembuktian keamanan menyeluruh atau mutu ilmiah.
- Attestation melindungi dari input API atau perubahan row tanpa key. Penyerang yang menguasai proses server sekaligus database dan signing key berada di luar jaminan tersebut. Auth Studio tetap development lokal.
- Setelah timeout/crash, runtime jarak jauh mungkin masih bekerja. Core menyimpan failed/outcome unknown, mempertahankan mapping yang diketahui, tidak mengklaim cancelled, dan tidak mengulang model dengan key sama. Token dari outcome yang tidak diketahui belum dapat direkonsiliasi secara pasti.
- Recovery startup ditujukan untuk satu proses Studio; tidak ada lease/distributed worker baru. Concurrency PostgreSQL nyata belum diverifikasi.
- Direct turn Studio belum menyediakan cancellation atau structured runtime trace. Core async memiliki pengujian cancellation terisolasi. Tidak ada tombol baru atau trace rekayasa.
- Harga biaya dan budget uang tidak diklaim telah terukur; ledger token diperiksa berdasarkan hasil runtime yang tersedia.
- Eksekusi model live dan UAT pengguna masih menunggu sesi pemilik. Tidak ada klaim PASS live berdasarkan runtime double.

**6. Satu sesi UAT bersama melalui Studio**

Sesi ini disiapkan setelah kelima pekerjaan selesai; tidak ada permintaan UAT terpisah per pekerjaan. Gunakan data riset yang boleh dikirim, model yang tersedia, dan persetujuan pengiriman yang sudah ada di Studio. Bila Hermes/model tidak siap, catat kegagalan nyata dan jangan lanjut dengan PASS buatan.

| Langkah | Hasil yang perlu diamati |
| --- | --- |
| Restart Studio dan buka Agent Factory | Desain/navigasi lama tetap; riwayat lama terlihat. Versi atau bukti legacy yang belum valid tidak menyediakan jalur publikasi/eksekusi yang layak. |
| Buat versi baru untuk blueprint yang dipilih | Prompt, model, temperature, max tokens, dan hash tampil sesuai input. Sebelum Bench lulus, approval/publish belum tersedia. |
| Jalankan Bench setelah menyetujui pengiriman model pada dialog | Empat skenario lengkap dengan output aktual, model, usage, durasi, score, dan alasan gagal. Bila gagal, publish tetap diblokir. Jangan ubah prompt hanya demi meluluskan gate; perbaiki konfigurasi jika hasil menunjukkan masalah. |
| Bila Bench lulus, tinjau hash dan beri approval manusia dengan catatan | Approval terikat versi dan evaluasi tepat; audit mencatat keputusan. |
| Publish lalu buat assignment pada blueprint/version yang sama | Published menjadi immutable; assignment menunjuk versi tersebut pada proyek aktif. |
| Jalankan satu instruksi riset yang diizinkan | Results menampilkan output asli, status selesai hanya jika benar, model aktual, token, run ID Core, dan audit; trace menyatakan belum tersedia. |
| Refresh lalu restart saat tidak ada model yang sedang berjalan | Hasil, token, approval, assignment, dan audit tetap tersimpan; key bukti tetap valid. |
| Buat versi berikutnya dengan prompt/parameter yang berbeda | Hash berbeda; evaluasi/approval versi sebelumnya tidak otomatis berlaku. Versi baru kembali membutuhkan seluruh alur. |

Forgery database, run ID lintas proyek, assignment nonaktif, concurrency, dan async cancellation sudah diuji otomatis; pengguna tidak diminta merusak database atau memakai kontrol Studio yang belum tersedia. Catat satu hasil UAT gabungan beserta run/version/evaluation ID dan temuan. Batch 1 berhenti di sini; tidak memulai Batch 2.

**7. Menjalankan aplikasi dengan Windows PowerShell**

Restart diperlukan agar backend dan migrasi baru aktif; launcher membangun frontend terkini. Instalasi yang sudah ada:

```powershell
Set-Location D:\ARYN\aryn-labs\aryn
.\scripts\stop-studio.ps1
.\scripts\start-studio.ps1 -SkipInstall
```

Buka `http://127.0.0.1:8710`. Untuk instalasi pertama, gunakan `.\scripts\start-studio.ps1` tanpa SkipInstall. Jika policy skrip memblokir, jalankan `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-studio.ps1 -SkipInstall`. Backup database dan `.aryn-evidence.key` bersama sebelum pemeliharaan data. Launcher tidak mengubah konfigurasi keamanan Hermes.

Menjalankan ulang gate otomatis tanpa mengirim model live:

```powershell
Set-Location D:\ARYN\aryn-labs\aryn
.\.venv\Scripts\python.exe -m pytest -q
$env:PATH = "D:\ARYN\aryn-labs\aryn\.venv\Scripts;" + $env:PATH
Set-Location apps\web
npm.cmd run build
npm.cmd test
npm.cmd run test:e2e
npm.cmd audit
```

Chromium Playwright sudah tersedia pada lingkungan verifikasi ini. Pada mesin baru, pasang lewat `npm.cmd exec playwright -- install chromium` sebelum E2E. Jangan menyalakan opt-in model live tanpa izin pemilik.

**8. Status penutup**

Lima pekerjaan PASS pada gate otomatis yang relevan. Tidak ada pekerjaan implementasi Batch 1 berstatus REVISI; UAT bersama, pengiriman model live, dan pengujian PostgreSQL nyata belum diklaim selesai. Commit pekerjaan 4 memiliki satu tindak lanjut khusus migrasi setelah pemeriksaan akhir menemukan perbedaan schema. Laporan ini dicommit terpisah sebagai dokumentasi bukti. Push belum dilakukan karena belum ada izin eksplisit push. `main` tidak diubah.
