# Core Execution Hardening

Tanggal audit/validasi: 8 Oktober 2026. Branch `development`, baseline dan HEAD awal
`5e9392c5f976b4725813dd98ccd8c6811472d9ae`. Working tree awal bersih dan HEAD tidak lebih
baru. `main` tetap `630cbc96d728a49a64247ad2b88978529a7cbbad`. Tidak ada push dalam delivery ini.

## Hasil dan batas klaim

Core memakai ledger budget existing, signed execution claim, owner process yang dikunci,
dan satu kontrak hasil persisten. Factory Bench memakai coordinator yang sama, termasuk bounded capabilities/model preflight dan action trace. BN-06,
AF-07, immutable AgentVersion, exact human approval, CAS, atomic publication/rollback,
dan independent history commitments migration 013 tetap berlaku.

Deployment yang didukung untuk execution sekarang adalah **satu authority process pada
satu host**, dengan beberapa coordinator dalam process tersebut. SQLite diuji dengan
proses OS nyata, bukan pengganti bukti live concurrency PostgreSQL. PostgreSQL DDL diuji offline; live PostgreSQL locking/privileges dan
multi-host failover belum terbukti. Hosted foundation freeze masih BLOCKED.

Provider tidak menyediakan exact input-token admission atau hard total-token/cost ceiling
pada kontrak existing. Karena itu, input admission adalah estimasi, output adalah request
cap yang diteruskan transport, dan total/input/output terukur diverifikasi setelah
completion. Pelanggaran terukur menjadi failure, bukan success; angka actual tidak
dipangkas agar terlihat sesuai policy. Missing evidence/timeout/outcome ambigu memblokir
verified completion dan mempertahankan reservation. Ini **bukan jaminan provider tidak
menagih lebih dari cap**, bukan hard tokenizer quota, dan bukan Managed AI billing.

## Root cause dan perbaikan

| Temuan | Root cause | Perubahan |
|---|---|---|
| H3 | Agent budget/timeout hanya metadata; preflight estimasi tanpa reservation; accounting Bench berada di wrapper API; missing usage bisa menjadi nol | Effective limits min agent/project/org/model/runtime, full token reservation sebelum dispatch, deadline Core, measured settlement satu transaksi, availability terpisah, Factory Bench melalui Core |
| H5 | Startup memperlakukan seluruh in-flight run/evaluation sebagai abandoned; tidak ada live owner atau fencing | OS lock lifetime, owner UUID per authority, PG advisory session lock, stale owner fence, recovery hanya owner sebelumnya setelah memperoleh authority, terminal outcome_unknown |
| M1 | Query scoped kosong jatuh ke global cache correlation ID | Scope wajib di semua reads; hasil database kosong tetap kosong; ephemeral cache filter org/project |
| M3 | Dependency exception/raw payload bisa masuk client, SSE, audit; prompt berulang di audit | Public code/message/IDs, scrub nested secrets/known credentials, prompt/output audit hanya fingerprint/reference; operational content tetap scoped |
| M4 | Persisted Bench verification membuat signer/identity/permission authority dari environment baru | Manager/engine memegang configured Core signer, PermissionEngine dan ApprovalEngine; revalidation memakai instance tersebut, bound mutation session |
| M5 | Studio membaca assignment sebelum await dan memakai version itu untuk audit/response | Semua run outcome/audit/cache/SSE dari committed Core claim; preclaim hanya intent; captured signed provenance tetap sama saat rollback |
| L1 | Project admin capability lebih luas daripada org governance commit authority; permissions sebelum await/transaction bisa stale | Org admin wajib approval/baseline/rollback, org admin/operator publication dengan project permission yang sesuai; membership re-read/lock saat commit; reads reauthorize setelah await |
| L2 | Response baru/cache/SSE/history berbeda dan status/error/usage/provenance parsial | RunResult persisten satu schema, explicit unknown/unavailable, typed important events/response reader, old flat aliases dipertahankan |

## Execution authority dan transaction boundaries

1. Studio default startup memperoleh `ExecutionAuthority` sebelum migration/provision/recovery.
   Coordinator dan Factory memperoleh instance yang sama per engine/database/process.
   SQLite absolute path memakai `.execution.lock` nonblocking OS lock; memory DB hanya
   authority process lokal. Host ACL harus melindungi path/parent dari unlink/replacement.
2. PostgreSQL membutuhkan protected `ARYN_HISTORY_COMMITMENT_PATH` dan session advisory
   lock database. Koneksi khusus dipertahankan sepanjang owner lifetime, diperiksa backend
   PID/invalidation, diserialisasi antar-thread, lalu explicit unlock dan invalidasi ketika
   disposed. Kehilangan koneksi menolak authority, bukan transparan reconnect/takeover.
3. Second process tidak boleh startup pada database yang masih dimiliki process hidup.
   Tidak ada lease expiry berbasis timeout yang dapat mengambil authority dari process
   lambat. Coordinator kedua dalam process yang sama berbagi owner dan melewati recovery
   atas run/Bench yang masih dimiliki owner tersebut.
4. Claim transaction: current membership + assignment/version/history/publication verification,
   effective limits, unique project idempotency key, Core run ID, owner/deadline,
   budget reservation, signed claim dan audit initiation commit **sebelum** runtime dispatch.
   Tidak ada lock database dipegang sepanjang inference. SQLite writes memakai BEGIN
   IMMEDIATE; PostgreSQL budget rows memakai FOR UPDATE, org `*` lalu project.
5. Setelah capabilities/model-availability await, Core memeriksa owner, state, deadline dan
   membership lagi sebelum dispatch. Factory approval/publication/assignment mengunci version sebelum membership;
   approval signatures/current approver authority direvalidate dalam session mutation.
6. Terminal transaction: owner/claim verification, model/runtime identity, measured usage,
   deadline/limits, ledger settlement, CAS state transition dan authenticated audit commit
   bersama. `usage_settled` serta terminal no-op mencegah double counting/re-dispatch.
7. Engine disposal/lost lock memfence coordinator lama. Engine lama tidak otomatis memperoleh
   authority baru. Restart memakai engine baru; old in-flight owner menjadi outcome_unknown,
   bukan confirmed failure/cancellation. Terminal tidak dapat diubah oleh stale completion.

Cancellation ACK hanya mencatat attempted/stopping. True dikembalikan ketika runtime/Core
terminal state membuktikan cancelled. Deadline, polling exception, caller cancellation atau
crash tanpa terminal evidence tetap unknown. Async deadline watchdog berjalan tanpa client
polling; runtime yang mengabaikan task cancellation tidak dapat menulis completion Core.
Provider/server mungkin masih bekerja sesudah Core deadline, sehingga reservation ditahan.
Rollout 013→014 harus menghentikan binary Core lama terlebih dahulu; mixed-revision live
execution tidak didukung. Pre-014 rows tanpa signed owner tidak membuktikan worker telah
mati. Recovery legacy hanya menyatakan outcome belum diketahui/read-only dan admission
scope diblokir sampai consumption direconcile, bukan proof termination/confirmed cancellation.
OS ownership proof berlaku pada authority 014 yang berpartisipasi dalam lock protocol.

Bench evaluation memiliki evaluation_owner_id. Startup tidak menolak evaluating version milik
owner hidup. Recovery owner sebelumnya menandainya rejected/interrupted, tanpa mengarang
Bench execution result/approval. Result commit memeriksa owner, exact payload, evaluating
state dan current permissions. Generic Factory service tetap melewati accounting walau tidak
melalui HTTP wrapper. Standalone BenchRunner adalah diagnostic tanpa persisted promotion
authority; signed Factory evidence selalu menggunakan Core coordinator.

Untuk multiworker/cloud scale-out diperlukan owner lease durable, heartbeat, fencing token
monotonik pada setiap commit, koordinasi durable dengan history commitment store, dan
independent provider-outcome reconciliation. Mekanisme sekarang tidak mengklaim distributed
worker framework, distributed freshness, atau native Hermes scheduler sebagai Core authority.

## Budget, usage dan provider contract

- Token total ceiling paling ketat dari agent RunRequest immutable config, Core default,
  organization `*` budget jika dikonfigurasi, project budget, dan model context window.
  Agent tidak dapat menaikkan project per-run cap. Timeout adalah min budget policy,
  AgentConstraints, Bench scenario/suite latency, request, dan runtime adapter timeout.
- Input UTF-8 admission estimate disimpan terpisah dalam effective_limits. Nilai itu tidak
  pernah dimasukkan sebagai measured ledger consumption. Exact tokenizer belum tersedia.
- Reservation mengunci **seluruh effective total ceiling**, bukan estimasi prompt, terhadap
  cumulative + outstanding reserved tokens. Org budget mencakup semua project; unknown
  historical execution juga memblokir admission pada scope aggregate org yang relevan.
- Ledger tetap `usage_budgets` existing. Tidak ada ledger API/Bench kedua. Fresh project
  budget default aggregate 1,000,000 tokens; migration tidak menebak quota organisasi/project
  lama: max_total_tokens NULL berarti aggregate quota belum dikonfigurasi. Existing per-run
  caps tetap berlaku. Jika legacy consumption belum bisa direconcile, execution scope diblokir. Angka aggregate tidak mengandung subscription/period-reset semantics.
- Complete measured triplet integer nonnegative dengan input+output=total diperlukan.
  Confirmed partial failure/cancellation dapat settle actual usage; unavailable evidence
  tidak menjadi measured zero. Numeric compatibility default 0 selalu disertai unavailable.
- Settlement membebaskan full reservation dan menambah actual tokens sekali saja, termasuk
  excess jika runtime melanggar limits. Missing evidence mempertahankan reservation;
  idempotent replay tidak dispatch atau settle lagi. Tidak ada auto-release/reconciliation
  yang menebak consumption. Operator harus memperoleh authoritative independent evidence.
- Cost hanya persisted bila runtime menyediakan finite nonnegative cost dengan source
  provider_usage/runtime_meter. Tidak ada harga/model-rate atau cost hasil perkiraan dibuat.
  Missing cost tetap NULL. Cost cap terukur yang dilanggar menjadi failure.
- Direct managed Gemini/Nous route diblokir bila pricing/ceiling authority belum tersedia.
  9Router/BYOK/local/mock diberi billing_category external_or_local; Core tidak melabeli
  konsumsi tersebut ARYN Managed AI. Atomic **money reservation** belum tersedia dan tidak
  diklaim. Managed AI baru dapat dibuka setelah trusted price/reservation/provider contract.
- Guarded Hermes transport meneruskan Core output cap, menolak extra n/completion override,
  membatasi satu upstream dispatch per receipt termasuk retry setelah success/failure,
  mempertahankan exact model dan deny-by-default tools. Tests memakai HTTP doubles;
  tidak ada paid/live-provider request.

## Audit, errors dan authority consistency

AuditEvent schema 2 dari migration 013 tetap authenticated/canonical UTC. New sanitization
berjalan sebelum hash/sign, mencakup nested sensitive keys, credential patterns dan credentials
runtime/gateway yang diberikan secara eksplisit. Prompt/system prompt/output/raw response/trace
pada audit menjadi SHA256 + byte count, bukan raw content. Token counters/evidence metadata
tidak ikut dihapus oleh regex credential. Historical weak audit tidak diubah atau dijadikan
approval/publication baru.

Audit correlation/all-events read memerlukan SecurityContext. Database query kosong tidak
menggunakan global cache. Repository/session/API selalu membatasi org/project. In-memory
cache juga discope, termasuk jika correlation ID dua tenant sama.

Dependency error text, repr, traceback dan upstream body tidak dikirim ke JSON/SSE atau audit.
Public error berisi error_code aman, pesan statis, correlation_id dan run_id bila claim ada.
Frontend ApiError mempertahankan IDs. Internal Core deadline persistence log hanya code/ID;
raw diagnostic exception tidak disimpan oleh jalur ini. Runtime native Hermes tetap trusted
operational storage/process terpisah; deployment harus membatasi akses log/trace/output dan
retention secara mandiri. Tidak ada retention enforcement baru yang diklaim. Recommended
operator policy: log diagnosis minimal/private, rotasi dengan TTL yang ditentukan operator,
scoped operational prompts/results hanya selama kebutuhan diagnosis yang disetujui.

Sanitizer tidak bisa mengenali semua secret arbitrer tanpa label/pattern/registered credential.
Host, signing key, trusted runtime configuration dan operational DB/ledger tetap trusted.
Tidak ada klaim tahan compromised database superuser/host atau coordinated snapshot rollback
ledger execution. Migration 013 independent history freshness boundary tetap berlaku sendiri.

BenchRepository dan activation/regression repository memakai DatabaseManager/session configured
signer, PermissionEngine, TrustedIdentityBinder dan ApprovalEngine. Tidak ada reconstruct
identity secret atau random signer dari environment pada persisted revalidation. Injected Core
trusted authority tetap berhasil tanpa ARYN_IDENTITY_SECRET, sedangkan missing/invalid authority
tetap deny. Approver org admin/status direvalidate saat mutation, tidak hanya saat approval dibuat.

## Run/Studio contract dan historical compatibility

RunResult selalu membawa Core run_id, status, requested/model, actual_model/provider/runtime/gateway
jika diamati, runtime_run_id jika tersedia, captured assignment/version/payload/transition,
publication reference dalam execution_provenance, effective_limits, verification flags,
usage availability/cost source, output_reference dan sanitized error_code. Timestamps UTC epoch
seconds pada envelope; UI menerima historical ISO timestamp juga.

JSON baru, SSE run.completed, cached terminal replay dan historical snapshot memakai serializer
persisted yang sama. run.completed berarti transport outcome tersedia; status bisa failed,
cancelled atau outcome_unknown dan UI tidak menampilkan success. In-progress replay kembali
state/provenance yang sama dan tidak memulai inference kedua. HTTP execution dependency failure
sebelum terminal evidence tetap sanitized error; caller bisa diagnosis/retry idempotent Core ID.

Rollback saat model preflight hanya mempengaruhi **claim berikutnya**. Core memilih exact current
version pada transaksi claim, dan final Studio audit/result berasal dari claim tersebut. Run yang
sudah in-flight tetap bound versi lama; current assignment tidak menulis ulang metadata history.
Preclaim event run.requested hanya membawa intent, tidak version/model yang bisa stale.

Historical rows tetap readable dengan missing claims/actual usage/provenance sebagai unverified
atau unavailable. Signed execution envelope mengikat org/project, run/request hash, model/provider,
owner, mode, canonical deadline, limits dan assignment attestation. Tamper/deletion sebagian
memblokir verification; menghapus seluruh new claim tidak membuat historical read-only row eligible
untuk authoritative execution replay. Existing completed counters tidak direattest sebagai measured.

## Migration dan compatibility

Migration `014_execution_authority` melanjutkan `013_history_integrity`. RunState menambah
execution claim/signature/owner/deadline/limits, reservation/settled/availability, sourced cost,
error code; UsageBudget menambah aggregate token cap/reservation; AgentVersion menambah evaluation
owner metadata. Tidak ada domain baru atau backfill historical evidence. Metadata fresh install
memiliki kolom yang sama dengan migration chain.

SQLite upgrade 005â†’014, 004â†’014, 009â†’014 dan 013â†’014; downgrade/re-upgrade 014â†”013 serta
legacy multi-revision migration diuji. PostgreSQL upgrade/downgrade DDL dikompilasi offline.
Downgrade menghapus execution-authority fields; backup wajib secara operasional sebelum downgrade.
Re-upgrade tidak mengarang kembali claim/settlement; unknown historical consumption memerlukan
reconciliation. Original database pengguna tidak dimigrasikan/dimutasi oleh validasi clone. Clone dari
.local/studio.sqlite3 (009) mempertahankan 8 runs, 13 versions dan 84 audit events; clone
aryn_local.db (004) mempertahankan empty counts. Keduanya upgrade ke 014, foreign_key_check
kosong, integrity_check ok dan zero fabricated execution claim. Original revision tetap sama.

## Evidence dan validasi aktual

Seluruh validation run final selesai. Hasil berikut berlaku untuk delivery ini. Command dijalankan dari repository root
kecuali npm dari apps/web. Tidak ada live model/provider berbayar diaktifkan.

| Command aktual | Hasil aktual |
|---|---|
| Dedicated command di bawah | **108 passed**, 31 warnings, 220.35 detik; no skipped |
| `python -m pytest -q -ra --tb=short` | **661 passed, 5 skipped**, 37 warnings, 619.25 detik; no failures |
| `npm.cmd test -- --reporter=dot` | **83 passed**, 13 files, 21.26 detik |
| `npm.cmd run build` | TypeScript/Vite PASS, 28.93 detik; existing >500 kB bundle warning |
| `npm.cmd run test:e2e` | **16 passed**, 0 retries/flaky/skipped, 5.0 menit; final serial run |
| SQLite clone migrations 009/004→014 | PASS, counts preserved, no fabricated claims, original DB unchanged |
| PostgreSQL upgrade + 014→013 offline SQL | PASS compilation only, covered dedicated tests |
| Focused Ruff `--select E4,E7,E9,F` changed production Python/new execution tests | PASS |
| `git -c core.safecrlf=false diff --check` | PASS |

```powershell
python -m pytest tests/security/test_core_execution_authority.py tests/integration/test_core_execution_contract.py tests/security/test_execution_idempotency_claims.py tests/security/test_governance_history_integrity.py tests/security/test_9router_exact_model.py tests/integration/test_schema_migration_compatibility.py tests/integration/test_assignment_activation_migration.py -q -ra --tb=short
```

Final logs: .local/execution-dedicated-release.log, execution-backend-release.log,
execution-browser-serial.log, execution-frontend-confirmed.log, execution-build-confirmed.log,
execution-existing-migration.json, execution-focused-lint.log. Logs tetap artefact lokal,
bukan data prompt model atau secrets yang dipublikasikan ke repository.

Lima backend skips adalah tiga live-model opt-in dan dua Hermes integration tanpa
API_SERVER_KEY. No paid/live-provider testing. Deprecation warnings FastAPI/httpx dan
Alembic path_separator dicatat; tidak berarti test failure. Percobaan full configured Ruff pada seluruh changed Python files menghasilkan **FAIL,
386 lint findings**, termasuk style rules dan unused fixture/import pada legacy tests;
full configured lint tidak direrun pada final revision. Final focused correctness lint di
atas PASS untuk changed production Python/new execution tests. Tidak ada klaim bahwa
seluruh configured lint clean; tidak ada security assertions dihapus sebagai lint fix.

Perubahan assertions compatibility yang disengaja: operational run-count tests membedakan
Core Bench consumption dari assignment runs; assertion tanpa operational dispatch tetap ada.
Downgrade tests membandingkan semua immutable configuration/evaluation/governance fields,
sedangkan evaluation_owner_id baru memang dihapus migration downgrade. Recovery/caller
cancellation sekarang mengharapkan outcome_unknown, bukan fabricated failure. Concurrent
idempotency mengharapkan one dispatch, in-progress signal, lalu exact terminal replay. API
failed runtime completion mengembalikan result envelope HTTP 200 dengan status failed;
transport error tetap error. Security assertions tidak dihapus untuk membuat PASS. Dua
existing approval-message assertions dipertahankan dan public/static denial text disesuaikan.

Percobaan validasi sebelum final mencatat failures yang diperbaiki: isolated cancellation
fixture kehilangan required output/created_at; org denied claim rolls back new budget row;
SSE browser Network.getResponseBody tidak tersedia. E2E kini membaca Response.clone pada
fetch browser yang nyata tanpa response replacement/request tambahan, serta mempertahankan
terminal evidence/URL assertions. Full run sebelum pesan approval diperbaiki menghasilkan
657 passed, 2 failed, 5 skipped; ini bukan final PASS. Beberapa full runs diinterupsi ketika
review menemukan perubahan tambahan, sehingga tidak digunakan sebagai completion evidence.

## Negative review akhir

- Tested agent timeout lebih rendah, measured input/output/total/cost breach, concurrent project
  quota dan aggregate org quota, idempotent settlement, Factory direct Bench consumption.
- Tested unavailable usage, partial failed usage, unknown reservation retention, no synthetic cost.
- Tested real Windows second process denial, crash process termination/new owner recovery, live
  same-process coordinator/app/Bench recovery exclusion, disposed stale worker terminal fencing.
- Tested cancellation ACK stoppingâ†’unknown, async deadline tanpa polling, membership revoke sesudah
  claim dan selama polling, project admin capability/commit denial, role change after preflight.
- Tested same correlation ID cross-tenant scoped empty read/cache, nested secret/prompt audit
  fingerprint, synthetic credential exception JSON/SSE/provider response, captured rollback race.
- Tested JSON/SSE/cached equality, in-progress actor binding/read reauthorization/unsigned claim denial,
  signed owner/deadline/limits/model tampering and claim deletion,
  injected generic Bench approval authority without environment secret, 013 commitments/BN-06/AF-07.
- Reviewed no hidden model retry, no successful error envelope, no fabricated historical approval,
  version immutability/state machine, no transaction kept open over model inference, exact claim
  source for API/audit/history, permission revalidation after async boundary.

Browser release run bersamaan dengan full/dedicated pytest mencatat 13 passed, 3 failed
pada display wait 5 detik. Trace menunjukkan snapshot HTTP 200 sekitar 4.9-9.6 detik dan
UI masih Memuat data proyek; tidak ada authority-denial bypass. Browser rerun final serial menghasilkan **16 passed** tanpa perubahan/kelonggaran assertions. Snapshot revalidation per-version,
long history dan repeated authority checks mempunyai biaya latency; optimisasi/pagination
belum diimplementasikan dan tidak diklaim scalable.

## Residual dan keputusan freeze

Supported local execution protections telah diimplementasikan; tidak ada klaim provider hard total
quota/cost, Managed AI ledger, distributed failover atau PostgreSQL live concurrency PASS. Unknown
outcomes mempertahankan reservation dan memerlukan manual evidence reconciliation, sehingga recovery
aman dapat mengurangi availability. Single-authority restriction sengaja enforced sampai desain
lease/heartbeat/fencing diterapkan dan diuji. Full audit-stream freshness/host compromise resistance,
production auth/retention enforcement dan operational reconciler tetap di luar capability yang dibuktikan.
Hosted foundation freeze tetap BLOCKED, selaras migration 013.

## Files changed

```text
.gitignore
STATUS.md
apps/web/e2e/studio.spec.ts
apps/web/src/components/canvas/canvas-builders.ts
apps/web/src/components/canvas/canvas-inspector.tsx
apps/web/src/components/shared.tsx
apps/web/src/components/version-form.tsx
apps/web/src/features/bench.tsx
apps/web/src/features/runs.tsx
apps/web/src/lib/api.ts
apps/web/src/lib/types.ts
apps/web/src/lib/utils.ts
apps/web/src/studio.tsx
apps/web/src/test/run-result-contract.test.tsx
database/connection.py
database/migrations/versions/014_execution_authority.py
database/repositories/agent_activation_repo.py
database/repositories/bench_regression_repo.py
database/repositories/bench_repo.py
database/repositories/budget_repo.py
database/repositories/run_state_repo.py
database/schema.py
docs/9router-gateway.md
docs/agent-factory-contracts.md
docs/bench-engine.md
docs/core-execution-hardening.md
docs/studio.md
modules/agent_factory/service.py
modules/bench/runner.py
modules/core/approvals/engine.py
modules/core/audit/logger.py
modules/core/errors.py
modules/core/permissions/engine.py
modules/core/usage/engine.py
modules/core/workflows/coordinator.py
modules/core/workflows/ownership.py
packages/contracts/runtime.py
packages/contracts/timestamps.py
packages/runtime_adapters/hermes/adapter.py
services/api/studio.py
services/runtime/gateway_transport.py
tests/e2e/test_smoke_end_to_end.py
tests/integration/test_9router_studio.py
tests/integration/test_assignment_activation_migration.py
tests/integration/test_core_execution_contract.py
tests/integration/test_schema_migration_compatibility.py
tests/integration/test_studio_api.py
tests/security/test_9router_exact_model.py
tests/security/test_agent_security_and_governance.py
tests/security/test_core_execution_authority.py
tests/security/test_core_persistence_security.py
tests/security/test_execution_idempotency_claims.py
tests/security/test_tenant_isolation_ownership.py
```


Commit delivery menggunakan pesan `Harden Core execution ownership, budgets, and captured provenance`.
Commit berada pada development dengan parent baseline 5e9392c5f976b4725813dd98ccd8c6811472d9ae;
hash aktual diberikan pada laporan akhir/git log. Tidak ada push, merge atau rebase main.

## Deployment authentication follow-up

Deployment boundary hardening continues this revision without changing captured execution claims, budgets/settlement, owner fencing or governance history. Hosted identity now comes from configured verified OIDC issuer/subject mapping and server session; Core binder signs the session reference and PermissionEngine revalidates session/mapping/current membership at authorization/commit. Local development identity requires explicit mode and cannot be enabled in production. See [deployment security](deployment-security.md); real hosted infrastructure remains unverified.
