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
7. **Bench Quality Gate**: Versi draft hanya dapat diajukan untuk approval setelah lulus seluruh evaluasi pada suite Bench yang ditentukan (`evaluation_reference`), dengan skor 100% dan bukti evidence terverifikasi.
8. **Dual-Mode Canonical Verification (Backward Compatibility)**: Versi baru menghitung SHA-256 menggunakan `canonical_format: 3` yang menyertakan seluruh 10 atribut definisi agent. Versi historis dengan `canonical_format: 2` tetap dapat diverifikasi integritasnya tanpa merusak data lama.

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
  - `operational_rules`: Aturan batasan operasional (misal: "Must not execute shell commands directly").
  - `require_evidence_citation`: Mewajibkan sitasi bukti pada setiap temuan/klaim.
  - `max_execution_time_seconds`: Batas waktu maksimum eksekusi per interaksi.

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
  - `suite_id`: Identifier test suite Bench (default: `research-safety-1.2.0`).
  - `evaluation_version`: Versi test suite evaluator (default: `1.2.0`).
  - `min_score_threshold`: Skor kelulusan minimum (default: `1.0` / 100%).
  - `required_scenarios`: Daftar skenario yang wajib lulus.

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

## 4. Representasi Kanonikal Payload Hash (Format 3)

Integritas versi dihitung dengan SHA-256 dari JSON kanonikal dengan kunci berurutan alfabetis dan tanpa spasi redundan (`separators=(",", ":")`):

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
    "required_scenarios": [],
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

Method `verify_integrity()` pada `AgentVersion` mengevaluasi:
1. Format 3 canonical hash (standar utama untuk seluruh versi baru).
2. Format 2 legacy hash (fallback otomatis untuk versi historis yang tersimpan sebelum migrasi).

---

## 5. Service Layer (`AgentFactoryService`)

Service layer di `modules/agent_factory/service.py` mengorkestrasi:
- **Pewarisan Persona Blueprint**: Jika pembuatan versi tidak secara eksplisit menyertakan `role`, `objective`, atau `owner`, nilainya secara otomatis diwarisi dari parent `AgentBlueprint`.
- **Validasi Kebijakan**:
  - `model_policy.validate_model(model, temperature, max_tokens)` dieksekusi sebelum commit.
  - `tool_policy.validate_tool_grants()` memastikan tidak ada tool terlarang yang lolos.
- **Audit Logging**: Mencatat event audit terstruktur `agent_factory.blueprint_created`, `agent_factory.version_created`, `agent_factory.version_evaluated`, dan `agent_factory.version_published` dengan metadata `schema_version`, `role`, `owner`, dan `payload_hash`.
- **Integrasi Bench & Approval**: Memastikan versi dievaluasi dan disetujui terhadap hash aktual sebelum dapat dipublikasikan.

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
- `tests/unit/test_agent_contracts.py` (17 tests): Unit testing komprehensif untuk contract models, policy boundary, hashing kanonikal, legacy backward compatibility, dan blueprint inheritance.
- `tests/security/test_version_payload_integrity.py` (20 tests): Pengujian keamanan anti-tampering pada setiap kolom definisi dan verifikasi immutability ORM.
- `tests/integration/test_schema_migration_compatibility.py` (3 tests): Pengujian migrasi Alembic 010, retensi data existing, dan kompilasi DDL PostgreSQL offline.
- `tests/integration/test_studio_api.py` (22 tests): Verifikasi API endpoint Studio dengan payload bertipe baru.
- Full backend suite: 295 passed, 5 skipped (0 failures).
- Frontend suite: 57 vitest tests passed (0 failures) & clean build (`tsc -b && vite build`).
