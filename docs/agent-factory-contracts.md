# Domain Contract Agent Factory — ARYN

Dokumen ini mendefinisikan canonical domain contract untuk **Agent Factory** pada ARYN, yang mencakup kontrak tipe, kebijakan keamanan (*security policies*), skema penyimpanan database, representasi kanonikal payload hash, serta aturan lifecycle yang mengikat seluruh subsistem ARYN.

---

## 1. Prinsip Desain & Invarian Keamanan

1. **First-Class Typed Contracts**: Seluruh atribut penting definisi agent (`objective`, `role`, `owner`, `output_contract`, `constraints`, `tool_policy`, `model_policy`, `budget_policy`, `schema_version`, `evaluation_reference`) dimodelkan sebagai typed domain models yang tervalidasi, bukan loose dictionary di dalam `metadata`.
2. **Immutability Versi Terpublikasi (*Immutable Published Version*)**: Versi agent yang berstatus `published` bersifat strictly read-only. Setiap perubahan konfigurasi harus menghasilkan versi baru (`draft`). Integritas ini dijaga secara berlapis:
   - Validasi ORM event listener (`protect_published_configuration`).
   - Cryptographic payload hash verification (`verify_integrity()`).
3. **Explicit Grant & Deny-by-Default Tool Policy**: Akses tool tidak boleh implisit. Setiap grant harus terdaftar eksplisit dalam `tool_grants`. Jika tool berada dalam `forbidden_tools`, versi ditolak pada tahap validasi (`ValueError`).
4. **Anti-Silent-Fallback Model Policy**: Sesuai ADR-005 dan tata kelola ARYN, fallback model tanpa persetujuan eksplisit dilarang (`allow_fallback = False`). Parameter model divalidasi terhadap daftar model yang diizinkan dan rentang hyperparameter yang aman.
5. **Exact Payload Hash Approval Binding**: Persetujuan manusia (*human approval*) mengikat exact SHA-256 hash dari representasi kanonikal versi agent, evaluasi Bench yang lulus dan terverifikasi, serta tenant/project boundary.
6. **No Self-Approve / No Self-Publish**: Agent tidak memiliki kapabilitas menyetujui atau menerbitkan versinya sendiri. Seluruh transisi status lifecycle memerlukan aktor manusia yang terautentikasi dan memiliki role yang sesuai.
7. **Authoritative Bench Evaluation Reference**: Agent version mendefinisikan `evaluation_reference` yang mengikat suite, versi, skor minimum, dan daftar skenario wajib (`required_scenarios`). Evaluasi Bench diverifikasi secara fail-closed terhadap referensi ini; evaluasi yang tidak cocok ditolak.
8. **Perlindungan Backward Compatibility & Anti-Bypass Legacy**: Versi baru menghitung SHA-256 menggunakan `canonical_format: 3`. Format legacy v2 hanya diizinkan untuk pembacaan historis (*read-only*), dengan proteksi ketat di mana versi legacy yang memiliki modifikasi field baru langsung ditolak sebagai korup/tampered. Seluruh transisi lifecycle baru (`evaluate`, `approve`, `publish`) mewajibkan Format 3 kanonikal.

---

## 2. Struktur Domain Contract

Domain contract didefinisikan pada `packages/contracts/agent.py` dan diekspor melalui `packages/contracts/__init__.py`.

### 2.1 Sub-kontrak Kebijakan & Spesifikasi

- **`AgentOutputContract`**:
  - `format`: Format respons yang diharapkan (`text`, `json`, `markdown`).
  - `schema_definition`: JSON schema opsional untuk format terstruktur.
  - `required_sections`: Daftar bagian yang wajib ada pada respons (misal `["Executive Summary", "Key Findings"]`).
  - `strict`: Boolean yang menentukan apakah schema harus divalidasi secara ketat.

- **`AgentConstraints`**:
  - `disallowed_actions`: Daftar aksi/operasi yang dilarang dieksekusi oleh agent.
  - `operational_rules`: Aturan batasan operasional.
  - `require_evidence_citation`: Mewajibkan sitasi bukti pada setiap temuan/klaim.
  - `max_execution_time_seconds`: Batas waktu maksimum eksekusi per interaksi (default: `300.0`).

- **`AgentToolPolicy`**:
  - `tool_grants`: Daftar tool yang diizinkan secara eksplisit (`List[str]`).
  - `forbidden_tools`: Daftar tool yang secara tegas dilarang (`List[str]`).
  - `deny_by_default`: Kebijakan default deny (`True`).
  - Method `is_tool_allowed(tool_name: str) -> bool`: Mengembalikan `True` hanya jika tool ada di `tool_grants` dan tidak ada di `forbidden_tools`.
  - Method `validate_tool_grants()`: Menolak pembuatan versi jika terdapat irisan antara `tool_grants` dan `forbidden_tools`.

- **`AgentModelPolicy`**:
  - `primary_model`: Model ID yang didelegasikan untuk inferensi (misal `gemini-2.5-flash`).
  - `provider`: Provider inference gateway (misal `google`, `anthropic`).
  - `allowed_models`: Whitelist model yang diperbolehkan untuk agent ini.
  - `temperature_min` / `temperature_max`: Batas bawah dan atas temperature (default: `0.0` s/d `1.0`).
  - `max_tokens_limit`: Batas atas token yang dapat dialokasikan (default: `32768`).
  - `allow_fallback`: Flag fallback runtime (default: `False`, tidak boleh fallback diam-diam).
  - Method `validate_model(model_name: str, temperature: float, max_tokens: int)`: Memastikan parameter model berada dalam batasan policy.

- **`AgentBudgetPolicy`**:
  - `max_tokens_per_run`: Batas token per single run (default: `16384`).
  - `max_turns`: Batas turn percakapan multi-turn (default: `10`).
  - `max_cost_usd`: Batas biaya estimasi per run dalam USD (default: `0.50`).
  - `timeout_seconds`: Batas waktu eksekusi run sebelum timeout (default: `120.0`).

- **`AgentEvaluationReference`**:
  - `suite_id`: Identifier test suite Bench (default: `research-safety-1.2.0`, alias: `research-safety`).
  - `evaluation_version`: Versi test suite evaluator (default: `1.2.0`).
  - `min_score_threshold`: Skor kelulusan minimum (default: `1.0` / 100%).
  - `required_scenarios`: Daftar skenario yang wajib lulus. Default berisi 4 skenario Bench aktual:
    - `scen_safety_injection_defense`
    - `scen_tool_confinement_defense`
    - `scen_research_accuracy_synthesis`
    - `scen_grounded_abstention`
  - Validasi: Memvalidasi `suite_id` terhadap suite registry dan memastikan seluruh elemen di `required_scenarios` merupakan skenario yang sah dalam suite tersebut.

- **`AgentDefinition`**:
  - Model komposit yang menyatukan seluruh spesifikasi di atas:
    `schema_version`, `role`, `objective`, `owner`, `output_contract`, `constraints`, `tool_policy`, `model_policy`, `budget_policy`, `evaluation_reference`.

### 2.2 `AgentBlueprint`

Representasi template agent induk:
- `blueprint_id`: Identifier unik blueprint (`abp_*`).
- `organization_id` & `project_id`: Batas isolasi multi-tenant.
- `name` & `description`: Metadata deskriptif.
- `role`: Peran agent default (misal: "Security Auditor").
- `objective`: Objektif utama agent.
- `owner`: Principal pemilik blueprint (user / tim).
- `status`: Status siklus hidup blueprint (`active`, `archived`).
- `metadata`: Data ekstensi tambahan.

### 2.3 `AgentVersion`

Representasi versi agent immutable yang memiliki hash kanonikal:
- Atribut konfigurasi runtime dasar: `system_prompt`, `model`, `temperature`, `max_tokens`, `tool_grants`.
- Atribut typed definition lengkap: `schema_version`, `role`, `objective`, `owner`, `output_contract`, `constraints`, `tool_policy`, `model_policy`, `budget_policy`, `evaluation_reference`.
- Sinkronisasi otomatis dua arah antara scalar fields (`model`, `temperature`, `max_tokens`, `tool_grants`) dan nested policy objects (`model_policy`, `tool_policy`).
- Property `.definition` yang memproyeksikan seluruh spesifikasi menjadi objek `AgentDefinition`.
- Property `.canonical_format` yang mengembalikan format integritas (`3` untuk kanonikal saat ini, `2` untuk legacy v2 bersih, `0` jika korup/tidak valid).

---

## 3. Skema Database & Migrasi

### 3.1 Tabel ORM (`database/schema.py`)

- **`agent_blueprints` (`AgentBlueprintModel`)**:
  - Kolom baru: `role` (Text, nullable), `objective` (Text, nullable), `owner` (String(128), nullable).
- **`agent_versions` (`AgentVersionModel`)**:
  - Kolom baru: `schema_version` (String(32), default `"1.0.0"`), `role` (Text, nullable), `objective` (Text, nullable), `owner` (String(128), nullable), `output_contract_json` (Text, nullable), `constraints_json` (Text, nullable), `tool_policy_json` (Text, nullable), `model_policy_json` (Text, nullable), `budget_policy_json` (Text, nullable), `evaluation_reference_json` (Text, nullable).
- **ORM Immutability Listener**:
  `protect_published_configuration` mendengarkan event `before_update`. Jika status adalah `published`, mutasi terhadap kolom-kolom definisi agent langsung ditolak dengan `RuntimeError("Published agent versions are immutable...")`.

### 3.2 Migrasi Alembic (`database/migrations/versions/010_agent_definition_contracts.py`)

- Revises: `009_gateway_provenance`.
- Operasi `upgrade()`:
  - Memeriksa ketersediaan kolom secara dinamis sebelum menambahkan (`add_column`), sehingga kompatibel dengan SQLite alter table maupun PostgreSQL DDL compilation.
- Operasi `downgrade()`:
  - Mendukung rollback schema yang aman melalui `batch_alter_table`.

---

## 4. Representasi Kanonikal Payload Hash (Format 3) & Hardening Legacy

Integritas versi dihitung dengan SHA-256 dari JSON kanonikal Format 3 dengan kunci berurutan alfabetis dan tanpa spasi redundan (`separators=(",", ":")`):

```json
{
  "budget_policy": {
    "max_cost_usd": 0.5,
    "max_tokens_per_run": 16384,
    "max_turns": 10,
    "timeout_seconds": 120.0
  },
  "canonical_format": 3,
  "constraints": {
    "disallowed_actions": [],
    "max_execution_time_seconds": 300.0,
    "operational_rules": [],
    "require_evidence_citation": false
  },
  "evaluation_reference": {
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
  "max_tokens": 4096,
  "model": "gemini-2.5-flash",
  "model_policy": {
    "allow_fallback": false,
    "allowed_models": [],
    "max_tokens_limit": 32768,
    "primary_model": "gemini-2.5-flash",
    "provider": "google",
    "temperature_max": 1.0,
    "temperature_min": 0.0
  },
  "objective": "Perform automated security audits",
  "output_contract": {
    "format": "text",
    "required_sections": [],
    "schema_definition": null,
    "strict": false
  },
  "owner": "usr_sec_lead",
  "role": "Security Auditor",
  "schema_version": "1.0.0",
  "system_prompt": "You are a specialized security agent.",
  "temperature": 0.2,
  "tool_grants": ["read_file"],
  "tool_policy": {
    "deny_by_default": true,
    "forbidden_tools": [],
    "tool_grants": ["read_file"]
  }
}
```

### 4.1 Aturan Verifikasi Integritas (`verify_integrity`)

1. **Format 3 Kanonikal**: Standar wajib untuk seluruh versi baru. Jika `payload_hash == calculate_payload_hash()`, integritas valid.
2. **Format 2 Legacy**:
   - Hanya diizinkan pada pembacaan (*read mode*) rekaman historis yang sudah ada.
   - **Anti-Bypass Protection**: Jika `_has_custom_definition_fields()` bernilai `True` (artinya ada perubahan pada `role`, `objective`, `owner`, `output_contract`, `constraints`, `tool_policy`, `model_policy`, `budget_policy`, `evaluation_reference`), verifikasi format legacy langsung menolak dengan `VersionIntegrityError`. Modifikasi atribut bertipe baru tidak dapat diselundupkan di balik hash legacy.
3. **Strict Canonical Lifecycle Gate**:
   - Parameter `verify_integrity(require_canonical=True)` mewajibkan Format 3.
   - Seluruh tahapan transisi aktif (`evaluate_version_with_bench`, `approve_version`, `publish_version`) memeriksa `version.canonical_format == 3`. Versi legacy draft/rejected/approved ditolak dari siklus hidup baru dan harus dibuatkan versi baru ber-Format 3.

---

## 5. Service Layer (`AgentFactoryService`)

Service layer di `modules/agent_factory/service.py` mengorkestrasi:
- **Pewarisan Persona Blueprint**: Jika pembuatan versi tidak secara eksplisit menyertakan `role`, `objective`, atau `owner`, nilainya secara otomatis diwarisi dari parent `AgentBlueprint`.
- **Validasi Kebijakan & Registry Bench**:
  - `model_policy.validate_model(model, temperature, max_tokens)` dieksekusi sebelum commit.
  - `tool_policy.validate_tool_grants()` memastikan tidak ada tool terlarang yang lolos.
  - `evaluation_reference` divalidasi terhadap suite registry (`get_bench_suite()`) dan scenario IDs suite.
- **Otoritas Evaluasi Bench**:
  - `BenchRunner` mengeksekusi suite yang secara eksplisit ditentukan oleh `version.evaluation_reference.suite_id`.
  - `BenchQualityGate.validate_evidence(evaluation, evaluation_reference)` memverifikasi kesesuaian suite, ambang skor (`min_score_threshold`), dan kelulusan seluruh skenario dalam `required_scenarios`.
- **Audit Logging**: Mencatat event audit terstruktur `agent_factory.blueprint_created`, `agent_factory.version_created`, `agent_factory.version_evaluated`, dan `agent_factory.version_published` dengan metadata `schema_version`, `role`, `owner`, dan `payload_hash`.
- **Integrasi Approval & Publikasi**: Memastikan versi ber-Format 3 kanonikal, memiliki hasil evaluasi Bench yang lulus dan valid terhadap `evaluation_reference`, serta approval mengikat exact payload hash sebelum transisi ke `published`.

---

## 6. API Service & Frontend Typing

- **API Models (`services/api/studio.py`)**:
  - `BlueprintInput`: Menerima `name`, `description`, `role`, `objective`, `owner`.
  - `VersionInput`: Menerima `system_prompt`, `model`, `temperature`, `max_tokens`, `tool_grants`, `role`, `objective`, `owner`, `schema_version`, `output_contract`, `constraints`, `tool_policy`, `model_policy`, `budget_policy`, `evaluation_reference`.
- **Frontend Types (`apps/web/src/lib/types.ts`)**:
  - Interface TypeScript `OutputContract`, `Constraints`, `ToolPolicy`, `ModelPolicy`, `BudgetPolicy`, `EvaluationReference`.
  - Menambahkan field-field ini ke interface `Blueprint` dan `Version`.

---

## 7. Verifikasi dan Pengujian Otomatis

Seluruh perubahan diverifikasi melalui automated test suite yang ketat:
- `tests/unit/test_agent_contracts.py` (20 tests): Pengujian contract models, boundary kebijakan, hashing Format 3 kanonikal, sinkronisasi scenario IDs Bench, rejection skenario/suite tidak dikenal, gate quality threshold, dan penolakan lifecycle pada format legacy.
- `tests/security/test_version_payload_integrity.py` (29 tests): Pengujian anti-tampering pada seluruh 10 kolom definisi baru, verifikasi immutability ORM, parameterized test penolakan penyelundupan field baru di balik hash legacy, dan rejection transisi lifecycle versi legacy.
- `tests/integration/test_schema_migration_compatibility.py` (3 tests): Pengujian migrasi Alembic 010, retensi data existing, dan kompilasi DDL PostgreSQL offline.
- `tests/integration/test_studio_api.py` (22 tests): Verifikasi API endpoint Studio dengan payload bertipe baru.
- Full backend test suite: 298 passed, 5 skipped (0 failures).
- Frontend suite: 57 vitest tests passed (0 failures) & clean build (`tsc -b && vite build`).
