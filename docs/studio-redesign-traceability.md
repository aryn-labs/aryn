# Studio requirement traceability

Audit source: `3a8ddb69b855ea37d1a33721c6c57a02f14ad881`. Evidence paths refer to the implementation accompanying this document. Final source and CI are recorded in studio-redesign-progress.md. Official references below are from the supplied PRD/repository; the normative PDFs are absent, so no missing PDF section is claimed verified.

| ST-ID | Official / product relation | API / contract and source | Evidence / negative coverage | Delivery owner / status |
|---|---|---|---|---|
| ST-DATA-01 | Core tenant/RBAC, workspace switch | lib/workspace-types.ts; studio.tsx; lib/api.ts | workspace-shell.test.tsx and workspace.spec.ts: AbortSignal, late A response, cache removal, 403 hide | 01 PASS workspace |
| ST-DATA-02 | Core scoped read model | workspace_reads.py; contracts/workspace.py; /summary and /resources/{resource} | test_workspace_api.py: real summary, list/detail, no output in lists; snapshot compatibility | 01 PASS API; resource-specific UIs 02–05 |
| ST-DATA-03 | Core scoped contracts | HMAC cursor, limit 1–100, newest/oldest, filter whitelist | test_workspace_api.py: forged, altered-sort, cross-project cursor, wildcard literal, duplicate/unknown params, 401/403/404 | 01 PASS |
| ST-DATA-04 | Workspace performance | benchmark_workspace.py; workspace_dataset.py; lazy Studio feature imports | workspace.spec.ts large navigation/summary thresholds; test_workspace_snapshot.py verifies every audit with one audit SELECT | 01 PASS bounded routes; legacy full snapshot residual |
| ST-DATA-05 | Core commit authority | WorkspaceService; DivisionUpdate.expected_generation | SQLite/PG concurrent edit, revoked membership, stale generation and audit atomicity | 01 PASS divisions; working copy 02 |
| ST-AF-01 | AF registry / AF-07 rollback | existing agent_activation_repo.py, factory.tsx, registry API; new versions read API | existing test_agent_registry_api.py/test_agent_registry_rollback.py; bounded API tests | 02; existing backend preserved, UI redesign planned |
| ST-AF-02 | AF visual one-agent definition | future working copy ADR; existing React Flow is representation | existing canvas/component tests preserved; semantic saving not claimed | 02 PLANNED |
| ST-AF-03 | AF immutable payload / layout | canonical format 3 in contracts/agent.py; layout separation ADR | existing version_payload_integrity and canvas-state tests; durable layout contract planned | 02 PLANNED |
| ST-AF-04 | AF working copy/candidate | explicit-save/generation ADR | new builder not implemented; no premature tables | 02 PLANNED |
| ST-AF-05 | AF canonical configuration | VersionInput / AgentVersion, restricted empty grants | existing test_agent_contracts.py and negative forbidden-tool tests | 02; existing backend preserved |
| ST-AF-06 | AF governed lifecycle / AF-07 | AgentFactoryService, Bench, Core approval/publication/activation | existing golden HTTP/browser lifecycle and registry rollback tests | 02; existing lifecycle preserved |
| ST-BN-01 | BN evaluations/provenance | BenchRepository/BenchRunner; new evaluations read API | existing bench_stream_contract, bench_engine and evidence integrity tests | 02; existing backend preserved |
| ST-BN-02 | BN-06 critical regression | BenchRegressionRepository and signed baseline comparison | existing test_bench_baseline_regression.py, test_bench_baseline_authority.py | 02; existing fail-closed gate preserved |
| ST-BN-03 | Core exact-hash human approval | approvals/engine.py; existing approval endpoints | existing governance_lifecycle_approvals and stale hash tests | 02; existing authority preserved |
| ST-BN-04 | Core sanitized audit | /resources/audits, actor/resource filters, authenticated envelope | test_workspace_api.py, test_workspace_snapshot.py; existing audit sanitation/security tests | 01 API PASS; 02 audit UI |
| ST-OP-01 | Assigned vs published operations | separate summary metrics; operations unavailable page | real inventory definitions and permission-aware shortcuts; no fake active/scheduled totals | 01 summary PASS; 02 Operations |
| ST-OP-02 | Manual execution / captured version | existing Runs/Core coordinator; /runs/:runId alias | existing captured-claim/idempotency/golden run tests; workspace.spec.ts old/new missing run routes | 01 alias PASS; 02 Console redesign |
| ST-OP-03 | Core RunResult provenance | run_state_repo.py; bounded runs detail; existing JSON/SSE | test_workspace_api.py actual captured claim and tampered signature, result withheld | 01 read API PASS; 02 Console UI |
| ST-OP-04 | Unknown outcome / reservation | existing coordinator/usage authority; attention list outcome_unknown | existing core execution security/recovery tests; benchmark historical unknown consumption fails closed | 01 attention PASS; 02 outcome UX |
| ST-OP-05 | Durable output / review | existing run output preserved; artifact registry ADR | output registry unavailable without enabled feature actions | 03 PLANNED |
| ST-WF-01 | Core graph/run/task ownership | WorkflowDefinition/Version/Run/TaskExecution ADR | future /workflows detail/builder routes tested unavailable | 03 PLANNED |
| ST-WF-02 | Typed DAG validation | allowlisted node/schema/quotas ADR; no arbitrary code executor | existing confined tool boundary remains tested | 03 PLANNED |
| ST-WF-03 | Single Core execution authority | owner/fence/reservation/checkpoint ADR; existing coordinator | existing single-owner and restricted PostgreSQL tests preserved | 03 PLANNED |
| ST-WF-04 | Durable review / unknown side effects | Core idempotency and exact-hash review ADR | no executable workflow or retry claim | 03 PLANNED |
| ST-WF-05 | Artifact/Deliverable scope/privacy | scoped immutable storage, safe preview ADR | /outputs/:id unavailable; no host filesystem access | 03 PLANNED |
| ST-WF-06 | AF-09 P0 Research → Content → Website staging | three-task executable workflow and human review ADR | no staging execution/publication claim in workspace delivery | 03 PLANNED |
| ST-BR-01 | BR-01–07 P0 evidence/abstention | EvidenceBundle ADR with support/conflict/neutral | /brief/:bundleId unavailable; no invented confidence | 04 PLANNED |
| ST-BR-02 | BR scoped authorized ingestion | internal-reference/document adapter ADR | no connector marked available | 04 PLANNED |
| ST-BR-03 | BR reference integrity | source digest/read verification ADR | no evidence backfill | 04 PLANNED |
| ST-BR-04 | BR evidence timeline/review | list/detail/lineage ADR | unavailable route has no feature actions | 04 PLANNED |
| ST-RL-01 | RL-01–04 incident investigation | dedup/state machine/evidence ADR | /relay/:incidentId unavailable | 04 PLANNED |
| ST-RL-02 | RL-05–06 exact-hash proposal | restricted disposable action / Core approval ADR | no production action or broader Hermes grant | 04 PLANNED |
| ST-RL-03 | RL-07 verified recovery | post-action health evidence ADR | action success not claimed as recovery | 04 PLANNED |
| ST-RL-04 | RL-08 / BN-05–07 safe replay | sanitized IncidentCapsule ADR | existing Bench no-live-write invariant retained | 04 PLANNED |
| ST-AU-01 | Core schedules | persisted timezone/occurrence/idempotency ADR | /automations unavailable; no browser/native scheduler | 05 PLANNED |
| ST-AU-02 | Single-authority scheduling | Core owner/fence and missed-occurrence ADR | nine-route runtime confinement preserved | 05 PLANNED |
| ST-AU-03 | Default-deny capabilities | future capability registry ADR | /capabilities unavailable; empty tool grants unchanged | 05 PLANNED |
| ST-AU-04 | Server-effective entitlement | summary usage.entitlement=unknown | no premium/payment/BYOK inference claim | 05 integration; external commercial program |

Workspace shell/Projects requirements in PRD sections 5–6 do not have separate ST identifiers. Evidence: studio.tsx, features/overview.tsx, features/projects.tsx, workspace.css; migration 016_workspace_structure; test_workspace_api.py, test_workspace_migration.py, test_workspace_authentication.py, test_workspace_persistence.py; workspace.spec.ts responsive themes/keyboard/axe, real division reload/edit/CAS/filter/project isolation and unavailable routes. Patterns R01/R02/R06/R09 are documented in studio-redesign-ux.md.

The current UI/backend remains operational for Factory/Bench/Approvals/Runs/Governance/Settings. Their later redesign acceptance is not promoted to complete by this matrix. All runtime/auth/governance acceptance remains attached to the actual full regression and exact-SHA CI results in progress.
