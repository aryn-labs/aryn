# Runs & Automations V1 — implementation and verification

## 1. Source and working tree

Work is on `development` in `D:\ARYN\aryn-labs\aryn`. Initial HEAD: `1ae31f35816e21b0d197edda67aaa8a0b5dbe1db` (`feat(workflows): add governed Workflow Builder Studio`). The initial working tree was clean. HEAD is unchanged; this implementation is uncommitted. No commit, push, merge, branch switch, deployment, user database modification or live inference was performed. The preceding Workflow commit remains local.

## 2. Audit

The actual HEAD already contains Agent Factory, shared StudioCanvas, Workflow Builder, immutable WorkflowVersion, WorkflowRun/checkpoints/artifacts/review, and Core Automations. `/runs` and `/automations` were scaffold routes. Existing scheduler contracts cover interval/daily/weekly, IANA timezone, exact approval, owner authority, revision, durable cursor, overlap/missed policy, pre-claim retry, daily admission budget, idempotency, recovery and reconciliation. Reimplementing those services would create competing authority.

The API uses scoped same-origin sessions/CSRF, permissions and signed evidence. `RunState`, `WorkflowRun` and `AutomationOccurrence` have different meanings. Private Chat and Bench require separate visibility; internal Workflow Core tasks must be inspected through their parent rather than counted again. The existing Projects resource drawer and Workflow run panel are the necessary navigation integration points. Home, Chat and Dashboard Shell product layouts remain intact.

## 3. Design reference

The complete `ARYN_Runs_Automations_Interactive_Design_v1.html` source was read, including its interaction code. Composition follows its compact inventory, filter row, right inspection drawer, four-step wizard, trigger choices and side review summary. The existing ARYN Dashboard Shell/tokens are retained. No prototype arrays, simulated execution, `innerHTML`, second frontend or static image UI was imported.

Opening this local HTML in the in-app browser was rejected by the browser protocol policy. No workaround was attempted. Visual comparison therefore uses the full prototype source and rendered application screenshots, not a claimed screenshot comparison against an opened prototype. Browser evidence below comes from the React application over disposable database/Core fixtures.

## 4. Runs architecture

`ExecutionReads` builds a bounded SQL union over the authoritative Core and Workflow ledgers, without a mirror table. Each request covers one authorized project. Agent candidates are governed direct/async/agent-preview runs; private Chat references, Bench/model-probe/legacy modes and Workflow internal tasks are excluded. Preview requires the initiating actor's signed accepted audit and existing Blueprint/Working Copy authorization.

Filtering, literal search, date range, stable ordering and pagination occur on the server. HMAC continuation tokens bind actor, organization, project, filters, ordering and time range; they expire after one hour. Pages default to 25, maximum 100. The frontend merges bounded authorized-project pages, and labels its count as records loaded, not a global aggregate. An invalid project cannot borrow the active selector's scope.

Agent detail verifies the captured Core claim/provenance, displays only permitted sanitized input/output, actual model/provider/runtime and recorded usage, and includes verified persisted audit envelopes. Workflow detail verifies its signed parent and frozen version, displays actual task states/traversed edges, and reuses shared StudioCanvas read-only. The graph's layout is presentation only. Workflow duration is unavailable because its contract has no completion timestamp; unknown agent duration is unavailable rather than inferred.

## 5. Automations architecture

The frontend uses existing Core definitions/occurrences/events, with scoped paginated catalogs and definition drawers. The four steps are Target → Trigger → Policy → Review. Discovery and exact-pin checks use Core; creation starts paused. Approval binds the server configuration hash and revision. Enable/pause and manual delivery require explicit actions. Edits increment revision, pause the definition, invalidate approval and clear its webhook credential.

Conflicts preserve local form state; server reload requires confirmation. Unsaved navigation is guarded. Deep-link permissions use the resource's owner project. Drawer identity changes remount its state so confirmations, manual intent and one-time credentials do not cross resources. Catalogs are invalidated after control mutations so their displayed approval/status follows the detail. Manual intent/revision survive refresh in scoped session storage; webhook secrets never use storage or Query cache.

## 6. Reused components

Dashboard Shell, WorkspaceProvider, session/theme/i18n, TanStack Router/Query, Zod API client, existing Button/Dialog/DataState, StudioCanvas, workflow registry/edge-state mapping and ArtifactPanel are reused. New shared OperationsUI provides status, facts, fields, drawer, tab navigation and Contracts & Boundaries dialog. Runs artifact inspection does not expose review forms; review remains in Workflow Studio through its existing exact receipt authority.

## 7. API/contracts

All authenticated paths are below `/api/projects/{project_id}`:

| Path | Purpose |
|---|---|
| GET `/executions` | Unified scoped observation, q/kind/status/order/since/until/after/limit |
| GET `/executions/{agent|workflow}/{id}` | Authorized detail and frozen workflow evidence |
| POST `/executions/{agent|workflow}/{id}/stop` | Existing Core cancellation; return actual refreshed status |
| GET `/automations` | Existing catalog enriched with actual approval/preview/target label; trigger filter added |
| POST `/automations`, POST `/automations/{id}` | Existing create/edit with expected revision |
| POST `/automations/{id}/approve`, `/state`, `/run` | Existing exact approval, enable/pause, manual intent |
| GET `/automations/{id}/occurrences`, `/events` | Signed bounded history |
| POST `/automations/{id}/occurrences/{occurrence}/reconcile` | Existing reason + no-retry acknowledgement |
| GET `/automation-targets`, POST `/automation-targets/check` | Bounded discovery and exact scoped pin preflight |
| POST `/automation-preview` | Five actual UTC/local offset instants; no timed preview for webhook |
| GET `/automation-triggers` | Actual server mode, supported kinds, ingress/MCP readiness and scheduler status |
| POST `/automations/{id}/webhook` | Scoped revision-bound credential rotation/revocation; one-time no-store response |

External POST `/ingress/webhooks/{opaque_issuance_id}` is a separate authenticated trigger transport into the same Core occurrence queue. It is not a session mutation or a free execution endpoint. Unknown GET ingress paths do not render the SPA. Authenticated mutations retain existing session/CSRF/Origin checks. `Prefer: respond-async` on manual delivery returns a durable queued receipt (HTTP 200 for compatibility); the existing lifespan owner dispatches it. Default synchronous behavior remains compatible.

## 8. Custom Cron

`Schedule.kind` adds `cron` and `webhook`; `cron_expression` is nullable and required only for cron. Cron accepts five numeric fields: minute 0–59, hour 0–23, day 1–31, month 1–12, weekday 0–7 (0 and 7 Sunday). Supports wildcard, comma lists, inclusive ranges and positive bounded steps, including numeric-start steps. When both day-of-month/day-of-week are restricted, they use OR; a literal `*` marks an unrestricted field. Names, macros, executable expressions, seconds, `L`, `#`, `?`, invalid bounds and impossible calendar patterns are rejected. Maximum expression length is 160. Aware start timestamps are bounded to years 2–9990 to preserve representable planning headroom.

The same Core scheduler computes next instants/preview and persists its cursor. DST gaps skip; ambiguous wall time uses fold 0 once. Search is bounded to eight years. Catch-up selects only the latest 1–3 instants within seven days, with older time recorded as a coalesced interval, without invented individual counts. Reverse selection avoids iterating years of minute backlog. A measured historical per-minute backlog retained three instants in 0.015205s locally, versus 4.906s before the optimization; this is an engineering measurement, not an SLA.

Frequency is never browser authority: one Core owner, per-tick definition/delivery bounds, queue cap, daily admission quota (1–100), current permissions/approval, model policy, token reservation and fence remain enforced. Cold scheduler delivery now refreshes the actual runtime model catalog before claim; it does not mark unknown models available or bypass model permissions.

## 9. Secure Webhook

Ingress is disabled by default. `ARYN_WEBHOOK_INGRESS_ORIGIN` must be an explicit non-loopback HTTPS origin equal to the authenticated Hosted Studio public origin. Local remains disabled even if this setting is supplied; there is no tunnel or fake public URL. HTTPS is validated through existing transport/host/trusted-proxy rules. Caller-supplied forwarding cannot set the internal verified-transport flag. Production TLS termination/public ingress still needs deployment validation.

Authentication is **scoped bearer over TLS**, an authenticated request scheme rather than a claimed HMAC implementation. Core generates 32 random bytes, displays the bearer once, and stores only SHA-256 in the signed definition. The opaque endpoint identity is an existing immutable issuance event ID, avoiding a table or unbounded credential scan. Rotation rejects the former credential; revoke blocks future signals; editing invalidates the binding. The hash binds the current reviewed configuration. Revocation does not erase durable accepted history or assert cancellation of an already admitted effect; pause/edit retain existing control semantics.

Protocol: `Authorization: Bearer <one-time-token>`, `Content-Type: application/json`, `X-ARYN-Timestamp: <offset-aware ISO instant>` and body `{"event_id":"source-id","event":"trigger"}`. Absolute timestamp skew is at most five minutes. Event IDs are bounded ASCII. Unknown fields, duplicate JSON keys, target/model/policy overrides, commands and credential-bearing signal data are rejected. Cookies and Origin headers are rejected on this machine-to-machine endpoint. Body streaming is capped at 4096 bytes. TLS protects the request; the timestamp is not a separately signed HMAC field.

Dedup keys contain a hash of event ID, never raw payload; a signed signal digest detects conflicts. Identical repeats return the original occurrence and never infer again. Definition row lock plus unique occurrence key serialize delivery. Accepted signals are limited to 12/minute/definition in durable storage; a separate in-process ingress ceiling is 60 attempts/minute. The latter is not a distributed edge limiter. At most three ready deliveries queue; overlap excess is explicitly skipped. Current human owner, exact approval, target pins, scope and Core fence are checked again. The existing scheduler performs later admission and binds the actual Core Run atomically before effects.

Raw inbound bodies and raw event IDs are not retained. Signal digests and control/admission events follow existing immutable signed-history retention; this task adds no deletion/cleanup job. Credential issuance, rotation/revocation and accepted delivery are signed/audited. Rejected unauthenticated attempts have safe HTTP errors and a local limiter; this does not claim a durable per-attempt security ledger or distributed abuse monitoring.

## 10. Trigger registry and policy

Registry entries are Interval, Daily, Weekly, Custom Cron, Secure Webhook and MCP Event. Availability derives from API capability facts. MCP is reserved and disabled; webhook is conditional on configured Hosted ingress. No sample templates, arbitrary scripts or new runtime tools are enabled.

Core policy remains overlap skip/queue, missed skip/catch-up, catch-up 1–3, daily admissions 1–100, task token ceiling 128–32768, attempts 1–3 and backoff 60–3600s. Retry only covers explicit readiness failure before Core claim. Unknown effect/consumption/lost reply after claim holds the schedule until explicit acknowledgement; reconciliation does not settle Core's run or reservation. There is no generic Runs retry action.

## 11. Persistence and compatibility

No schema migration or parallel ledger was necessary. Existing signed automation definition JSON accommodates optional credential metadata; occurrence JSON accommodates optional trigger digest. Existing scoped events, mutable protected heads, indexes/foreign keys/unique keys and PostgreSQL guards remain authoritative. Webhook's internal non-null cursor sentinel is never displayed as a future execution date and is never planned as a timed trigger.

New optional fields do not rewrite historical records or approvals. Old signatures are verified over their stored payload before typed parsing. The frontend accepts old schedules missing the additive cron field. Creation/edit uses the current schema and requires fresh approval. Database version remains `024_project_metadata`; no backfill, destructive rollback or deletion of governed history occurred.

## 12. Changed files

Frontend: `.github/workflows/quality.yml`, `apps/web/package.json`, `apps/web/playwright.operations.config.ts`, `apps/web/e2e/operations.spec.ts`; router `src/app/router/index.tsx`; shared `src/components/operations/{OperationsUI.tsx,operations.css}`; `src/features/runs/{api.ts,RunsPage.tsx,RunDrawer.tsx,WorkflowRunGraph.tsx}`; `src/features/automations/{api.ts,triggers.ts,AutomationsPage.tsx,AutomationBuilder.tsx,AutomationDrawer.tsx}`; integration `src/features/projects/components/ProjectResourceDrawer.tsx`, `src/features/workflows/WorkflowRunPanel.tsx`, `src/hooks/use-workspace-queries.ts`; i18n `src/i18n/{index.ts,operations.ts}`; unit test `src/test/operations-contracts.test.ts`.

Backend: `.env.example`, `modules/core/automations/{cron.py,webhook.py,recurrence.py,service.py}`, `modules/core/records.py`, `packages/config.py`, `packages/contracts/automation.py`, `services/api/{studio.py,automations.py,execution_reads.py,executions.py}`.

Tests: `tests/operations_browser_server.py`, `tests/unit/{test_automation_cron.py,test_automation_ingress_config.py}`, `tests/integration/test_runs_automations.py`, `tests/security/{test_automation_webhook.py,test_9router_boundary.py,test_9router_discovery.py}`, `tests/postgresql/{test_automation_persistence.py,test_webhook_persistence.py}`. The two existing gateway security tests explicitly allowlist the new non-secret ingress configuration variable; provider credential restrictions remain enforced. Documentation: this report and `docs/core-automations-contracts.md`. Frontend tests remain under `apps/web/src/test` and `apps/web/e2e`, separate from feature source. No production dependencies were added.

## 13. UI/Core navigation

Runs ↔ Automation occurrence uses real automation/occurrence/run IDs with verified lineage. Workflow detail links to its Studio, frozen version/run, existing artifact preview/download and Project Results. Agent detail links to the actual Blueprint when available. Projects resource drawer links parent Workflow runs to Runs, including internal task-parent provenance; it does not manufacture a second parent. Source attribution is based on signed references, not display names. Cross-project deep links fail closed. Stop returns and displays the actual refreshed Core state, rather than treating accepted cancellation as confirmed cancellation.

## 14. Browser evidence

Evidence is ignored under `.local/runs-automations-evidence/`. It is rendered React UI using migrated disposable SQLite, signed governance and actual Core/scheduler/Workflow services with `IsolatedTestRuntime`. Provider/model/usage in these images are explicitly test fixtures, not production inference or billing.

| View | File |
|---|---|
| Runs desktop dark/light | `runs-desktop-dark.png`, `runs-1440-light.png` |
| Runs mobile | `runs-390-dark.png`, `runs-390-light.png` |
| Agent / Workflow details | `agent-run-detail.png`, `workflow-run-detail.png` |
| Unknown / cancelled | `outcome-unknown.png`, `workflow-cancelled.png` |
| Artifact | `run-artifact.png` |
| Automation inventory/detail | `automations-catalog.png`, `automation-detail.png` |
| Wizard Target / Policy / Review | `wizard-target.png`, `wizard-policy.png`, `wizard-review.png`, `wizard-review-top.png` |
| Trigger / Cron | `trigger-selection-webhook-unavailable.png`, `custom-cron.png` |
| Approval / occurrences | `approval-exact-hash.png`, `occurrence-history.png` |
| Reconciliation / lost response | `unknown-reconciliation.png`, `manual-response-recovery.png` |
| Automation Workflow parent | `automation-workflow-run.png` |
| Mobile builder | `builder-390-dark.png`, `builder-390-light.png` |
| English | `runs-english.png`, `builder-english.png` |

Secure Webhook screenshot deliberately shows its unavailable Local state. Hosted protocol security is verified by offline OIDC/API tests; there is no claimed screenshot of a deployed public webhook or an exposed real secret. Screenshot UI composition was inspected; filters, table, independent drawer and single-column mobile wizard follow the prototype while keeping ARYN Shell.

## 15. Automated verification

All log paths below are relative to the repository's ignored `.local/` directory. Browser tests use actual application/API/Core code with a disposable database and explicit isolated runtime fixtures. They do not establish production provider, billing or public ingress readiness. Counts across focused backend suites overlap and must not be added as unique coverage.

| Check | Observed result | Log |
|---|---|---|
| Frontend unit | 113 passed, 15 files | `runs-automations-unit.log` |
| Operations browser | 15 passed | `runs-automations-operations-final.log` |
| Agent Factory browser regression | 14 passed | `runs-automations-agents-regression.log` |
| Workflow browser regression | 14 passed | `runs-automations-workflows-regression.log` |
| Projects browser regression | 12 passed | `runs-automations-projects-regression.log` |
| Chat browser regression | 29 passed | `runs-automations-chat-regression.log` |
| Home and Shell browser regression | 90 passed | `runs-automations-shell-regression.log` |
| Core scheduler/Cron/read projection focused checks | 89 passed | `runs-automations-trigger-final.log` |
| Webhook/config/gateway security checks after allowlist fix | 49 passed | `runs-automations-security-final.log` |
| Installed Hermes guarded gateway test, isolated rerun | 1 passed | `runs-automations-native-boundary.log` |
| Broad offline backend run | **3 failed, 1036 passed, 5 skipped, 132 deselected** | `runs-automations-offline.log` |
| Frontend lint, format, typecheck/build | Passed; build retains the existing >500 KB chunk warning | `runs-automations-lint.log`, `runs-automations-format.log`, `runs-automations-build.log` |
| Ruff, repository/action pin hygiene, actionlint | Passed | `runs-automations-ruff.log`, `runs-automations-hygiene.log`, `runs-automations-actionlint.log` |
| Changed-source secret scan | No leaks found; redacted scan excludes local databases/evidence | `runs-automations-secret-scan.log` |

The browser regressions total **174 passing tests** across six suites. Operations verifies persisted inventory, parent workflow graph/artifact, cancellation and catalog refresh, all three timed schedule forms plus Cron, explicit exact-hash approval/activation, actual occurrence-to-Run linkage, waiting review, unknown reconciliation, idempotent recovery after a lost manual response, CAS conflicts and unsaved exit, foreign-project rejection, ID/EN, 1440/768/390 dark/light, Axe, independent drawer Escape and no page overflow. A final visual check found target discovery briefly using an unavailable message while loading; it now displays loading/error/permission states separately, and browser snapshots wait for actual eligible options.

The broad backend run is **not reported as PASS**. Two failures were strict environment allowlists missing the newly introduced `ARYN_WEBHOOK_INGRESS_ORIGIN`; both were updated explicitly and pass in the 49-test security/config rerun. The installed Hermes test failed during its guarded subprocess turn in the combined run; its isolated rerun passed in 34.51 seconds. That result does not prove the combined-run failure cannot recur. The full 23-minute backend suite was not repeated after the targeted fixes; later Cron and ingress changes were checked by the focused suites above. Five skips comprise three owner-opt-in live-provider tests and two unavailable local Hermes API-key tests. No paid model request was made.

The five existing product browser regression suites ran before the last Operations-only catalog refresh/loading refinements. The final 15-test Operations rerun and frontend build/lint/format ran after those refinements. Its Windows server log contains a nonfatal `ConnectionResetError` callback during the lost-response recovery case; that case and the suite passed. This is retained in the log rather than suppressed.

`runs-automations-evidence/core-checkpoints.json` contains a safe fixture evidence export: five verified parent records, two automation-to-occurrence-to-Core links, two direct Agent parents, and a frozen Workflow parent with persisted task Core Run ID and actual traversed edges `edge_0` and `edge_1`. The export marks `test_fixture: true` and `IsolatedTestRuntime`; it excludes secrets, raw prompts and sensitive claim fields. It proves the observation mapping against Core fixtures, not a live provider inference. `runs-automations-verification.json` records source/log/screenshot digests for local review.

Live PostgreSQL was not executed locally: `ARYN_TEST_POSTGRES_ADMIN_URL` is absent and Docker Desktop's Linux daemon is unavailable. Collection found 132 live PostgreSQL tests; fixtures do not fall back to SQLite. New wrappers cover cron budget/cold catalog, union/cursor/filters/private Chat/preview, deferred delivery and hosted webhook delivery/rotation/contention. Provider live and deployed Hosted TLS/public routing are not tested or claimed.

## 16. CI readiness

Operations E2E runs on browser shard 2 with Agent Factory; Workflow remains shard 3, Chat/Projects shard 1, Home/Shell spans three shards. Existing backend Windows/Linux, frontend, PostgreSQL, security/native runtime, Required Quality Gates and Validated Delivery Artifact remain required. Local actionlint/hygiene checks are separate from a GitHub Actions result. No new remote run/artifact exists because the change has not been committed or pushed. The previous Agent Factory commit's CI is not evidence for this source.

## 17. Implemented scope

Scoped unified Runs catalog/detail, actual status/evidence/timeline, read-only frozen Workflow graph, safe stop, Automations catalog/detail/four-step builder, server previews, all five supported trigger contracts, governed Cron/Webhook extensions, exact approval/state/manual/history/reconciliation, project navigation, ID/EN, dark/light, responsive and automated coverage are implemented. Operational success is limited to the environments actually tested above, not a production-readiness assertion.

## 18. Limits and technical debt

No global aggregate from partial pages, granular tool/token telemetry, fabricated Workflow duration, generic effect retry, automatic publication/approval, second worker, unrestricted tools or frontend scheduler. Run timeline is persisted audit/checkpoints; fast intermediate states may not be visible between polling reads. Graph layout in inspection is deterministic, not an editable persisted Studio layout. Loaded per-project pages are bounded, but the combined catalog is not a server-global cursor/aggregate. Immutable signed history retains digests; deletion/retention infrastructure is out of scope.

Final manual platform UAT remains for the user. Large wizard/drawer components can be split into domain hooks/sections as the product expands. Existing bundle size warning and first-party dependency deprecations are not hidden. Ingress's local attempt limiter is not a distributed defense; deployment needs edge limits and operational monitoring. A cancellation/rotation/pause response never proves rollback of effects already admitted by Core.

## 19. MCP & Integrations dependencies

MCP Event requires a real authenticated source adapter, event capability and lifecycle, scoped subscription ownership, event schema/replay/idempotency, Core admission policy, revocation/recovery and offline/live security tests. Registry availability remains false until these exist. This task neither enables MCP admin nor creates an integration marketplace.

## 20. Hosted/Hybrid dependencies

Hosted requires validated HTTPS origin/TLS termination/trusted proxy, real OIDC provisioning, protected signing storage, restricted PostgreSQL writer/migrations, one fenced scheduler owner, durable operations/backup/observability, deployment/edge replay/rate tests and governed runtime/model readiness. Local execution stops when the device/process stops; Hosted is not automatically an SLA. Hybrid relocation, execution-environment selection and billing/subscription entitlements need authoritative contracts rather than frontend switches. No silent runner fallback or relocation was added.
