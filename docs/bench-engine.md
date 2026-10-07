# Generic Bench Evaluation Engine

Tanggal validasi: 8 Oktober 2026. Branch kerja: `development`.

## Audit dan keputusan arsitektur

Audit mencakup contracts agent/Bench/runtime/approval, runner dan quality gate, lifecycle Factory, Core approval/permissions/evidence/idempotency, repositories/schema/migrations, Hermes adapter, API Studio, frontend Bench, serta tests unit/integration/security/E2E. Dokumen README, AGENTS, SECURITY, kontrak Factory, governance, Studio dan laporan Bench dibaca. Checkout `aryn-docs` hanya menyediakan indeks; dokumen PRD/ARCH/TECH/SEC privat yang disebut README belum tersedia. Tidak ada ID requirement privat yang direka.

Sebelumnya runner dan quality gate menilai regex Research Safety secara langsung; Factory dan preflight API memaksakan empat skenario; registry hanya menyelesaikan satu suite. Persistence sudah mempunyai detail JSON, provenance JSON, HMAC tenant-scoped, dan revalidation sebelum approval/publish. Jalur tersebut dipertahankan.

Alur sekarang:

`EvaluationReference → authoritative suite registry → BenchScenario → runtime execution → deterministic graders → ScenarioResult → suite aggregate → promotion decision → persisted evidence revalidation → Core approval → publish`

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

`details_json` menyimpan seluruh execution/grader/scenario evidence. `provenance_json` menyimpan format, suite/config hash, requested model, adapter, output contract, agent boundaries, evaluation reference, suite aggregate, gate decision dan outer attestation. Repository mengikat policy snapshots ke current canonical agent configuration dan tenant, lalu menghitung ulang grader/agregat. HMAC original format historis dipertahankan. Database schema dan Alembic head tidak berubah; tidak diperlukan migration.

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

Hasil aktual pada 8 Oktober 2026:

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

`main` dan `origin/main` tetap pada `630cbc96d728a49a64247ad2b88978529a7cbbad`; tidak ada merge, rebase, push, atau mutation branch tersebut. Perubahan implementasi berada pada working tree branch `development`. `STATUS.md` tidak diubah.

## Residual risks dan pekerjaan di luar scope

- Suite regex Research Safety tetap merupakan gate awal, bukan proof keamanan menyeluruh atau kualitas ilmiah.
- Completeness/action observations dan measurement extensions memerlukan adapter yang terpercaya. Current Hermes tidak mengklaim evidence yang belum didukung.
- Approval authority yang dicabut, suite/config yang berubah, atau signing key yang hilang dapat menggugurkan stored eligibility; ini fail-closed behaviour yang disengaja.
- Tidak ada baseline/candidate comparison, regression history, incident replay/corpus promotion, rollback registry, Brief, Relay, desktop packaging, billing, production authentication, atau perubahan branch protection.
- Private controlled requirement documents belum tersedia dalam checkout. Findings runtime di luar scope tidak diperluas menjadi implementation baru.
