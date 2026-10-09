# Studio requirement traceability

Current audit source: `40df9d1f894b257df3a277c4623466d6d03541dc`; dependency workflow [37837626257](https://github.com/aryn-labs/aryn/actions/runs/37837626257) completed/success, 14/14 jobs. This matrix covers implemented Agent editing/manual operations and preserved workspace behavior. Exact implementation source and terminal CI are recorded in [delivery evidence](studio-redesign-progress.md); dependency CI is not evidence for new code. Official references below derive from the supplied PRD/repository; normative PDFs are absent, so no missing PDF section is claimed verified.

Verified implementation source: `2ca9dca575a2cfcc95505547e4426fe95e7e97b4`; [current source CI](https://github.com/aryn-labs/aryn/actions/runs/37882643080) completed/success, 14/14 jobs. Every local PASS below is additionally covered by that exact-source workflow. Evidence-only closure CI is checked separately before delivery.

| ST-ID | Official / product relation | API / contract and source | Evidence / negative coverage | Delivery owner / status |
|---|---|---|---|---|
| ST-DATA-01 | Core tenant/RBAC, workspace switch | lib/workspace-types.ts; studio.tsx; lib/api.ts | workspace-shell.test.tsx and workspace.spec.ts: AbortSignal, late A response, cache removal, 403 hide | 01 PASS workspace |
| ST-DATA-02 | Core scoped read model | workspace_reads.py; /summary, /resources, bounded /lifecycle; resource-browser.tsx | workspace API/editor/browser tests: scoped paging/detail, no run output in lists, canonical history without full snapshot | PASS workspace and Agent/Bench/Operations UI; future domains 03–05 |
| ST-DATA-03 | Core scoped contracts | HMAC cursor, limit 1–100, newest/oldest, filter whitelist | test_workspace_api.py: forged, altered-sort, cross-project cursor, wildcard literal, duplicate/unknown params, 401/403/404 | 01 PASS |
| ST-DATA-04 | Workspace performance | benchmark_workspace.py; workspace_dataset.py; lazy Studio feature imports | workspace.spec.ts large navigation/summary thresholds; test_workspace_snapshot.py verifies every audit with one audit SELECT | PASS workspace/lifecycle/history; legacy Settings snapshot residual |
| ST-DATA-05 | Core commit authority | WorkspaceService and AgentEditor generation/CAS; Factory supplied transaction | SQLite/PG race, revoked membership, discard tombstone, stale generation, injected audit failure rollback | PASS divisions and working copy |
| ST-AF-01 | AF registry / AF-07 rollback | factory.tsx, version-detail.tsx, paged versions, existing activation registry | nested diff/key-order tests; registry API/browser known-good rollback; active config beyond 25 candidates | PASS local and exact-source CI |
| ST-AF-02 | AF visual one-agent definition | agent-builder.tsx; eight semantic nodes/typed inspector/full form | agent-editor.spec.ts completes all fields, keyboard, themes 390/768/1440; no executable edge gesture | PASS local |
| ST-AF-03 | AF immutable payload / layout | AgentDraft to canonical format 3; separate actor layout; migration 017 | API/PG/browser every saved canonical field, drag/layout keeps version count/hash, published immutable | PASS local |
| ST-AF-04 | AF working copy/candidate | AgentEditor save/read/discard/candidate; independent generation | API/PG concurrent winner/conflict, tombstone, reload/restore/undo/discard, incomplete JSON and browser Back confirmation; no prompt storage | PASS local |
| ST-AF-05 | AF canonical configuration | strict nested AgentDraft/VersionInput; server catalog; empty grants | forbidden authority/fallback/suite/range tests; all-field roundtrip; model provenance mismatch regressions | PASS local |
| ST-AF-06 | AF governed lifecycle / AF-07 | existing Factory/Bench/Core; explicit candidate and manual Operations | real HTTP/browser Builder to Bench/approval/publish/assignment/Operations/captured run; baseline/regression and known-good rollback | PASS local |
| ST-BN-01 | BN evaluations/provenance | bench.tsx, paged evaluations, exact detail; signed BenchRunner | actual scenario/grader/result/evidence UI, bench_stream_contract, bench_engine, evidence integrity and browser | PASS local |
| ST-BN-02 | BN-06 critical regression | existing signed BenchRegressionRepository and baseline UI | baseline regression/authority/API and browser; critical failure blocks good aggregate | PASS local; gate preserved |
| ST-BN-03 | Core exact-hash human approval | approval-queue.tsx, approvals metadata, existing exact Core lifecycle | actual scope/hash/evaluation/reviewer; stale/tampered/forged approval tests; no read-derived publication authority | PASS local |
| ST-BN-04 | Core sanitized audit | governance-browser.tsx; actor/resource/q/cursor, lazy sanitized envelope | API/snapshot sanitation and real browser audit open/close, mobile/themes/axe; viewer read-only | PASS local |
| ST-OP-01 | Assigned vs published operations | operations.tsx; active assignments/published inventory/readiness/budget | golden browser begins run from actual Core Operations link; verified metadata and large navigation | PASS local |
| ST-OP-02 | Manual execution / captured version | runs.tsx; /runs history, /runs/new, /runs/:id Console | historical A stable after new B/completion/reload; unrelated selector cannot replace captured version; 404 has no false canvas | PASS local |
| ST-OP-03 | Core RunResult provenance | bounded captured projection, signed claim; existing JSON/SSE/cache | core_execution_contract preflight rollback/parity/cache; tamper withholds results; actual Console limits/output/audit | PASS local |
| ST-OP-04 | Unknown outcome / reservation | capturedCorePanel; actual Core stop/usage/reservation | cancel ACK/unknown/recovery/idempotency; editor API completed stop remains completed, forged confirmation rejected | PASS local; no fabricated trace/cost |
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

All runtime/auth/governance acceptance remains attached to actual full regression and exact-SHA CI results in progress. R02/R03/R05/R06/R09 and visual/performance datasets are documented in UX and progress. ST-OP-05, ST-WF, ST-BR, ST-RL and ST-AU future acceptance is not promoted by completion of Agent editing/manual operations.
