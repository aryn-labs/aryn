# Domain Contract Agent Factory — ARYN

Dokumen ini mendefinisikan canonical domain contract untuk **Agent Factory** pada ARYN, yang mencakup kontrak tipe, kebijakan keamanan (*security policies*), skema penyimpanan database, representasi kanonikal payload hash, serta aturan lifecycle yang mengikat seluruh subsistem ARYN.

---

## 1. Prinsip Desain & Invarian Keamanan

1. **First-Class Typed Contracts**: Seluruh atribut penting definisi agent (`objective`, `role`, `owner`, `output_contract`, `constraints`, `tool_policy`, `model_policy`, `budget_policy`, `schema_version`, `evaluation_reference`) dimodelkan sebagai typed domain models yang tervalidasi, bukan loose dictionary di dalam `metadata`.
2. **Immutability Versi Terpublikasi (*Immutable Published Version*)**: Versi agent yang berstatus `published` bersifat strictly read-only. Setiap perubahan konfigurasi harus menghasilkan versi baru (`draft`). Integritas ini dijaga secara berlapis:
   - Validasi ORM event listener (`protect_published_configuration`).
   - Cryptographic payload hash verification (`verify_integrity()`).
3. **Explicit Grant & Deny-by-Default Tool Policy**: Akses tool tidak boleh implisit. Setiap grant harus terdaftar eksplisit dalam `tool_grants`. Jika tool berada dalam `forbidden_tools`, versi ditolak pada tahap validasi (`ForbiddenToolError`).
4. **Anti-Silent-Fallback Model Policy**: Sesuai ADR-005 dan tata kelola ARYN, fallback model tanpa persetujuan eksplisit dilarang (`allow_fallback = False`). Parameter model divalidasi terhadap model primer dan daftar model yang diizinkan.
5. **Exact Payload Hash Approval Binding**: Persetujuan manusia (*human approval*) mengikat exact SHA-256 hash dari representasi kanonikal versi agent, evaluasi Bench yang lulus dan terverifikasi, serta tenant/project boundary.
6. **No Self-Approve / No Self-Publish**: Agent tidak memiliki kapabilitas menyetujui atau menerbitkan versinya sendiri. Seluruh transisi status lifecycle memerlukan aktor manusia yang terautentikasi dan memiliki permission yang sesuai.
7. **Authoritative Bench Evaluation Reference**: Agent version mendefinisikan `evaluation_reference` yang mengikat suite, versi, skor minimum, dan daftar skenario wajib (`required_scenarios`). Evaluasi Bench diverifikasi secara fail-closed terhadap referensi ini; evaluasi yang tidak cocok ditolak.
8. **Perlindungan Backward Compatibility & Anti-Bypass Legacy**: Versi baru menghitung SHA-256 menggunakan `canonical_format: 3`. Format legacy v2 hanya diizinkan untuk pembacaan historis (*read-only*), dengan proteksi ketat di mana versi legacy yang memiliki modifikasi field kustom baru langsung ditolak sebagai korup/tampered. Seluruh transisi lifecycle baru (`evaluate`, `approve`, `publish`) mewajibkan Format 3 kanonikal.

---

## 2. Struktur Domain Contract

Domain contract didefinisikan pada `packages/contracts/agent.py` dan `packages/contracts/bench.py`, serta diekspor melalui `packages/contracts/__init__.py`.

### 2.1 Sub-kontrak Kebijakan & Spesifikasi

- **`AgentOutputContract`**:
  - `format`: Format respons yang diharapkan (`text`, `json`, `markdown`, default: `"text"`).
  - `schema_definition`: JSON schema opsional untuk format terstruktur (`Optional[Dict[str, Any]] = None`).
  - `required_sections`: Daftar bagian yang wajib ada pada respons (`List[str] = []`).
  - `description`: Deskripsi instruksi format (`Optional[str] = None`).
  - `strict`: Boolean yang menentukan apakah schema harus divalidasi secara ketat (default: `False`).

- **`AgentConstraints`**:
  - `disallowed_actions`: Daftar aksi/operasi yang dilarang dieksekusi oleh agent (`List[str] = []`).
  - `operational_rules`: Aturan batasan operasional (`List[str] = []`).
  - `require_evidence_citation`: Mewajibkan sitasi bukti pada setiap temuan/klaim (default: `True`).
  - `max_execution_time_seconds`: Batas waktu maksimum eksekusi interaksi dalam detik (default: `120`, rentang: 1 s/d 3600).

- **`AgentToolPolicy`**:
  - `tool_grants`: Daftar tool yang diizinkan secara eksplisit (`List[str] = []`).
  - `forbidden_tools`: Daftar tool yang secara tegas dilarang (default: `["terminal", "file", "browser", "code_execution", "bash", "shell", "os_exec"]`).
  - `deny_by_default`: Kebijakan default deny (default: `True`).
  - `network_access`: Izin akses jaringan eksternal (default: `False`).
  - `file_write_access`: Izin modifikasi file sistem (default: `False`).
  - `code_execution`: Izin eksekusi kode dinamis (default: `False`).
  - Method `is_tool_allowed(tool_name: str) -> bool`: Mengembalikan `True` jika tool ada di `tool_grants` dan tidak berada di `forbidden_tools`.
  - Method `validate_tool_grants() -> None`: Memvalidasi tidak ada tool terlarang yang diminta, jika ada raises `ForbiddenToolError`.

- **`AgentModelPolicy`**:
  - `primary_model`: Model ID yang didelegasikan untuk inferensi (default: `"mock-fast"`).
  - `provider`: Provider inference gateway (default: `"9router"`).
  - `allowed_models`: Whitelist model alternatif yang diizinkan (`List[str] = []`).
  - `temperature`: Hyperparameter temperature (default: `0.7`, rentang: 0.0 s/d 2.0).
  - `max_tokens`: Alokasi token maksimum (default: `2048`, rentang: 1 s/d 32768).
  - `allow_fallback`: Flag fallback runtime (default: `False`, tidak boleh fallback diam-diam).
  - `stop_sequences`: Sequence penanda berhenti inferensi (`List[str] = []`).
  - Method `validate_model(requested_model: str) -> None`: Memastikan requested model sesuai primary model atau terdapat dalam allowed models.

- **`AgentBudgetPolicy`**:
  - `max_tokens_per_run`: Batas token per single run (default: `4096`, rentang: 1 s/d 100000).
  - `max_turns`: Batas turn percakapan multi-turn (default: `10`, rentang: 1 s/d 100).
  - `max_cost_usd`: Batas biaya estimasi per run dalam USD (default: `0.50`).
  - `timeout_seconds`: Batas waktu eksekusi run sebelum timeout (default: `120`, rentang: 1 s/d 3600).

- **`AgentEvaluationReference`**:
  - Canonical Authority: `packages/contracts/bench.py`.
  - `suite_id`: Identifier test suite Bench (default: `"research-safety-1.2.0"`, alias recognized: `"research-safety"`).
  - `evaluation_version`: Versi test suite evaluator (default: `"1.2.0"`).
  - `min_score_threshold`: Skor kelulusan minimum (default: `1.0` / 100%).
  - `required_scenarios`: Daftar skenario yang wajib lulus. Default berisi 4 skenario Bench aktual:
    - `scen_safety_injection_defense`
    - `scen_tool_confinement_defense`
    - `scen_research_accuracy_synthesis`
    - `scen_grounded_abstention`
  - `evaluation_id`: Identifier evaluasi yang berhasil dijalankan (`Optional[str] = None`).
  - Validasi: Model validator `_validate_suite_and_scenarios` memeriksa `suite_id` terhadap `resolve_bench_suite_manifest()`, menolak `evaluation_version` yang tidak sesuai sedini mungkin, dan memvalidasi seluruh elemen di `required_scenarios` terhadap skenario suite yang sah.

- **`AgentDefinition`**:
  - Model komposit yang menyatukan seluruh spesifikasi di atas:
    `schema_version`, `role`, `objective`, `owner`, `output_contract`, `constraints`, `tool_policy`, `model_policy`, `budget_policy`, `evaluation_reference`.

### 2.2 `AgentBlueprint`

Representasi template agent induk:
- `id`: Identifier unik blueprint (`abp_*`).
- `organization_id` & `project_id`: Batas isolasi multi-tenant.
- `name` & `slug`: Identitas dan slug URL.
- `description`: Deskripsi persona.
- `role`: Peran agent default (misal: "financial_analyst").
- `objective`: Objektif utama agent.
- `owner`: Principal pemilik blueprint.
- `created_by`: Aktor pembuat.
- `created_at` & `updated_at`: Timestamp ISO-8601.

### 2.3 `AgentVersion`

Representasi versi agent immutable yang memiliki hash kanonikal:
- Atribut runtime dasar: `id`, `blueprint_id`, `version_number`, `status`, `system_prompt`, `model`, `tool_grants`, `temperature`, `max_tokens`, `metadata`, `payload_hash`.
- Atribut typed definition lengkap: `schema_version`, `role`, `objective`, `owner`, `output_contract`, `constraints`, `tool_policy`, `model_policy`, `budget_policy`, `evaluation_reference`.
- Sinkronisasi otomatis dua arah antara scalar fields (`model`, `temperature`, `max_tokens`, `tool_grants`) dan nested policy objects (`model_policy`, `tool_policy`).
- Property `.definition` yang memproyeksikan seluruh spesifikasi menjadi objek `AgentDefinition`.
- Property `.canonical_format` yang mengembalikan format integritas (`3` untuk kanonikal saat ini, `2` untuk legacy v2 bersih, `0` jika korup/tidak valid).

---

## 3. Bench Authority & Suite Registry

Bench menggunakan generic contracts pada `packages/contracts/bench.py`, immutable server-owned registry pada `modules/bench/registry.py`, dan catalog definisi suite pada `modules/bench/scenarios.py`. Research Safety merupakan suite pertama di atas generic runner, graders, evidence validator dan aggregation.

- `EvaluationReference` dan `OutputContract` adalah shared contracts. Names `AgentEvaluationReference` dan `AgentOutputContract` tetap tersedia sebagai aliases; canonical format 3 serialization/defaults tidak berubah.
- `resolve_bench_suite_manifest()` dan `get_supported_bench_suite_ids()` tetap merupakan compatibility entrypoints ke authoritative registry. Constants `RESEARCH_SAFETY_*` tetap tersedia sebagai compatibility defaults, bukan branching rules dalam engine/Factory.
- Version/reference dan required scenario identities divalidasi terhadap manifest. Untuk reference suite lain, omitted version/required scenarios berasal dari manifest tersebut.
- Factory meminta Bench menyelesaikan dan menjalankan seluruh suite referenced sebelum promotion. Factory tidak mengetahui isi Research Safety.
- Quality gate menghitung ulang setiap grader, scenario/suite aggregate dan promotion decision dari execution evidence; stored booleans/scores bukan authority.
- Generic evidence format 2 menyimpan execution HMAC, individual grader evidence, policy snapshots, suite aggregate dan gate decision dalam kolom JSON persistence existing. Original format 1 serialization/HMAC tetap dapat diverifikasi untuk historical evidence; new evaluation writes wajib format 2.

Lihat [generic Bench engine](bench-engine.md) untuk scenario/grader contracts, runtime observation coverage, Research Safety compatibility, fail-closed rules dan validation evidence.

---

## 4. Skema Database & Migrasi

### 4.1 Tabel ORM (`database/schema.py`)

- **`agent_blueprints` (`AgentBlueprintModel`)**:
  - Kolom: `role` (Text, nullable), `objective` (Text, nullable), `owner` (String(64), nullable).
- **`agent_versions` (`AgentVersionModel`)**:
  - Kolom: `schema_version` (String(32), default `"1.0.0"`), `role` (String(64), default `"general_agent"`), `objective` (Text, default `""`), `owner` (String(64), nullable), `output_contract_json` (Text, default `"{}"`), `constraints_json` (Text, default `"[]"`), `tool_policy_json` (Text, default `"{}"`), `model_policy_json` (Text, default `"{}"`), `budget_policy_json` (Text, default `"{}"`), `evaluation_reference_json` (Text, default `"{}"`).
- **ORM Immutability Listener**:
  `protect_published_configuration` mendengarkan event `before_update`. Jika status adalah `published`, setiap upaya mutasi kolom konfigurasi langsung dibatalkan dengan `RuntimeError("Published agent versions are immutable...")`.

### 4.2 Migrasi Alembic (`database/migrations/versions/010_agent_definition_contracts.py`)

- Revises: `009_gateway_provenance`.
- `upgrade()`:
  - Menambahkan kolom `role`, `objective`, `owner` pada `agent_blueprints` menggunakan `op.add_column`.
  - Menambahkan kolom-kolom definisi (`schema_version`, `role`, `objective`, `owner`, `output_contract_json`, `constraints_json`, `tool_policy_json`, `model_policy_json`, `budget_policy_json`, `evaluation_reference_json`) pada `agent_versions` menggunakan `op.add_column` dengan server defaults.
- `downgrade()`:
  - Menghapus kolom yang ditambahkan menggunakan `op.drop_column`.

---

## 5. Representasi Kanonikal Payload Hash (Format 3) & Hardening Legacy

Integritas versi dihitung dengan SHA-256 dari representasi JSON kanonikal Format 3 dengan 20 kunci berurutan alfabetis dan tanpa spasi redundan (`sort_keys=True`, `separators=(",", ":")`):

```json
{
  "budget_policy": {
    "max_cost_usd": 0.5,
    "max_tokens_per_run": 4096,
    "max_turns": 10,
    "timeout_seconds": 120
  },
  "canonical_format": 3,
  "constraints": {
    "disallowed_actions": [],
    "max_execution_time_seconds": 120,
    "operational_rules": [],
    "require_evidence_citation": true
  },
  "evaluation_reference": {
    "evaluation_id": null,
    "evaluation_version": "1.2.0",
    "min_score_threshold": 1.0,
    "required_scenarios": [
      "scen_safety_injection_defense",
      "scen_tool_confinement_defense",
      "scen_research_accuracy_synthesis",
      "scen_grounded_abstention"
    ],
    "suite_id": "research-safety-1.2.0"
  },
  "id": "av_0123456789abcdef",
  "blueprint_id": "abp_0123456789abcdef",
  "max_tokens": 2048,
  "metadata": {},
  "model": "mock-fast",
  "model_policy": {
    "allow_fallback": false,
    "allowed_models": [],
    "max_tokens": 2048,
    "primary_model": "mock-fast",
    "provider": "9router",
    "stop_sequences": [],
    "temperature": 0.7
  },
  "objective": "Perform governed domain research with citations.",
  "output_contract": {
    "description": null,
    "format": "text",
    "required_sections": [],
    "schema_definition": null,
    "strict": false
  },
  "owner": "usr_lead",
  "role": "financial_analyst",
  "schema_version": "1.0.0",
  "system_prompt": "You are a research analysis agent.",
  "temperature": 0.7,
  "tool_grants": [],
  "tool_policy": {
    "code_execution": false,
    "deny_by_default": true,
    "file_write_access": false,
    "forbidden_tools": [
      "terminal",
      "file",
      "browser",
      "code_execution",
      "bash",
      "shell",
      "os_exec"
    ],
    "network_access": false,
    "tool_grants": []
  },
  "version_number": "1.0.0"
}
```

### 5.1 Aturan Verifikasi Integritas (`verify_integrity`)

1. **Format 3 Kanonikal**: Standar wajib untuk seluruh versi baru. Jika `payload_hash == calculate_payload_hash()`, integritas valid.
2. **Format 2 Legacy**:
   - Hanya diizinkan pada pembacaan (*read mode*) rekaman historis yang sudah ada.
   - **Anti-Bypass Protection**: Jika `_has_custom_definition_fields()` bernilai `True` (artinya ada perbedaan pada `role`, `objective`, `owner`, `output_contract`, `constraints`, `tool_policy`, `model_policy`, `budget_policy`, `evaluation_reference`), verifikasi format legacy langsung menolak dengan `VersionIntegrityError`. Modifikasi atribut bertipe baru tidak dapat diselundupkan di balik hash legacy.
3. **Strict Canonical Lifecycle Gate**:
   - Parameter `verify_integrity(require_canonical=True)` mewajibkan Format 3.
   - Seluruh tahapan transisi aktif (`evaluate_version_with_bench`, `approve_version`, `publish_version`) memeriksa `version.canonical_format == 3`. Versi legacy draft/rejected/approved ditolak dari siklus hidup baru dan harus dibuatkan versi baru ber-Format 3.

---

## 6. Service Layer (`AgentFactoryService`)

Service layer di `modules/agent_factory/service.py` mengorkestrasi:
- **Pewarisan Persona Blueprint**: Jika pembuatan versi tidak menyertakan `role`, `objective`, atau `owner`, nilainya secara otomatis diwarisi dari parent `AgentBlueprint`.
- **Validasi Kebijakan & Registry Bench**:
  - `model_policy.validate_model(model)` dieksekusi sebelum commit.
  - `tool_policy.validate_tool_grants()` memastikan tidak ada tool terlarang yang diminta.
  - `evaluation_reference` divalidasi sedini mungkin terhadap suite manifest registry dan scenario IDs.
- **Audit Logging**: Mencatat event audit terstruktur `agent_factory.blueprint_created`, `agent_factory.version_created`, `agent_factory.version_evaluated`, dan `agent_factory.version_published` dengan metadata lengkap.
- **Integrasi Approval & Publikasi**: Memastikan versi ber-Format 3 kanonikal, hasil Bench terbaru valid terhadap `evaluation_reference`, dan current baseline regression gate tidak diblokir. Core approval mengikat exact payload hash, evaluation ID dan comparison ID; perubahan baseline memerlukan human review baru. Publication dan advancement baseline/audit commit atomik. Factory tidak mengetahui isi Research Safety. Lihat [baseline lifecycle, bootstrap dan compatibility](bench-engine.md#accepted-baseline-dan-regression-governance-bn-06).

---

## 7. API Service & Frontend Typing

- **API Models (`services/api/studio.py`)**:
  - `BlueprintInput`: Menerima `name`, `description`, `role`, `objective`, `owner`.
  - `VersionInput`: Menerima `system_prompt`, `model`, `temperature`, `max_tokens`, `tool_grants`, `role`, `objective`, `owner`, `schema_version`, `output_contract`, `constraints`, `tool_policy`, `model_policy`, `budget_policy`, `evaluation_reference`.
- **Frontend Types (`apps/web/src/lib/types.ts`)**:
  - Interface TypeScript `OutputContract`, `Constraints`, `ToolPolicy`, `ModelPolicy`, `BudgetPolicy`, `EvaluationReference`.
  - Menyediakan pengetikan untuk antarmuka Studio Workbench dan Canvas Inspector.

## 8. Version Registry dan known-good rollback (AF-07)

Audit pada `development` dimulai dari `48f97592024ada1aad8f5a7906a6d84f1207c86a`.
AgentVersion sudah immutable, Core approval sudah mengikat payload/evaluation/comparison,
dan publication sudah memajukan accepted Bench baseline secara atomik. Assignment hanya
menyimpan `version_id`; run request membawa metadata versi tetapi durable run row belum
menyimpannya, dan UI historical run memakai pointer assignment saat ini. Dokumen korporat
PRD/architecture/security pada sibling `aryn-docs` masih scaffold; implementasi mengikuti
contracts, security tests dan technical documentation aktual repository.

Registry tetap merupakan projection AgentVersion dan authority existing, bukan registry
kedua. `VersionRegistryEntry` memuat lifecycle, SHA-256 checksum, created/published time,
publisher, Bench verification/pass state, approval, historical baseline/publication/comparison
references, current baseline indicator, active assignment count dan derived rollback eligibility.
Tidak ada kolom atau endpoint `known_good=true`.

### Known-good authority

`AgentActivationRepository.known_good()` memverifikasi ulang:

- organization/project/blueprint, canonical payload format 3 dan checksum;
- status **published**, publication timestamps dan human publisher yang mempunyai Core authority;
- latest passing persisted Bench evaluation, exact version evaluation reference, evidence HMAC,
  deterministic graders/aggregate dan quality gate;
- exact-payload/evaluation human Core approval, signature dan current approver authority;
- accepted historical baseline receipt, evaluation/configuration hashes dan predecessor chain;
- signed comparison yang direview pada publication, dengan deterministic recomputation terhadap
  baseline historisnya, bukan current baseline;
- immutable HMAC publication receipt yang mengikat semua reference di atas serta publisher/time.

Receipt publication baru ditulis hanya di transaction Factory yang sudah melewati approval
dan publish gates. ORM melindungi publication dan activation records dari update/delete.
Direct repository activation memeriksa permission dan verified target kembali; client flags
dan fabricated evidence tidak dapat menjadi authority. Immutable published/deprecated version
configuration dan status machine tetap berlaku. **Deprecated tetap terminal dan tidak eligible**.

Accepted baseline sebelum publication tidak cukup untuk known-good. Historical superseded
publication baseline tetap dapat digunakan. Evaluator yang tidak lagi supported, latest failure,
approval authority yang dicabut, kehilangan signing key atau evidence tampering menolak target.

### Operational activation dan rollback

Assignment adalah scope operasi. Version baru tetap di-publish melalui BN-06; creation assignment
tetap mekanisme existing untuk memakai publication baru. Scope ini tidak menambahkan deployment
orchestration atau forward-upgrade otomatis terhadap assignment yang sudah ada.

Assignment baru mempunyai initial signed activation origin. Table `assignment_transitions`
menyimpan append-only generation, from/to version IDs, actor, reason, requested/committed time,
idempotency identity/fingerprint, previous receipt/hash, stable assignment scope hash dan exact
known-good publication reference. `agent_assignments.current_transition_id` menunjuk history head.
History/pointer mismatch, missing origin atau HMAC mismatch ditolak. Assignment scope fields dan
version pointer tidak dapat diedit melalui ORM biasa tanpa governed transition.

Rollback:

1. Human admin mengirim target, **expected current version + expected transition**, reason dan key.
2. Core `agent:rollback` permission memverifikasi trusted USER identity dan active admin membership.
3. Server mengunci blueprint → assignment → target version → membership; memvalidasi history,
   expected state, same scope, target publication yang lebih awal dan known-good evidence.
4. Server menulis signed transition, mengganti assignment pointer dan mencatat requested,
   activated/committed audit dalam satu transaction. Kegagalan audit juga membatalkan pointer/history.
5. Duplicate exact actor/intent/key mengembalikan transition semula. Key dengan actor/target/reason
   atau reviewed state berbeda conflict. Review stale tidak diterapkan ke versi/activation lain.
6. Denial event disimpan setelah mutation transaction rollback, tanpa raw prompt atau credential.

Key scoped pada assignment. Repeating committed intent tidak mengaktifkan target lagi jika pointer
sudah berubah melalui operasi berikutnya. Retry tetap memverifikasi authority/evidence; permission
yang dicabut atau evidence yang berubah tidak diloloskan hanya karena key pernah berhasil.

Rollback A dari v2 ke v1 tidak mengubah assignment B, v1/v2 configuration, evaluation, approval,
comparison, lifecycle status atau Bench baseline. Baseline tetap evolution reference v2; runtime
assignment A memakai exact original v1. Tidak ada Bench run, reverse comparison atau fake PASS baru.

### Run provenance dan in-flight semantics

Pemilihan assignment/version dan durable Core claim dilakukan pada transaction/lock yang sama.
Claim menyimpan assignment ID, version ID, payload hash, transition reference, publication reference,
requested model dan request fingerprint dengan HMAC `assignment_run`. Tidak ada lock yang ditahan
saat inference. Run yang sudah di-claim tetap memakai request/config versi semula; rollback berlaku
untuk claim berikutnya. Duplicate run key terhadap configuration/activation berbeda tetap conflict.

RunResult dan snapshot memuat captured version identity. Repository memeriksa provenance dan ORM
melindungi field tersebut. Historical UI menggunakan signed captured version/hash, tidak mengambil
configuration dari mutable current assignment. Run lama tanpa captured provenance tetap readable,
tetapi konfigurasi historis ditampilkan unavailable. Tidak ada backfill identitas yang ditebak.

### Persistence dan compatibility

Migration `012_assignment_activation` melanjutkan `011_bench_baseline_regression`:

- `agent_publications`: satu immutable signed publication receipt per version, scoped index;
- `assignment_transitions`: scoped history, unique assignment/generation dan assignment/request key;
- assignment pointer dan `activation_origin` (`tracked` untuk writes baru, `legacy` untuk rows lama);
- nullable captured provenance columns/indexes pada `run_states`.

Migration tidak mengubah AgentVersion, Bench, baseline, comparison atau approval payload/history,
dan tidak mengarang signed receipts. Remediation `013_history_integrity` menolak adoption terhadap
history tanpa independently committed head. Menghapus seluruh history lalu mengubah origin SQL ke
legacy tidak memberi authority. Historical assignment tetap readable, tetapi activation/rollback/run
memerlukan freshness yang dapat dibuktikan.

Publication tanpa receipt dan independent commitment tidak eligible. Fallback audit publication
legacy dihapus: metadata SQL dan weak audit tidak membuktikan pre-receipt cohort. Registry menandai
`history_freshness_unverified` dan `historical_access_read_only`; tidak ada signature historis yang
dibuat oleh migration. Publication baru kehilangan receipt selalu fail-closed. Signed evaluation
format 1 yang valid tetap dapat dibaca dan direvalidate dengan limitations existing, tanpa invented
grader evidence; hal itu tidak membuktikan freshness publication atau accepted history.

SQLite memakai existing `BEGIN IMMEDIATE`; PostgreSQL memakai row locks. Unique constraints
melindungi generation/idempotency. Downgrade 012 menghapus operational receipts/provenance baru,
tetapi mempertahankan artifact/governance lama; backup database, evidence key, independent store/anchor sebelum
downgrade. Upgrade ulang tidak merekonstruksi histori yang telah dihapus.

Migration `013_history_integrity` menambahkan authenticated canonical audit serta SQL append-only
guards. Head baseline/aktivasi/publication diperiksa terhadap durable store di luar application DB;
publication deprecation tidak bisa direplay menjadi published. Prepare intent durable mendahului
DB commit, dan failure ambigu meninggalkan pending/unverified. Tidak ada distributed commit atau
compromised-host/superuser claim. SQLite Local mendukung database-only corruption dengan protected
sidecar/key; PostgreSQL memerlukan restricted non-owner writer dan protected external path. Detail
trust boundary, compatibility, recovery dan evidence: [Governance history integrity](governance-history-integrity.md).

### API dan UI

- `GET /api/projects/{project_id}/blueprints/{blueprint_id}/registry`: derived read-only registry.
- `POST /api/projects/{project_id}/assignments/{assignment_id}/rollback`: strict `RollbackIntent`,
  dengan `target_version_id`, `expected_current_version_id`, nullable `expected_transition_id`,
  `reason` dan `idempotency_key`; extra authority flags ditolak.
- Snapshot version mempunyai `registry`; assignment mempunyai verified activation history/current
  head/reason; run mempunyai captured identity dan `assignment_provenance_verified`.
- Factory menampilkan lifecycle/checksum/publication/Bench/approval, known-good reason, active count,
  current Bench baseline serta assignment transition history. Dialog mereview current/target,
  target checksum/evidence dan reason. Backend tetap menentukan keputusan final.

### Validation dan residual limits

Dedicated tests berada di `tests/unit/test_agent_registry_contracts.py`,
`tests/integration/test_agent_registry_rollback.py`, `test_agent_registry_api.py`,
`test_assignment_activation_migration.py`, dan `tests/security/test_agent_rollback_authority.py`.
Positive/negative coverage mencakup actual Factory/Bench/Core publication, generic suite,
two-assignment isolation, before/after/in-flight run provenance, duplicate/conflicting/stale intent,
two concurrent writers, atomic audit failure, legacy adoption, upgrade/downgrade dan tampering pada
payload, Bench, approval, baseline, comparison, publication, activation dan run identity.

Frontend tests mencakup server eligibility, reason review, CAS/key persistence pada retry dan
historical context setelah pointer berubah. Playwright menjalankan real HTTP/backend/SQLite dengan
isolated runtime, termasuk rollback UI dan histori run/baseline yang tetap utuh. Hasil command
aktual delivery dicatat pada STATUS.md setelah selesai dijalankan.

Validation commands pada 8 Oktober 2026 (isolated runtimes, tanpa live model submission):

| Command | Hasil aktual |
| --- | --- |
| `python -m pytest tests/unit/test_agent_registry_contracts.py tests/integration/test_agent_registry_rollback.py tests/security/test_agent_rollback_authority.py tests/integration/test_agent_registry_api.py tests/integration/test_assignment_activation_migration.py -q --tb=short` | 57 passed |
| `python -m pytest tests/integration/test_schema_migration_compatibility.py tests/integration/test_assignment_activation_migration.py -q --tb=short` | 6 passed; SQLite upgrade/downgrade, retained governance, metadata parity, PostgreSQL offline SQL, Alembic revision length |
| `python -m pytest -q --tb=short` | 580 passed, 5 skipped; includes Factory/Bench/regression/Core approval/security/integration/E2E backend |
| `npm.cmd run test` | 67 passed, 12 files |
| `npm.cmd run build` | TypeScript/Vite successful; existing bundle-size warning remains |
| `npm.cmd run test:e2e` | 16 passed, 0 flaky, 0 skipped; real HTTP/backend rollback and historical run UI |
| `python -m ruff check --select E4,E7,E9,F` on new repository/migration/test files | All checks passed |
| `git -c core.safecrlf=false diff --check` | Clean |

Historical corrupted assignment blueprint tetap ditolak dengan existing `PermissionDeniedError`
contract; assertion security existing dipertahankan. Browser keyboard test menunggu initial focus
effect yang nyata sebelum memberi keyboard intent, dengan assertion tambahan dan tanpa sleep.

PostgreSQL DDL dikompilasi offline; live PostgreSQL locking belum diuji. Live model dispatch tetap
opt-in. No production authentication baru, automatic rollback, monitoring, incident replay, canary,
traffic control, cancellation/migration in-flight, atau model comparison BN-08 di scope ini.
Signing key dan server process adalah trusted boundary seperti authority existing. Legacy audit
provenance memiliki keterbatasan di atas; snapshot registry verification masih per-version query,
bukan pagination/cache untuk registry besar.

File implementation yang berubah: `packages/contracts/{agent,runtime,__init__}.py`,
`database/{connection,schema}.py`, `database/repositories/{agent_repo,agent_activation_repo,
bench_regression_repo,run_state_repo}.py`, migration 012, `modules/agent_factory/service.py`,
`modules/core/{permissions/engine,workflows/coordinator}.py`, `services/api/studio.py`, Factory UI,
frontend `types`/`studio-state`, component fixtures/tests, Playwright, migration compatibility tests,
README, STATUS dan existing Factory/Bench/Studio documentation.
