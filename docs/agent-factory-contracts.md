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
- **Integrasi Approval & Publikasi**: Memastikan versi ber-Format 3 kanonikal, memiliki hasil evaluasi Bench yang lulus dan valid terhadap `evaluation_reference`, serta approval mengikat exact payload hash sebelum transisi ke `published`.

---

## 7. API Service & Frontend Typing

- **API Models (`services/api/studio.py`)**:
  - `BlueprintInput`: Menerima `name`, `description`, `role`, `objective`, `owner`.
  - `VersionInput`: Menerima `system_prompt`, `model`, `temperature`, `max_tokens`, `tool_grants`, `role`, `objective`, `owner`, `schema_version`, `output_contract`, `constraints`, `tool_policy`, `model_policy`, `budget_policy`, `evaluation_reference`.
- **Frontend Types (`apps/web/src/lib/types.ts`)**:
  - Interface TypeScript `OutputContract`, `Constraints`, `ToolPolicy`, `ModelPolicy`, `BudgetPolicy`, `EvaluationReference`.
  - Menyediakan pengetikan untuk antarmuka Studio Workbench dan Canvas Inspector.
