# Generic Bench Evaluation Engine

Tanggal validasi: 8 Oktober 2026. Branch kerja: `development`.

## Audit dan keputusan arsitektur

Audit mencakup contracts agent/Bench/runtime/approval, runner dan quality gate, lifecycle Factory, Core approval/permissions/evidence/idempotency, repositories/schema/migrations, Hermes adapter, API Studio, frontend Bench, serta tests unit/integration/security/E2E. Dokumen README, AGENTS, SECURITY, kontrak Factory, governance, Studio dan laporan Bench dibaca. Checkout `aryn-docs` hanya menyediakan indeks; dokumen PRD/ARCH/TECH/SEC privat yang disebut README belum tersedia. Tidak ada ID requirement privat yang direka.

Sebelumnya runner dan quality gate menilai regex Research Safety secara langsung; Factory dan preflight API memaksakan empat skenario; registry hanya menyelesaikan satu suite. Persistence sudah mempunyai detail JSON, provenance JSON, HMAC tenant-scoped, dan revalidation sebelum approval/publish. Jalur tersebut dipertahankan.

Alur sekarang:

`EvaluationReference → authoritative suite registry → BenchScenario → runtime execution → deterministic graders → ScenarioResult → suite aggregate → persisted evidence revalidation → accepted baseline → deterministic regression comparison → promotion gate → Core approval → publish + baseline advancement`

- `packages/contracts/bench.py`: contracts generik, spesifikasi grader discriminated, dan validasi schema/configuration.
- `modules/bench/registry.py`: registry immutable yang menyimpan salinan definisi tervalidasi; alias ambigu/duplikat ditolak. Resolution mengembalikan salinan baru, sehingga mutation caller tidak mengubah authority.
- `modules/bench/runner.py`: resolve/preflight seluruh suite sebelum dispatch, confined isolated execution, pengumpulan evidence, grader composition dan aggregation.
- `modules/bench/graders.py`: interface dan implementasi deterministic tanpa state mutable bersama.
- `modules/bench/evidence.py`: normalisasi observasi adapter, revalidation setiap grader/agregat, dan pembacaan format historis.
- `modules/bench/aggregation.py`: penghitungan scenario, suite dan promotion policy yang sama untuk runner dan validator.
- `modules/bench/scenarios.py`: definisi Research Safety dan catalog server. Penambahan suite dilakukan dalam konfigurasi server melalui `BenchSuiteRegistry`, bukan melalui request browser.

## Contracts dan fail-closed validation

`BenchScenario` direfactor, bukan diduplikasi dengan class scenario lain. `schema_version=2.0.0`, `scenario_version`, identifier, name/description, domain/category string, prompt, expected outcomes, allowed actions/tools/capabilities, forbidden actions/capabilities, safety constraints, output/evaluation contract, grader specifications, runtime requirements, fixtures ber-hash, dan resource limits merupakan fields typed.

Scenario kosong, version invalid, unknown grader, duplicate identities, contradictory grants, schema invalid/unresolved/external reference, fixture hash mismatch, atau non-finite limits ditolak sebelum runtime dispatch. Setiap scenario memerlukan integrity, model identity, forbidden-action dan latency/resource graders; contract output scenario memerlukan schema grader. Agent output JSON/schema/required sections juga memerlukan schema grading pada setiap scenario.

`OutputContract` dan `EvaluationReference` adalah shared contracts; `AgentOutputContract` dan `AgentEvaluationReference` tetap tersedia sebagai aliases. Serialization default untuk canonical payload format 3 tidak berubah. Default Research Safety dipertahankan untuk agent existing; reference suite lain mendapatkan evaluation version dan default required scenarios dari manifest suite tersebut. Reference/version/required identities divalidasi lagi sebelum execution dan promotion.

Expected outcomes dan safety constraints berbentuk deskripsi. Kalimat bebas tersebut tidak dianggap enforcement. Enforcement berasal dari typed boundaries, output contracts, grader specifications dan suite policy yang eksplisit.

## Graders yang diimplementasikan

Semua grader menghasilkan `GraderResult` dengan ID/type/version, pass indicator, state, machine-readable reason dan details. Malformed atau unavailable evidence tidak menghasilkan PASS. Semua grader tetap dijalankan, sehingga satu kegagalan tidak menyembunyikan hasil grader lain.

| Grader | Enforcement |
|---|---|
| Schema validity | JSON parsing dengan duplicate-key dan non-finite rejection; JSON Schema 2020-12 validation termasuk required fields/types/extra properties dan formats; required sections. Scenario contract dan agent contract **keduanya** diperiksa. Strict mode menutup object properties yang belum mempunyai aturan additionalProperties eksplisit; non-strict tetap menghormati schema eksplisit. Hanya local references yang dapat di-resolve; external retrieval dan schema IDs yang mengubah root ditolak. |
| Forbidden action | Explicit intersection scenario grants dan agent grants; confined adapter capabilities; deny-by-default tools/capabilities; explicit action grants dan forbidden actions; mock-write isolation untuk suite bertool. Complete structured traces dapat membuktikan batas aksi; missing/malformed traces yang dibutuhkan menghasilkan unverifiable/invalid evidence. |
| Approval enforcement | Captured approval diverifikasi melalui **Core ApprovalEngine**, bukan subsystem baru. Status, tenant/project, target identity, exact payload hash, evaluation identity, allowed actors, timestamp/age, current durable record, HMAC dan authority approver aktif diperiksa. |
| Idempotency | Minimal dua observasi yang mengikat tenant/project, idempotency key dan request fingerprint; result/state hash konsisten; replay identity; stable side-effect IDs; duplicate IDs atau emission side effect pada replay ditolak. Missing observations tidak bisa membuktikan idempotency. Tidak ada live writes atau destructive replay untuk menghasilkan proof. |
| Model identity | Requested model, adapter model, actual model dan runtime requested model harus konsisten; provider/backend/gateway dapat diwajibkan oleh spec. Silent fallback dan provenance mismatch ditolak. |
| Latency/cost/resources | Finite nonnegative latency/cost/resources, integer nonnegative token usage dan input+output=total; configurable latency/token/cost/resource limits. Limit efektif menggunakan nilai terketat dari grader, scenario dan suite. Cost/resource yang diwajibkan tetapi tidak tersedia menghasilkan unverifiable. |
| Evidence integrity | Evaluation/version/payload/suite/scenario identities, scenario configuration hash, adapter provenance, execution content hash, run identity, dan execution HMAC bila digunakan. Missing attestation pada signed production path ditolak. Model identity diperiksa oleh grader wajib tersendiri. |
| Text pattern | Grader content khusus untuk expected/forbidden patterns. Research Safety menggunakan grader ini; engine tidak mempunyai regex dispatch rules. |

`ScenarioExecutionEvidence` memisahkan observasi runtime dari hasil penilaian. `ScenarioResult` berisi execution evidence, individual graders dan scenario aggregate. `BenchEvaluationResult` menyimpan suite aggregate serta quality-gate decision terhadap reference agent; keduanya dapat berbeda ketika reference agent lebih ketat. States membedakan `failed`, `policy_violation`, `unverifiable`, `invalid_evidence`, `runtime_error`, dan `passed`. Invalid/unverifiable/runtime/policy failures tidak dapat ditoleransi dengan menurunkan score threshold.

## Runtime observations dan batas coverage

`RunResult.execution_evidence` adalah extension optional untuk adapter yang mampu menyediakan observasi lebih kaya. Bench menerima hanya fields berikut dan memvalidasi `run_id` terhadap result adapter:

- `trace_complete` dan `actions` dengan action ID/action/tool/capability/side-effect identity;
- `idempotency_observations` dengan organization/project/key/request hash/result hash/state hash/stable side-effect IDs/**emitted** side-effect IDs/replayed;
- `cost_usd` dan named `resources`.

Unknown judgement fields seperti `passed`/`score`, identity mismatch, malformed actions, non-finite cost/resources, atau coercion dari boolean menjadi cost ditolak. `RuntimeTrace` hanya dianggap complete bila adapter memberikan structured events dan explicit completeness evidence untuk run yang benar.

Hermes existing tetap menyediakan model/provider/backend/gateway provenance dan token usage. Hermes belum menyediakan supported complete action traces, cost, resource measurements tambahan, atau repeated-operation observations. Research Safety menggunakan capability confinement yang sudah tersedia dan tidak mengklaim action-level trace proof. Suite yang mewajibkan evidence yang belum tersedia gagal secara eksplisit. Bench tidak mengarang cost atau idempotency PASS. Test idempotency juga memeriksa observasi dari claim/cache Core existing dengan satu dispatch adapter terisolasi.

Tools dalam Bench hanya diizinkan melalui grants eksplisit dan adapter dengan mocked-write isolation. Studio/Hermes tetap text-only. Tidak ada production tool capability baru yang dibuka.

## Research Safety compatibility

Empat scenario `research-safety-1.2.0` dipertahankan: prompt injection defense, tool confinement, conceptual grounding dan grounded abstention. Prompt, expected/forbidden patterns, latency limits, binary scenario scores dan syarat empat scenario lulus tidak diperlonggar. Masing-masing scenario sekarang mendeklarasikan integrity, exact-model, confinement, schema, content-pattern dan resource graders.

Canonical suite hash baru mencakup seluruh manifest, scenarios, grader specs dan policy. `research_suite_hash()` dipertahankan sebagai historical scenario hash untuk format evidence lama. `expected_pattern`, `forbidden_pattern` dan `max_latency_seconds` tetap dapat dibaca melalui compatibility properties pada scenario.

Evidence format 1 yang sudah tersimpan tetap dapat direvalidate dengan original serialization/HMAC dan historical suite hash, tanpa mendapat klaim grader baru. Evidence unsigned, tampered, atau configuration-mismatched tetap tidak eligible. Penulisan evaluation baru wajib format 2 dan complete attested execution evidence. Tests menjalankan approval/publish untuk historical evidence yang intact, dan menolak downgrade pada new writes.

## Factory, persistence dan API

Factory hanya menyelesaikan suite reference melalui Bench sebelum mengubah version menjadi evaluating. Factory tidak mengimpor scenario Research Safety. Canonical format 3, immutable published configuration, exact-payload approval, no agent self-approve/publish, tenant/project isolation dan latest-evaluation gate tetap berlaku.

`details_json` menyimpan seluruh execution/grader/scenario evidence. `provenance_json` menyimpan format, suite/config hash, requested model, adapter, output contract, agent boundaries, evaluation reference, suite aggregate, gate decision dan outer attestation. Repository mengikat policy snapshots ke current canonical agent configuration dan tenant, lalu menghitung ulang grader/agregat. HMAC original format historis dipertahankan. Generalization awal tidak mengubah schema; BN-06 menambahkan migration `011_bench_baseline_regression` untuk authority baseline/comparison yang terpisah.

## Accepted baseline dan regression governance (BN-06)

Audit kelanjutan dimulai pada `eb3cc223e9b70fa21e9e77d8d468d2b730353c48` di `development`. Engine generik, suite registry, generic graders, signed execution/evaluation evidence, latest evaluation semantics, Core authority dan canonical Agent payload format 3 dipertahankan. Sebelumnya belum ada baseline governance, durable comparison, atau regression enforcement. Private PRD/ARCH/SEC masih hanya berupa indeks dalam checkout; BN-06 mengikuti requirement yang diberikan pemilik secara langsung.

### Authority dan lifecycle

- `bench_baselines` adalah riwayat append-only. `agent_blueprints.bench_baseline_id` menunjuk satu current baseline untuk organization/project/blueprint. Suite canonical/version/config hash ikut mengikat receipt; pindah suite tetap bertemu baseline blueprint yang sama dan tidak membuka bootstrap baru.
- `AcceptedBaseline` menyimpan evaluation/version/payload identity, fingerprint seluruh persisted evaluation, fingerprint konfigurasi Agent yang sebelumnya sudah diverifikasi format 3, suite definition snapshot, generation, predecessor hash/ID, accepted actor/time, reason dan Core approval reference bila publication. Receipt ditandatangani HMAC domain `bench_baseline`. Signed evaluation tidak diubah.
- Admin human dapat menerima **latest verified passing evaluation** melalui permission Core `bench:accept_baseline`. Exact version/evaluation/payload dan registry divalidasi server. Intent browser hanya evaluation ID, reason, expected current baseline ID dan explicit suite-transition intent. CAS yang stale ditolak. Failed/forged/tampered evaluation, unknown suite, wrong tenant/blueprint dan stale configuration tidak dapat diterima.
- Bootstrap hanya berlaku saat belum ada accepted baseline **dan** belum ada published/deprecated history pada blueprint. Ini mengizinkan promotion pertama dari versi yang mempunyai passing verified evaluation; nomor semver/draft terdahulu tidak menjadi authority. Approval menandai comparison sebagai `bootstrap`. Tidak ada baseline otomatis dari label `passed`.
- Publish yang melewati current regression gate dan exact-payload Core approval memajukan baseline secara atomik dengan publication dan audit. `accepted_by` berasal dari human approver Core; actor publikasi dicatat di audit. Publication pertama membuat generation 1; publication berikutnya menambah generation dan predecessor receipt tanpa overwrite. Republish idempotent tidak memajukan baseline lagi.
- Database lama tanpa independently committed baseline origin/head menghasilkan unverified history setelah `013_history_integrity`; source published/deprecated, signed evaluation dan approval lama tetap readable tetapi tidak membuktikan freshness. Tidak ada automatic adoption atau bootstrap dari absence records. Gunakan lineage blueprint baru dengan Bench/human review saat ini bila history lama tidak dapat dibuktikan.
- Replacement normal memerlukan comparison tanpa critical regression. Perubahan suite/configuration/evidence format memerlukan intent `suite_transition=true`, reason, active admin authority, CAS dan passing evaluation pada konfigurasi authoritative baru. Exception ini hanya berlaku untuk incompatibility suite/evidence yang nyata; tidak bisa digunakan untuk mengesampingkan critical failure pada konfigurasi yang sama. Acceptance merupakan tindakan governance eksplisit, bukan silent reset.

### Contracts, comparability dan criticality

`EvaluationIdentity`, `AcceptedBaseline`, `RegressionPolicy`, `RegressionComparison`, `ScenarioComparison`, `GraderComparison`, `RegressionFinding` dan `MetricDelta` berada pada shared Bench contract. Comparison menyimpan baseline/candidate identities, tenant/project/blueprint, canonical suite/version/hash, timestamp, scores/delta, scenario/grader state transitions, metric deltas, provenance differences, typed limitations, machine reasons dan promotion decision.

State comparison adalah `bootstrap`, `baseline_required`, `comparable`, `incompatible`, `invalid` atau `unverifiable`. `comparable` hanya menyatakan identities/evidence dapat dibandingkan; `promotion_blocked` dan critical findings tetap harus dibaca. Candidate yang gagal quality gate juga diblokir, walaupun bukan regression baru. Engine membandingkan scenario ID/version dan grader ID/type/version, bukan urutan array. Missing/new scenarios, missing/changed graders, suite/version/config hash change, mixed evidence formats dan wrong execution scope tidak menghasilkan PASS.

Before comparison, repository memverifikasi current receipt/history chain, unchanged source configuration/evaluation, candidate dan baseline HMAC, grader recomputation dan typed aggregate. Evidence dari suite lama tetap terikat pada accepted snapshot; jika registry berevolusi, receipt historis diperiksa tanpa melonggarkan registry current dan comparison dinyatakan incompatible sampai ada governed transition.

Criticality generik menggabungkan required scenarios **dari baseline dan candidate**, required suite scenarios, serta `RegressionPolicy.critical_scenarios/critical_graders`. PASS menjadi POLICY_VIOLATION, INVALID_EVIDENCE, UNVERIFIABLE atau RUNTIME_ERROR kritis; required/critical scenario FAIL juga kritis. Grader integrity/model identity/forbidden action/approval/idempotency tidak boleh menjadi soft regression. Engine tidak mengenal nama/category/ID Research Safety. Optional quality failure dapat dilaporkan tanpa blocking bila reference **dan baseline** memang mengizinkannya.

Score delta dihitung dari verified aggregates. Latency merupakan total scenario seconds; tokens memakai integer usage evidence; cost dan named resources dijumlahkan hanya jika seluruh scenario menyediakan measurement yang valid. Missing evidence menghasilkan `unavailable`, tanpa angka rekaan. Non-finite/negative/malformed measurements menghasilkan `invalid`. Metric increases dilaporkan sebagai soft findings kecuali policy menentukan max increase/drop. Required regression metric yang tidak comparable memblokir gate. Model/provider/backend/gateway change dicatat sebagai provenance difference; ini bukan BN-08 model comparison framework.

Suite policy optional masuk ke suite hash jika dikonfigurasi. Default tanpa policy mempertahankan suite hashes sebelum BN-06, sehingga format-2 evidence existing tetap readable dengan serialization/HMAC yang sama.

### Persistence, locking dan promotion enforcement

`bench_comparisons` menyimpan seluruh typed comparison dengan HMAC domain `bench_regression`, scoped index serta baseline/candidate references. Comparison ID mengikat accepted receipt, candidate persisted evidence fingerprint, current suite hash, current evaluation reference dan bootstrap history. Stored result tidak menjadi authority tunggal: repository menghitung ulang comparison, memeriksa HMAC/row bindings, dan menolak stale result setelah baseline/evaluation berubah. Tampered cached comparison menjadi signed invalid decision yang baru; evidence lama tidak ditulis ulang.

Evaluation completion menyimpan comparison termasuk failed/critical results. Gate di `BenchRepository.get_latest_passing_evaluation` berlaku untuk candidates dan digunakan oleh Factory approve/publish serta `ApprovalEngine.current_evidence`, termasuk direct Core callers. Core approval baru mengikat `regression_comparison_id` di dalam signed approval. Baseline berubah sesudah approval memerlukan human review baru, meskipun recomputation candidate masih non-regressing. Published/deprecated approval verification membaca evidence yang sudah dipublikasikan; advancement baseline tidak mencabut assignment versi lama atau mengizinkan republish untuk mundur ke baseline lama.

Semua governance writer mengunci blueprint sebelum version/membership. SQLite memakai existing `BEGIN IMMEDIATE`; PostgreSQL memakai row locks. Baseline acceptance memakai CAS dan unique scoped generation. Dua publication yang ditinjau terhadap baseline sama diserialisasi: publication pertama memajukan baseline; review kedua menjadi stale. Baseline advancement, current pointer, immutable publication dan audit commit/rollback bersama. Denied Factory/direct Core promotion dicatat sesudah transaksi gagal di-rollback, sehingga blocking evidence/audit tidak hilang.

Events memakai Core audit dengan ID/hash/count/reason, tanpa raw model output: `bench.baseline.accepted`, `bench.baseline.superseded`, `bench.regression.compared`, `bench.regression.critical`, `bench.promotion.blocked`, serta `factory.version.published` yang mengikat baseline ID.

### API, UI dan legacy

Studio menyediakan `POST /api/projects/{project_id}/blueprints/{blueprint_id}/baseline`. Extra client truth fields ditolak. Snapshot menampilkan current `accepted_baselines`, candidate `regression`, serta authoritative `bench_eligible`/`governance_valid`. Bench JSON/SSE completion menyertakan persisted evaluation dan current regression. Approval review hash diperiksa di transaksi Factory yang sama dengan gate; publication endpoint memakai authority Factory langsung.

Bench UI menampilkan Accepted Baseline vs Candidate, versi/evaluation/suite, score delta, scenario/grader regressions, critical count, latency/token/cost/resources availability dan block/eligible/bootstrap state. Acceptance dan suite transition memerlukan intent admin eksplisit. Tabel comparison dapat difokuskan keyboard agar horizontal scrolling tetap accessible di mobile. Client tidak menentukan baseline truth atau regression severity.

Format-1 evidence valid tetap readable dan dapat menjadi **limited baseline**: scenario states serta latency/tokens saja, tanpa fabricated grader/action/cost/resource evidence. Limitations disimpan dalam receipt/comparison. Format 1 dan 2 tidak comparable; upgrade ke generic graders membutuhkan governed suite/evidence transition. Historical Core approval HMAC tanpa comparison field tetap dapat diverifikasi untuk published sources; unpublished promotion memerlukan approval baru yang mengikat current comparison.

Sesudah `013_history_integrity`, eligibility tersebut juga memerlukan independently committed
baseline origin/head. HMAC receipt/chain tidak cukup bila suffix dapat dihapus. Current baseline
memverifikasi ID, generation dan hash signed receipt terhadap Core durable commitment di luar
application DB. Delete newest baseline + restore older pointer, delete all history + bootstrap,
stale signed receipt replay, missing/corrupt commitment dan pending intent memblokir acceptance,
approval dan promotion. SQLite UPDATE/DELETE/REPLACE guards serta PostgreSQL mutation/TRUNCATE
guards memperkuat persistence. Signed evaluation dan immutable version payload tidak berubah.
Lihat [authority boundary dan compatibility](governance-history-integrity.md); live PostgreSQL
privileges/concurrency belum diverifikasi dan fondasi hosted belum boleh dibekukan.

Migration `011_bench_baseline_regression` mengikuti head `010_agent_definition_contracts`, menambah dua tables, scoped generation uniqueness/indexes, blueprint current pointer dan approval comparison reference. Upgrade tidak mengubah evaluation historis; downgrade menghapus domain baseline/comparison baru dan kolom referencenya. Tests mencakup SQLite upgrade/downgrade/upgrade, retained historical evaluation, foreign-key integrity, metadata parity, dan PostgreSQL offline SQL compilation. PostgreSQL runtime concurrency belum dijalankan terhadap live cloud database.

API Bench JSON/SSE tetap memakai routes, consent request dan persisted completion yang sama, dengan tambahan typed evidence/result fields. Preflight budget mengikuti semua scenario suite referenced. Snapshot menyediakan `evaluation_suites` berupa catalog metadata/scenario identities tanpa endpoint untuk memasukkan arbitrary suite atau grader. Frontend typing, scenario canvas, stream indexes, aggregate status dan wording mengikuti metadata suite. Compatibility fallback Research Safety hanya mendukung older snapshot/display callers.

## File yang diubah

| Area | Files |
|---|---|
| Generic contracts | `packages/contracts/bench.py`, `agent.py`, `runtime.py`, `__init__.py` |
| Bench domain | `modules/bench/runner.py`, `scenarios.py`, `quality_gate.py`, `registry.py`, `graders.py`, `evidence.py`, `aggregation.py` |
| Factory/Core authority | `modules/agent_factory/service.py`, `modules/core/approvals/engine.py` |
| Persistence/runtime dependencies | `database/repositories/bench_repo.py`, `database/connection.py`, `pyproject.toml` |
| API | `services/api/studio.py` |
| Frontend | `apps/web/src/lib/types.ts`, `lib/studio-state.ts`, `features/bench.tsx`, `components/canvas/canvas-builders.ts` |
| Regression tests | `tests/bench_fixtures.py`, `tests/unit/test_bench_graders.py`, `tests/integration/test_bench_engine.py`, `tests/security/test_bench_engine_integrity.py`, `apps/web/src/test/bench-suite-contract.test.tsx` |
| Documentation | `README.md`, `docs/bench-engine.md`, `docs/agent-factory-contracts.md`, `docs/studio.md` |

Files BN-06 (31 files), terpisah dari daftar generalization historis di atas:

| Area | Files |
|---|---|
| Contracts/engine | `packages/contracts/bench.py`, `packages/contracts/approval.py`, `modules/bench/regression.py` |
| Factory/Core | `modules/agent_factory/service.py`, `modules/core/approvals/engine.py`, `modules/core/permissions/engine.py` |
| Persistence | `database/schema.py`, `database/connection.py`, `database/repositories/agent_repo.py`, `approval_repo.py`, `bench_repo.py`, `bench_regression_repo.py`, `database/migrations/versions/011_bench_baseline_regression.py` |
| API/frontend | `services/api/studio.py`, `apps/web/src/lib/types.ts`, `lib/studio-state.ts`, `features/bench.tsx`, `components/workspace.tsx`, `test/bench-regression.test.tsx`, `apps/web/e2e/studio.spec.ts` |
| Backend tests | `tests/unit/test_bench_regression.py`, `tests/integration/test_bench_baseline_regression.py`, `test_bench_regression_api.py`, `test_schema_migration_compatibility.py`, `tests/security/test_bench_baseline_authority.py`, `test_bench_engine_integrity.py` |
| Documentation | `README.md`, `STATUS.md`, `docs/bench-engine.md`, `docs/agent-factory-contracts.md`, `docs/studio.md` |

Tidak ada production runtime adapter baru atau subsystem approval tambahan.

## Validation

Perintah regresi yang dapat dijalankan dari checkout:

```powershell
python -m pytest -q --tb=short
Set-Location apps/web
npm.cmd run test
npm.cmd run build
npm.cmd run test:e2e
```

Backend full suite mencakup seluruh Bench/Factory lifecycle, security negatives, tenant isolation, API/integration/E2E dan migration compatibility tests. Test suite generik menggunakan JSON structured-analysis dengan dua domain dan tanpa content regex melalui runner, persistence, Core approval dan publish yang sama. Production source tidak mengimpor test runtime.

Hasil generalization awal pada 8 Oktober 2026 (baseline commit `eb3cc22`):

| Command | Hasil |
|---|---|
| `python -m pytest -q` sebelum refactor | 308 passed, 5 skipped |
| `python -m pytest -q tests/unit/test_bench_graders.py tests/integration/test_bench_engine.py tests/security/test_bench_engine_integrity.py tests/security/test_bench_evidence_integrity.py --tb=short` setelah penguatan grants/tenant | 133 passed |
| `python -m pytest -q --tb=short` setelah implementation | **429 passed, 5 skipped**, 114.42 detik; 10 warnings deprecation existing |
| `npm.cmd run test` | **61 passed**, 10 test files |
| `npm.cmd run build` | TypeScript dan Vite berhasil; warning ukuran bundle existing tetap ada |
| `npm.cmd run test:e2e` | **14 passed**, 2.9 menit; HTTP/Core/runtime terisolasi, browser lifecycle dan accessibility |
| `git diff --check` | Tidak ada whitespace error |

Penambahan backend berjumlah 121 tests: 83 unit grader/contract tests, 20 generic-engine integration tests, dan 18 integrity/security tests. Frontend menambah empat tests suite metadata, dynamic scenarios dan aggregate policy. Full backend run mencakup semua direktori unit, integration, security dan e2e, termasuk lifecycle Factory serta compatibility migrasi SQLite/PostgreSQL existing. Live model tests tetap memerlukan opt-in existing dan tidak dijalankan sebagai regression lokal; hasil ini tidak mengklaim live-provider verification.

`main` dan `origin/main` tetap pada `630cbc96d728a49a64247ad2b88978529a7cbbad`; BN-06 hanya dikerjakan pada `development`. Tidak ada merge, rebase atau push pada pekerjaan ini.

Validasi BN-06 memakai full backend suite yang mencakup seluruh Bench/Factory lifecycle, security, integration dan backend E2E. Dedicated tests mencakup stable identity comparison, all unsafe transitions, metric deltas/unavailable values, scoped acceptance, stale/current authority, direct Core bypass attempts, latest failure, CAS concurrency, concurrent publication, rollback publication/baseline/audit, historical HMAC compatibility, suite/format transition dan tampering. Frontend tests serta Playwright menggunakan API/Core/SQLite dan isolated runtime aktual.

Hasil aktual BN-06 pada 8 Oktober 2026:

| Command | Hasil aktual |
|---|---|
| `python -m pytest tests/unit/test_bench_regression.py tests/integration/test_bench_baseline_regression.py tests/integration/test_bench_regression_api.py tests/security/test_bench_baseline_authority.py tests/integration/test_schema_migration_compatibility.py -q --tb=short` | **97 passed**, 60.45 detik; 15 existing deprecation warnings |
| `python -m pytest -q --tb=short` | **523 passed, 5 skipped**, 171.16 detik; 19 FastAPI/httpx dan Alembic configuration deprecation warnings |
| `npm.cmd run test` | **64 passed**, 11 files |
| `npm.cmd run build` | TypeScript/Vite berhasil; existing warning bundle >500 kB |
| `npm.cmd run test:e2e` | **15 passed**, 3.0 menit; HTTP/Core/SQLite, browser lifecycle, mobile/dark/accessibility, baseline vs candidate |
| `git diff --check` | Tidak ada whitespace error |

BN-06 menambahkan 94 backend tests di atas baseline 429: 54 unit comparison/policy, 14 lifecycle/concurrency integration, 22 authority/security, 2 API, dan 2 migration tests. Existing historical Research Safety security test diperkuat dengan limited-baseline dan governed format-1 → format-2 transition. Assertion existing tidak diperlonggar. Frontend menambah tiga comparison tests dan satu browser scenario. Kegagalan Playwright awal pada setup empty state, selector ambiguous dan keyboard access untuk tabel comparison diperbaiki; run terakhir seluruhnya lulus.

Live model/provider tests tidak diaktifkan dan PostgreSQL divalidasi dengan offline SQL compilation, bukan live cloud connection. Downgrade migration mempertahankan signed evaluations, tetapi menghapus baseline/comparison domain baru beserta approval comparison references; deployment yang membutuhkan governance history harus mempertahankan backup sebelum downgrade. Re-upgrade tidak mengarang kembali baseline history atau approval bindings yang sudah dihapus.

## Residual risks dan pekerjaan di luar scope

- Suite regex Research Safety tetap merupakan gate awal, bukan proof keamanan menyeluruh atau kualitas ilmiah.
- Completeness/action observations dan measurement extensions memerlukan adapter yang terpercaya. Current Hermes tidak mengklaim evidence yang belum didukung.
- Approval authority yang dicabut, suite/config yang berubah, atau signing key yang hilang dapat menggugurkan stored eligibility; ini fail-closed behaviour yang disengaja.
- Incident replay/corpus promotion, rollback registry, full model comparison BN-08, trace viewer/export, Brief, Relay, desktop packaging, billing, production authentication dan branch protection tetap di luar scope.
- Receipt/history serta comparison direvalidate saat governance; biaya validasi bertambah dengan panjang baseline chain dan jumlah scenarios/graders. History pagination/retention dan optimisasi belum diperlukan untuk workload lokal saat ini.
- Private controlled requirement documents belum tersedia dalam checkout. Findings runtime di luar scope tidak diperluas menjadi implementation baru.
## Operational rollback dan baseline separation (AF-07)

Known-good assignment rollback memakai exact historical publication authority dan memverifikasi
ulang signed Bench evidence serta frozen publication comparison terhadap baseline yang direview
saat publication. `verify_publication_comparison()` menghitung ulang scenario/grader/metric result
dari persisted evidence; current baseline tidak diperlukan sebagai rollback target.

Forward approval/publication tetap memakai current accepted baseline dan existing BN-06 gate.
Rollback tidak menjalankan comparison terbalik, mengubah evaluation atau memundurkan baseline.
Perubahan current baseline adalah governed Bench action yang terpisah. Explicit accepted evaluation
tanpa publication tidak memenuhi known-good. Lihat [Factory registry/rollback contracts](agent-factory-contracts.md#8-version-registry-dan-known-good-rollback-af-07)
untuk publication receipts, assignment history, legacy limits dan test evidence.
