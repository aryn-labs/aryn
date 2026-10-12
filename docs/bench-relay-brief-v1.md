# Bench, Relay dan Brief V1 — implementasi dan bukti

Laporan pekerjaan lokal 12 Oktober 2026. Tiga modul memakai Dashboard Shell, session, project ownership, theme, bahasa, API dan authority Core yang sama. Data produksi tidak diisi dari prototype. Record dalam screenshot berasal dari operasi Core pada database uji disposable dengan `IsolatedTestRuntime`; gambar tersebut bukan hasil inference provider live.

## 1. HEAD dan working tree

- Repository: `D:\ARYN\aryn-labs\aryn`, branch `development`.
- HEAD awal dan akhir: `8cf87a7bb3d0aa49e833a81291fe3f922ffeb05a`.
- Awal audit: working tree bersih, development sesuai origin.
- Akhir pekerjaan: 11 file tracked berubah dan 15 file baru; perubahan implementasi lokal belum di-commit atau di-push. Tidak ada pergantian branch, merge, perubahan main, migrasi produksi, atau penghapusan perubahan pengguna.
- `.local/intelligence-evidence/` menyimpan bukti lokal dan berada di luar source produksi. Wheel lokal merupakan build working tree, bukan delivery CI yang sudah tervalidasi.

## 2. Audit fondasi

Core Brief, Relay, replay, approvals dan protected persistence sudah tersedia. Frontend tiga modul masih memakai scaffold routing. Implementasi ini menggunakan kembali `modules/brief/service.py`, `modules/relay/service.py`, `modules/relay/recovery.py`, `modules/bench/replay.py`, Bench runner/graders, repository baseline/regression, dan kontrak existing.

Audit meliputi kontrak intelligence/Bench, routes intelligence/Studio, signed records, history heads, schema/repositories, Dashboard routing/providers, existing UI primitives, Projects, Runs, Workflow Studio, Agent Factory serta browser/CI configs. Tidak dibuat tabel, migration, signer, runtime, approval ledger atau execution engine kedua.

Referensi yang dibaca:

- HTML `ARYN_Bench_Relay_Brief_Interactive_Design_v1.html`: keseluruhan HTML, CSS dan JavaScript, termasuk navigasi, detail, wizard, dialog dan responsive rules. Browser menolak membuka file lampiran dengan security-policy block. Tidak dilakukan workaround untuk melewati blok itu. Perbandingan desain menggunakan source HTML; tidak diklaim sebagai perbandingan visual langsung terhadap render lampiran.
- `docs/intelligence-recovery-contracts.md`, `docs/bench-engine.md`, `docs/governance-history-integrity.md`, `docs/uat-bench-model-validation.md`.
- Dokumen normatif ditemukan di luar checkout, di `D:\ARYN\dokumen aryn`: `03_ARYN_Product_Requirements_v1.0.docx` (khusus BR-01–09, BN-01–10, RL-01–10), `04_ARYN_System_Architecture_Specification_v1.0.docx`, dan `06_ARYN_Security_Governance_Compliance_v1.0.docx`. Teks dibaca untuk pemeriksaan requirements; layout DOCX tidak diaudit. Folder `aryn-docs` sendiri hanya berisi index/README. Pencocokan dokumen ini dilanjutkan setelah lokasi eksternalnya ditemukan.
- File terpisah bernama `ARYN_Bench_Relay_Brief_Implementation_Prompt_v1.md` tidak ditemukan pada lokasi lampiran yang tersedia; instruksi lengkap dalam chat menjadi scope pekerjaan.

## 3. PRD dibandingkan dengan Core aktual

| Kebutuhan | Implementasi yang sah saat ini | Batasan |
|---|---|---|
| BR-01–07, BR-09 | Source snapshot, digest, freshness, coverage, typed hypothesis, counter-evidence, abstention dan links melalui Brief Core | Dukungan literal/predicate terukur; bukan semantic root-cause engine |
| BR-08 | Dokumen pengguna, artifact/run internal terverifikasi dan disposable demo observations | Git, runbook connector dan telemetry eksternal belum tersedia |
| BN-01–04, BN-06 | Server suite, exact version/evaluation, scenario/graders, provenance, verified evidence dan regression gate | Tidak semua adapter menyediakan biaya, resources atau tool trace granular |
| BN-05, BN-07 | Capsule replay diagnostik tanpa live remediation; tidak ada promosi dataset otomatis | Replay tidak menjadi promotion evidence |
| BN-08–10 | Per-scenario identity/resource observations dan baseline comparison dapat diperiksa | Belum ada workspace perbandingan model arbitrer atau export laporan evaluasi Bench khusus; raw trace viewer tidak diada-adakan |
| RL-01–08 | Signal dedup, lifecycle, investigation, proposal, exact-hash human approval, once-only effect, independent verification, closure dan capsule | Hanya fixed action `restart_demo` pada database disposable fixture |
| RL-09–10 | State aktual termasuk DEGRADED dan OUTCOME_UNKNOWN serta explicit reconciliation | Jalur rejected/expired/escalated dan remediasi infrastruktur produksi tidak dibuat tanpa kontrak |

State Relay mengikuti kontrak operasional Core: OPEN, INVESTIGATING, PROPOSED, EXECUTING, DEGRADED, RECOVERED, CLOSED, OUTCOME_UNKNOWN. State aspiratif di dokumen desain tidak ditambahkan sebagai authority frontend.

## 4. Shared components dan queries

`components/intelligence/IntelligenceUI.tsx` menyediakan Badge, Notice, Panel, DateValue, JsonFacts, IntelligenceLayout, CatalogFilters, QueryState, More, ScopeGuard, ResourceLink, Field dan MutationDialog. Facts/Tabs, Button, Dialog dan DataState existing digunakan kembali.

`hooks.ts` memisahkan scoped record/catalog/context queries, pagination per proyek, deferred search, serta pengembalian fokus dialog. Query keys memuat actor, organisasi dan proyek. Response diperiksa dengan Zod serta scope/identity aktual. Error tidak menampilkan cached private record sebagai fallback. Dialog memakai focus trap existing, Escape dan pengembalian fokus ke trigger.

CSS menggunakan token ARYN; tidak mengubah palette Dashboard global. Tabel compact dapat di-scroll horizontal, detail memakai workspace penuh dengan provenance kanan, dan pada layar sempit panel ditumpuk. Kontras badge light mode diperbaiki secara lokal. Namespace i18n Indonesia/English mempunyai key yang sama.

## 5. File baru

- `modules/bench/workspace.py`
- `apps/web/src/components/intelligence/{IntelligenceUI.tsx,hooks.ts,intelligence.css}`
- `apps/web/src/features/intelligence/api.ts`
- `apps/web/src/features/bench/BenchPage.tsx`
- `apps/web/src/features/brief/BriefPage.tsx`
- `apps/web/src/features/relay/RelayPage.tsx`
- `apps/web/src/i18n/intelligence.ts`
- `apps/web/src/test/intelligence.test.tsx`
- `apps/web/e2e/intelligence.spec.ts`
- `apps/web/playwright.intelligence.config.ts`
- `tests/integration/test_intelligence_workspace.py`
- `tests/intelligence_browser_server.py`
- Laporan ini.

## 6. Perubahan existing

`services/api/intelligence.py`, router dan i18n registration; package script E2E; CI Browser shard 3; AgentEditor exact-version search; links di RunDrawer, WorkflowRunPanel, ProjectResourceDrawer dan ProjectWorkspace. Home, Chat dan Dashboard Shell tidak didesain ulang.

`tests/postgresql/test_intelligence_persistence.py` menambah dua pemeriksaan read projection menggunakan actual PostgreSQL restricted-writer fixture existing. Tes tersebut masuk job PostgreSQL CI; belum diklaim lulus lokal tanpa database yang dikonfigurasi.

## 7. Kontrak API/Core

Semua path berikut berada di `/api/projects/{project_id}` dan mempertahankan authentication/session, Origin/CSRF serta Core permission checks.

Tambahan read-only:

| Path | Fungsi |
|---|---|
| `GET /intelligence/context` | Current effective permissions untuk actions yang ditampilkan |
| `GET /bench/suites` | Manifest dari server registry |
| `GET /bench/evaluations` | Scoped bounded catalog, q, blueprint, exact version, suite dan passed/failed |
| `GET /bench/evaluations/{id}` | Detail terverifikasi, scenarios/graders, provenance dan baseline/regression |
| `GET /brief/{id}/links` | Bounded signed links untuk bundle yang sudah diotorisasi |

`GET /brief/sources` ditambah current integrity/freshness tanpa mengirim blob content dalam katalog. Invalid/missing origin menjadi UNVERIFIED/unavailable; korupsi signed catalog record tetap ditolak. Query keys tidak dikenal/duplikat ditolak dan page size maksimum 100.

Backend Bench projection memanggil validasi stored evaluation existing, exact AgentVersion, serta BenchRegressionRepository. `passed`, `verified`, `current_evaluation`, `promotion_eligible` dipisahkan. Signature envelopes tidak dikirim sebagai UI trace. Unknown historical suite tidak diberi suite identity buatan.

Endpoint existing yang digunakan: Brief documents/sources/bundles/detail/download/brief-links; Relay demo-fixtures/signals/incidents/investigate/proposals/approve/execute/reconcile/close/capsules/download; Bench capsule replay/replays; blueprint baseline acceptance, lifecycle dan Agent Factory version evaluation. Semua mutation tetap memakai handler Core existing.

## 8. Bench

Katalog menyajikan persisted history dengan filter proyek, blueprint, versi, suite dan pass/fail. Integrity dan regression ditampilkan terpisah dari skor. Historical pass dengan provenance rusak tetap dapat diperiksa tetapi UNVERIFIED dan tidak eligible untuk promosi.

Detail menampilkan exact AgentVersion, suite/version, skenario, actual output, failure reason, grader results, requested/actual model, provider/backend/gateway, usage, latency, measured cost/resources bila tersedia, serta trace availability. Critical regressions terlihat walaupun ada skor agregat. Baseline view menampilkan accepted identity/version, candidate, score delta, nested scenario/grader differences, metric comparability, provenance differences dan keputusan Core.

Acceptance menggunakan exact evaluation, expected baseline ID/CAS, alasan dan explicit suite-transition option; permission dan evidence diperiksa ulang oleh Core. Tidak ada auto-approve atau auto-publish. Link Agent Factory memilih versi yang persis sama, tidak mengganti Working Copy atau immutable version.

Replay menggunakan endpoint existing. UI memvalidasi `backend=deterministic_in_memory`, model/provider null, `live_write_calls=0`, `promotion_evidence=false`. Persisting report/audit/link dibedakan dari live remediation effects. Tidak ada inferensi ulang pada replay.

## 9. Relay

Katalog insiden memuat state, severity, target, project, updated time; detail memuat timeline persisted, evidence/investigation, proposal, approval, execution checkpoint, independent verification dan capsule. Demo fixtures dapat dibuat/diubah secara eksplisit dengan expected revision; signal collection menggunakan dedup key.

Proposal membawa exact target/revision, bundle/digest, payload hash, preconditions dan verification contract. Human approval berasal dari Core. Execute memakai explicit idempotency key dan fixed action; UI tidak memberi tool authority. Action success tidak diperlakukan sebagai recovered. Closure diblokir sampai current fixture revision/health sesuai verification. Outcome unknown membutuhkan rekonsiliasi eksplisit dan tidak dijalankan ulang otomatis.

Recovery bukan SSH, Kubernetes, command runner atau production server remediation. Boundary disposable ditampilkan pada UI dan dialog tindakan.

## 10. Brief

Katalog bundles dan source registry, source inspector, detail evidence matrix, provenance, linked records dan download menggunakan persistence Core. Current evidence evaluation terpisah dari original immutable collection status. Source metadata menampilkan kind/origin, observed/collected time, integrity, freshness, quality dan digest/reference.

Wizard tiga langkah memilih sumber project-scoped, mengisi pertanyaan/predicate dan mereview konfigurasi sebelum API mutation. Predicate hanya `service_healthy`, `contains_text`, `run_completed`. Coverage/minimum divalidasi Core; source stale, unsupported atau kurang menghasilkan abstention. Counter-evidence tidak disembunyikan. Dokumen pengguna tidak dilabeli sebagai pembuktian fakta eksternal.

## 11. Integrasi

- Runs drawer dan WorkflowRunPanel membuka Brief related lookup dengan actual run/workflow-run IDs.
- Brief linked records membuka incident, run, artifact, capsule atau replay aktual.
- Relay capsule membuka Bench diagnostik; replay kembali ke incident/capsule sesuai identity server.
- Bench membuka exact version di Agent Factory dan memakai approval/baseline authority existing.
- Projects Pekerjaan/Hasil/Aktivitas mempunyai scoped module links; resource drawer membuka evaluation tepat dan Brief related lookup untuk run/artifact.
- Owner project detail berasal dari route dan API response yang diverifikasi. Mengganti selector tidak memindahkan kepemilikan record.

## 12. Security dan governance

Tidak ada pengurangan RBAC, CSRF/Origin, budget/model policy, signing, protected heads, immutable versions, tool confinement, idempotency atau approval checks. Tambahan backend adalah authorized read projections. No-store, sanitized errors/content dan existing safe attachment headers dipertahankan.

Tes baru memeriksa identity/scope, server registry, evidence corruption, failed evaluation, baseline CAS, bounded pagination/query validation, viewer permissions dan revoked membership. Negative corruption/lost-checkpoint fixtures berada hanya pada test server disposable; tidak ada endpoint production untuk memalsukan evidence.

## 13. Pengujian aktual

| Pemeriksaan | Hasil pekerjaan ini |
|---|---|
| TypeScript + Vite production build | PASS; peringatan chunk aplikasi sekitar 724 kB dan annotation Zod tetap terlihat |
| ESLint dan Prettier | PASS |
| Vitest seluruh frontend | 124 passed / 16 files; `.local/intelligence-evidence/frontend.xml` |
| API/Core read projection baru | 9 passed; `.local/intelligence-workspace.xml` |
| Regresi intelligence recovery existing | 34 passed; `.local/intelligence-core-regression.xml` |
| Browser intelligence actual API/Core | 16 passed, 0 failed/skipped; `.local/intelligence-evidence/browser.xml` |
| Browser Home/Dashboard existing | 90 passed; suite existing memakai fixture API browser |
| Browser Chat/Projects actual API/Core | 29 dan 12 passed menggunakan isolated test runtime |
| Browser Agent Factory / Workflow / Runs & Automations | 14 / 14 / 15 passed; actual API/Core dengan runtime terisolasi |
| Backend/security offline lengkap | 1.064 passed, 5 skipped, 132 deselected; `.local/intelligence-evidence/backend.xml` dan `backend.log` |
| Ruff, actionlint, repository hygiene, diff whitespace | PASS pada pemeriksaan implementasi |
| Gitleaks area domain yang berubah | Tidak ditemukan leaks; hasil redacted |
| Python wheel lokal | Build berhasil; `FINAL_WHEEL_IMPORT_PASS` pada wheel yang diekstrak secara terpisah; bytes `modules/bench/workspace.py` cocok dengan source terakhir |
| Live PostgreSQL pada perubahan lokal | Belum dijalankan: admin URL tidak dikonfigurasi, Docker daemon tidak tersedia. Tidak ada fallback SQLite yang diklaim sebagai PostgreSQL |

Browser intelligence memakai aplikasi build sebenarnya, migrated disposable SQLite, Core persistence/signing dan isolated test runtime. Pengujian mencakup baseline acceptance tanpa perubahan status versi, critical regression, unverified 4/4 pass, suite registry, Runs → Brief, fixture revision/signal, wizard/ingest persistence, human approval → execution → health → closure → capsule replay, degraded/unknown reconciliation, isolation, focus/Escape, axe, mobile, light dan English.

Lima backend skips berasal dari pengujian live model/Hermes yang memerlukan opt-in atau API key; 132 deselected termasuk suite PostgreSQL yang dipisahkan oleh marker. Pengulangan API projection sembilan tes mencakup perbaikan terakhir agar underscore pada suite ID tidak menjadi wildcard SQL. Hitungan tersebut tidak dijumlahkan kembali ke total backend karena ada overlap. Total browser adalah 190 passed: intelligence 16, Home/Dashboard 90, Chat 29, Projects 12, Agent Factory 14, Workflow 14, Runs/Automations 15. Report HTML existing dan JUnit intelligence disimpan sebagai bukti. [Manifest validasi](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/validation.json) mencatat SHA, scope runtime, hasil JUnit/report browser, hash source yang berubah, screenshot dan wheel.

## 14. GitHub Actions

[ARYN Quality 38258240147](https://github.com/aryn-labs/aryn/actions/runs/38258240147) pada exact SHA `8cf87a7bb3d0aa49e833a81291fe3f922ffeb05a`: completed/success, semua 14 jobs success termasuk PostgreSQL, Native Hermes Boundary, Browser shards, Required Quality Gates dan Validated Delivery Artifact. Artifact `aryn-delivery-8cf87a7bb3d0aa49e833a81291fe3f922ffeb05a` tersedia dan belum expired ketika diperiksa.

Run sebelumnya [38254506911](https://github.com/aryn-labs/aryn/actions/runs/38254506911) pada SHA `763c9deee43fb823447c4d9e544f4d6a94c168be` cancelled: [Windows backend 4/4](https://github.com/aryn-labs/aryn/actions/runs/38254506911/job/114828977661) cancelled, Required Quality Gates failure, delivery skipped. Check annotation GitHub membuktikan penyebab: `The job has exceeded the maximum execution time of 20m0s`. Timeout Windows sudah dinaikkan ke 30 menit pada HEAD 8cf87a7 dan run berikutnya sukses. Job individual pada run cancelled tidak dianggap overall PASS.

Perubahan lokal laporan ini belum mempunyai CI run baru karena tidak di-commit/push. Browser intelligence ditambahkan ke shard 3 dan evidence artifact di-upload dengan SHA CI; required gates/completeness checks tidak dilemahkan.

## 15. Screenshot aplikasi nyata

Semua screenshot di `.local/intelligence-evidence/` berisi data uji terisolasi yang dibuat lewat Core:

| Tampilan | File |
|---|---|
| Bench catalog | [bench-catalog.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/bench-catalog.png) |
| Evaluation detail / graders | [bench-evaluation-detail.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/bench-evaluation-detail.png), [bench-graders.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/bench-graders.png) |
| Baseline / suites | [bench-baseline-comparison.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/bench-baseline-comparison.png), [bench-suites.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/bench-suites.png) |
| Diagnostic replay | [bench-capsule-replay.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/bench-capsule-replay.png) |
| Relay catalog / incident | [relay-catalog.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/relay-catalog.png), [relay-incident-detail.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/relay-incident-detail.png) |
| Independent health / unknown | [relay-recovery-verification.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/relay-recovery-verification.png), [relay-outcome-unknown.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/relay-outcome-unknown.png) |
| Brief catalog / bundle / matrix | [brief-catalog.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/brief-catalog.png), [brief-bundle-detail.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/brief-bundle-detail.png), [brief-evidence-matrix.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/brief-evidence-matrix.png) |
| Source / wizard | [brief-source-inspector.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/brief-source-inspector.png), [brief-create-wizard.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/brief-create-wizard.png) |
| Mobile ketiga modul | [bench-mobile.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/bench-mobile.png) / [bench-mobile-records.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/bench-mobile-records.png), [relay-mobile.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/relay-mobile.png) / [relay-mobile-records.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/relay-mobile-records.png), [brief-mobile.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/brief-mobile.png) / [brief-mobile-records.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/brief-mobile-records.png) dan varian `*-mobile-records.png` |
| Light dan English ketiga modul | [bench-light-english.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/bench-light-english.png), [relay-light-english.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/relay-light-english.png), [brief-light-english.png](D:/ARYN/aryn-labs/aryn/.local/intelligence-evidence/brief-light-english.png) |

Desktop, matrix, baseline dan mobile screenshots diperiksa langsung dengan image viewer. Desain mempertahankan shell ARYN, workspace detail/provenance, compact tables dan semantic badges. Screenshot merupakan viewport nyata; konten panjang tetap dapat di-scroll, termasuk provenance independen dan tabel mobile.

## 16. Known issues dan batas pengujian

- Manual visual refinement/UAT final seluruh ARYN ditunda sesuai scope pengguna. Axe bukan sertifikasi WCAG penuh.
- Render browser lampiran HTML diblokir; visual comparison terhadap render lampiran tidak dapat diklaim.
- Tidak ada live provider inference, paid model run, production remediation atau hosted production UAT.
- PostgreSQL untuk source lokal masih perlu validasi pada CI atau instance disposable yang dikonfigurasi. PASS baseline tidak membuktikan perubahan uncommitted.
- Filter source search/freshness berlaku pada halaman yang telah dimuat; UI menjelaskan batas ini dan menyediakan Muat lagi. Bundle status filter mengikuti original collection status sesuai Core.
- Filter tanggal Bench belum disediakan kontrak backend. Blueprint/version filter menerima exact IDs; belum ada picker pencarian resource lanjutan.
- Biaya/resources/trace yang tidak direkam adapter ditampilkan unavailable. Tidak dibuat angka atau tool steps fiktif.
- External connectors, arbitrary suite editor, model-comparison workspace, dataset promotion dan export report Bench khusus tetap gap PRD P1 yang dinyatakan eksplisit.
- Generic baseline catalog membuka evaluasi dan perbandingan accepted baseline melalui detail; tidak ada baseline authority/ledger frontend kedua.

## 17. Kesiapan tahap selanjutnya

Fondasi scoped UI, resource navigation, immutable evidence, guarded mutations, browser fixture, baseline/replay inspection dan shared intelligence primitives dapat dipakai pada MCP & Integrations serta Deployments. Adapter berikutnya perlu kontrak capability, authorization, provenance/freshness, consent dan failure behavior sendiri sebelum UI diaktifkan. Deployment produksi tetap memerlukan quality gates pada SHA yang benar, hosted/security validation dan approval yang sesuai; pekerjaan ini tidak memberi authority baru untuk menjalankannya.
