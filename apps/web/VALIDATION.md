# ARYN Studio — validation

## Home audit refinements — current, 10 October 2026

Scope: Home only, on the local `development` working tree. The shell, global navigation, selectors, theme foundation and other modules are preserved. Pre-existing deletions/edits remain untouched. No backend/API/database/dependency changes, commit, push, merge or changes to `main`.

### Findings and corrections

- The original composer combined its outer focus border with the global textarea outline and allowed manual resizing. It now uses one outer border/focus cue, a borderless 16px textarea with no manual resize, bounded automatic height (200px desktop/tablet, 168px mobile), and internal scrolling beyond the cap. Input and button occupy separate flow rows; shrinking text and viewport changes recalculate height.
- Continue previously opened Guided Creation automatically. It now opens a conversation surface in the main Home workspace, preserves the user's text as **Not sent**, and explicitly reports the missing conversation API. Follow-up input is available for preparation, with Send disabled. There is no simulated assistant message, network send, loading animation or streaming claim.
- Guided Creation opens only through explicit quick actions or **Create Agent draft / Create Workflow draft**. Review and the scoped, unsaved handoff remain unchanged; no publish, approval, grant or agent execution occurs.
- Workspace service warnings now occupy a compact collapsed disclosure. Keyboard users can expand it to read individual failures and use existing scoped retries. Available work and New/Active/Important Issues derivation remain intact.
- Agent rows show actual description and creation date. Known internal audit codes are mapped to customer-facing labels, while resource identity/detail contracts remain intact. Unknown event types receive a neutral recorded-activity label, never an inferred success. Bench gate failures and uncertain outcomes use readable labels. Home headings, input, list text and supporting copy are larger without changing shell typography or tokens.

### Audit of actual AI contracts

Inspected `services/api/studio.py`, the registered workflow/intelligence/automation routes, `services/api/workspace_reads.py`, `modules/core/capabilities.py`, Core permission/execution code, `packages/contracts/agent_builder.py`, the Hermes adapter and deployment/runtime documentation.

| Existing capability      | Actual contract                                                                                                                        | Consequence for Home                                                                              |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Assigned agent inference | `POST /api/projects/{project_id}/runs`; `RunInput` requires `assignment_id`, `prompt`, `idempotency_key`, `allow_remote_model` consent | Executes a published, assigned agent through Core; **not used as Home chat**                      |
| Run JSON/SSE             | Core validation/progress and terminal run result/error; authenticated, budgeted, exact-model execution provenance                      | Does not define persistent conversations, messages, safe Home assistant policy or token streaming |
| Capability registry      | `aryn.agent.text` requires a pinned published version, active signed assignment, exact runtime model, Core budget and empty grants     | Does not authorize a generic Home assistant conversation                                          |
| Builder working copy     | Typed definition CRUD and version creation                                                                                             | Not an AI conversational or automatic draft-generation contract                                   |
| Hermes text completion   | Private authenticated server/runtime boundary                                                                                          | Never called from the browser; no runtime key or prompt is exposed to it by Home                  |

**Blocker: no safe ARYN Home conversation endpoint exists in the audited API. Real assistant responses, sending, loading/streaming and server chat errors are not implemented or claimed.** The production UI shows the explicit unavailable state instead. No model inference was invoked during this audit.

### Backend contract needed before AI integration

This is a proposed requirement list, not existing routes/fields or an implemented contract. Backend ownership must agree and implement it in a separate authorized scope.

1. A versioned project-scoped assistant capability/permission projection and conversation/turn API using existing same-origin authenticated sessions and CSRF. Core derives organization, user and project access from trusted session context, validates every referenced conversation/message, and revalidates access after awaits. Chat permission cannot be inferred from blueprint/version creation permission or role labels.
2. Bounded input, server-owned conversation/message IDs, parent revision/order checks and an idempotency key. Define retention, reload/read behavior and whether an unsent draft can persist. Reject client-supplied authority, tool grants, system instructions, runtime sessions/secrets or unrelated resource scope.
3. Core admission for a **text-only assistant turn**, with token/time/cost policy, explicit remote-model consent, exact configured model/provider and no silent fallback. Define how this differs from executing a published assigned agent; a conversation turn must never implicitly publish, approve, grant tools, create an assignment, dispatch an assigned agent run or perform external actions.
4. A typed response with authoritative delivery/terminal state, ordered user/assistant messages, timestamps, correlation IDs and actual model/provider provenance. Usage is nullable/unavailable unless measured. Assistant content is untrusted text; structured Agent/Workflow draft proposals, if supported, need their own validated schema and explicit human selection before any separate mutation.
5. Define synchronous completion first or a documented streaming protocol with accepted/delta/completed/error events, event/turn identity and ordering. Cancellation/disconnect must distinguish request abort from confirmed backend cancellation and unknown outcome; reconnect/retry must reuse idempotency without duplicating inference or charges. Do not infer success merely from transport completion.
6. Sanitized typed errors for unauthorized/forbidden, unavailable, input rejection, revision/idempotency conflict, budget/rate limit, provider failure and timeout/unknown outcome. Define retry eligibility server-side; never expose credentials or raw provider exceptions.
7. Positive and negative backend tests for organization/project/user isolation, revoked access, CSRF, replay/idempotency, budgets, exact model, cancellation/unknown delivery, secret sanitation and absence of publication/execution/tool-grant side effects. Only after those contracts exist can Home show a real AI response or loading/streaming.

### Current verification and evidence

- `npm run lint`: passed, zero warnings.
- `npm run typecheck`: passed, TypeScript strict.
- `npm test`: **50 passed** (20 shell, 18 Home component/contract, 9 state, 3 label tests).
- `npm run build`: passed. Existing Zod/Rollup annotation warnings do not prevent the build.
- Home E2E: **40 passed**, including three workspace conditions, dark/light at 1440/768/390px, auto-growth cap/shrink, no double border/resize/overlap, conversation focus, no automatic drawer, disabled follow-up send, explicit draft review, scoped retries, Axe and no horizontal overflow. No external requests or business mutations occur in the conversation tests.
- Existing shell E2E: **26 passed** in a separate regression run. Total: **66 browser tests**. Both suites passed; reports are separate to preserve each run's evidence.
- SHA-256 preservation: **35 existing source files outside Home unchanged**; backend/dependencies remain untouched. `git diff --check` passed, and test fixture names are absent from production JavaScript.

Evidence is in ignored `D:/ARYN/aryn-labs/aryn/.local/home-audit-v2/`:

- `home-{new,active,issues}-{1440,768,390}-{dark,light}.png` / `-lower.png`: isolated test contracts, not runtime sample data.
- `conversation-{1440,768,390}-{dark,light}.png`: clearly **unavailable/unsent** conversation, not a successful AI interaction.
- `guided-review-*` / `home-details-*`: explicit draft review and detail drawer checks.
- `foundation-before.json`: hashes for all existing frontend source outside Home, used to verify preservation.
- `working-tree-before.txt`: recorded pre-existing worktree state.
- `apps/web/playwright-report/index.html`: current 40-test Home report.
- `.local/home-audit-v2/shell-report/index.html`: 26-test shell regression report.
- `production-conversation-{1440,768,390}-{dark,light}.jpg`: current production bundle with the actual authorized Local API session and a manually entered **unsent** message; no AI response is represented.
- `production-home-{1440,768,390}-{dark,light}.jpg`: current Home and actual backend resources; unavailable services remain honest and collapsed.
- `production-existing-session.json`: live DOM state/overflow measurements. New/Active scenarios use test-only contracts; the live project is in Important Issues.

The HTML reference and previous screenshots were compared with the current Home captures. Neutral token surfaces, turquoise focus/action accents, whitespace, compact lists and drawer foundation are retained; composer behavior follows the latest request in place of the prototype's automatic drawer. The existing Local server still returns 404 for workflows, Relay and workflow output reviews. Those integration gaps are explicit; no conversation endpoint, backend behavior or successful AI response is claimed.

## Earlier Home / Overview validation, 10 October 2026

Implemented on `development`, Windows, Node 22.14.0. No commit, push, merge, `main`, backend, database, migration or API contract changes. The owner's existing frontend deletions and unrelated edits are preserved. Dependencies are unchanged by this Home implementation.

The primary Home reference is `C:/Users/User/Downloads/ARYN_Home_Interactive_Concept.html`. Its New, Active and Attention content was inspected and captured at 1440, 768 and 390px. Home preserves the existing App Shell and uses its Standard layout, query/session providers and semantic theme tokens. SHA-256 checks against `.local/home-v1/shell-before.json` confirm no changes to shell components, providers, navigation components or theme styles during this implementation.

### Checks actually run

| Check                       | Current result                                                                                                                                            |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `npm run lint`              | Passed with zero warnings                                                                                                                                 |
| `npm run typecheck`         | Passed in strict mode                                                                                                                                     |
| `npm test`                  | **43 passed**: 20 existing shell, 14 Home component/contract, 9 Home state tests                                                                          |
| `npm run build`             | Passed; production bundle generated                                                                                                                       |
| `npm run test:e2e`          | **60 passed**: 26 existing shell and 34 Home E2E tests                                                                                                    |
| Frontend `git diff --check` | Passed                                                                                                                                                    |
| Fixture isolation           | Test-only names absent from built application assets                                                                                                      |
| Visual and overflow audit   | All three Home conditions at 1440×900, 768×900 and 390×900 in dark/light mode; no page/workspace horizontal overflow                                      |
| Accessibility               | Axe WCAG 2 A/AA and 2.1 AA: zero violations in tested Home, Guided Creation and details views; keyboard focus trapping/return and route navigation passed |
| Existing API integration    | Production build opened through the existing authenticated Local API at 8710; six viewport/theme checks show real work and no horizontal overflow         |

### User-request traceability

The following labels identify sections of the user's Home request, not private PRD P0 identifiers.

| User requirement                            | Implementation and positive evidence                                                                                            | Relevant negative evidence                                                                                                              |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| §1/§2: modular Home and preserved shell     | `features/home` components, scoped hook, pure derivation and contracts; compact lists and closable drawers                      | Shell/provider/navigation/theme hashes unchanged; no permanent inspector, prototype navigation or scenario switcher                     |
| §3A: confirmed New workspace                | Composer, three actions and Getting Started; work/activity sections hidden                                                      | Unknown inventory, 404/503 and loading do not classify as new                                                                           |
| §3B: Active workspace                       | Actual agent/workflow names and revisions, recorded run/work audit activity, resource inspection                                | No invented workflow status or creation timestamp; setup audits do not imply work                                                       |
| §3C: Important Issues                       | Attention precedes Continue Working; server failures, blocking Bench, allowed Relay records and verified pending reviews ranked | Closed/informational records, unverified candidates and unauthorized actions excluded; arbitrary attention URLs rejected                |
| §4: Composer and Guided Creation            | Agent/Workflow selection, objective/output/integrations, review and scoped route handoff                                        | No business POST, publish, approve, grant or execution; private input absent from URLs/storage; reload discards unsaved brief           |
| §4: isolation and cancellation              | Organization/project query keys; consumed AbortSignal; scope change resets input/details                                        | Nested foreign-scope agent/workflow/comparison data rejected; revoked access hides private content; foreign user/project brief rejected |
| §4: honest availability and recovery        | Scoped retries; known work retained during partial service failure; loading skeleton and accessible details                     | Required service failures display error/unavailable; no fake success or empty workspace inference                                       |
| §6: responsive, theme, focus and navigation | Both themes at all requested widths; drawer keyboard trap, Escape and focus return; existing shell navigation still passes      | No horizontal overflow, hidden focus targets or inaccessible project choices in tested views                                            |

Tests are in `src/features/home/tests`, `src/test/shell.test.tsx`, `e2e/home.spec.ts` and `e2e/shell.spec.ts`. Fixture imports are confined to tests. `home-state.test.ts` tests derivation and scoped ephemeral briefs; component/E2E tests exercise API parsing, interactions, permission responses, cancellation, unavailable recovery and accessibility.

### Contract audit and practical limits

All Home requests use existing project summary, generic blueprint/resource, workflow, Relay, review queue, workflow-run and lifecycle endpoints. Zod validates actual response fields, envelope/item scope, selected resource identity and Bench comparison identity. Existing same-origin session/CSRF handling is reused. The UI displays effective permissions; backend authority remains unchanged. No endpoint or response field was invented.

Workflow definitions expose name and revision, not creation timestamps/status. Bench evidence is derived from actual lifecycle comparisons and labels non-regression gate failures as gate review. Attention lists are bounded to recent evidence and provide inspection rather than approval or execution controls. Relay's existing contract explicitly represents disposable test incidents, which are labeled accordingly.

Guided Creation does not implement a builder. It hands the review brief to the existing `/agents` or `/workflows` route, where the unavailable builder and unsaved brief are clearly displayed. The brief lives in module memory, scoped to organization/project/user with a 30-minute expiry. Only an opaque ID enters history; refresh discards the input. No unsupported draft persistence is claimed.

The running Local API currently returns **404 for workflow definitions, Relay and workflow output reviews**, although these contracts exist in the checked-out backend source. Actual Home keeps available agents, activity and Bench evidence visible and identifies those three services as unavailable. Full real-server integration for those services is therefore not certified; their positive/negative contracts are covered by test-only fixtures. The live project exercised the Important Issues condition. New and Active conditions were verified with isolated fixtures, not fabricated runtime workspace data.

Initial headless capture attempts encountered the server's session limit (429). The final live screenshots and DOM measurements were taken through an existing authorized browser session without restarting the backend, extracting credentials or bypassing limits. The capture helper now reuses one session across viewport captures.

### Current Home evidence

Evidence directory: `D:/ARYN/aryn-labs/aryn/.local/home-v1/` (ignored).

- `home-{new,active,issues}-{1440,768,390}-{dark,light}.png` and `-lower.png`: current test-only contract captures for all three conditions.
- `guided-review-{1440,768,390}-{dark,light}.png`: review, permissions and focus validation using test-only contracts.
- `home-details-{1440,768,390}-{dark,light}.png`: accessible details drawer using test-only contracts.
- `reference-{new,active,attention}-{1440,768,390}-dark.png`: HTML prototype comparison captures, not product runtime.
- **`production-home-{1440,768,390}-{dark,light}.jpg`**: final production bundle, real Local API, existing authenticated browser session.
- `production-bench-drawer-{1440,390}-dark.jpg`: actual Bench evidence detail, closed again with Escape and focus return verified.
- `production-home-existing-session.json`: final CSS viewport, workspace state, available rows/services and overflow measurements.
- `shell-before.json`: pre-implementation hashes for preservation checks.
- `apps/web/playwright-report/index.html`: latest 60-test report.

The similarly named production **PNG** files and `production-home-browser.json` are historical failed headless attempts, not the final live evidence. Use the JPG files and existing-session report above.

## Earlier App Shell evidence — historical

Validated on 10 October 2026, branch `development`, Windows, Node 22.14.0. Work is uncommitted. New source is confined to `apps/web`; browser evidence is in ignored `.local/studio-shell-v1`. Pre-existing deletions and edits outside the frontend were preserved.

## Completed checks

| Check                                                  | Actual result                                                                                           |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `npm run typecheck`                                    | Passed, TypeScript strict and no unchecked indexed access                                               |
| `npm run lint`                                         | Passed, zero lint warnings                                                                              |
| `npm run build`                                        | Passed, production assets generated                                                                     |
| `npm test`                                             | 20 component/API tests passed                                                                           |
| `npm run test:e2e`                                     | 26 Chromium interaction/visual/accessibility tests passed                                               |
| `npm audit`                                            | Initial shell dependency audit found zero vulnerabilities; dependencies unchanged by the UI refinements |
| `git diff --check` for frontend                        | Passed                                                                                                  |
| Production build through existing Local API, port 8710 | Loaded at 1440, 768 and 390px; zero page errors and zero horizontal overflow                            |

## Acceptance evidence

| Requirement                               | Verification                                                                                                                                                                                                                          |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reference layout and proportional spacing | Screenshot review: navy surfaces, restrained cyan, grouped sidebar, hero, banner, 3 quick actions and activity table; annotation frames omitted. Context removed at the owner's request                                               |
| Exact desktop panel dimensions            | Browser asserts 60px topbar, 240px sidebar and 64px collapsed sidebar; logo divider shares the sidebar boundary                                                                                                                       |
| Responsive Home                           | Dark/light screenshots at 1440×900, 768×900 and 390×900, plus scrolled activity captures; no page, workspace or topbar horizontal overflow                                                                                            |
| Sidebar and routing                       | All 13 secondary routes visited, deep-link reload, browser back, active links, collapse and route focus                                                                                                                               |
| Combined workspace selector               | One organization/project dropdown using the real context endpoint; checked radio items, keyboard project switching, persisted selection, inaccessible saved ID rejection and resource selection reset                                 |
| Organization scope                        | Shows the API's single current organization; explains why additional organizations cannot be selected. Empty authorized lists expose no project choices or scoped requests                                                            |
| Global search                             | Ctrl+K/Cmd+K handler, keyboard route selection, API resource search, selected resource inspection, Escape focus return and partial API-failure recovery                                                                               |
| Context removal and resource details      | No right panel, breadcrumb toggle, account-menu entry or View context button, including with a saved legacy preference. Activity/search details use an accessible modal and the same actual detail endpoint                           |
| Account/environment/model/notifications   | Backend identity/mode, explicit unknown states, read-only Environment/Models in Settings, no catalog-to-active-model inference, hosted CSRF logout and sign-in recovery                                                               |
| Failure/empty/loading states              | 401, 403, 503, malformed contract, network failure, empty projects, no activity, slow response and session recovery                                                                                                                   |
| Cache after access revocation             | Component test first renders a real test response, then refetches a denial; private identity/activity disappear                                                                                                                       |
| Accessibility                             | Axe WCAG 2 A/AA and 2.1 AA: zero violations on six viewport/theme combinations, workspace menus on desktop/mobile, Settings, resource detail dialogs at all three widths and search error state; keyboard/focus interactions verified |
| Reusable foundation                       | Standard, Explorer and Canvas layout exports; providers, typed API schemas, scoped query hooks, reusable feedback and Radix UI primitives                                                                                             |

Corrections made during the audit: improved light-theme secondary text contrast, deferred route focus until the new DOM is mounted, added dialog focus restoration, moved search alerts/retry controls outside the ARIA listbox, and limited the search dialog height to the available viewport.

## Brand and layout refinement

The supplied `D:/ARYN/Logo Aryn Transparan.png` is copied unchanged to `src/assets/aryn-logo.png` (matching SHA-256: `00FD7B4A6C591FBE36DB618755080FB3B255E23F76B69645A0DA789D3E28759C`). CSS frames the original symbol and wordmark in a horizontal topbar lockup, with dark-theme contrast treatment; the source artwork remains intact.

The right Context panel and all its entry points are removed. Its presentation state is removed from the shell provider, so a legacy preference cannot restore it. Existing resource detail behavior remains available through a Radix modal with loading/error handling, focus trapping and Escape focus restoration. Component checks include a failed detail request and absence of stale verified data.

The topbar logo region and sidebar share `--sidebar-width`: 240px expanded and 64px collapsed/tablet. The divider runs the full topbar height at the same horizontal position as the sidebar border. The original symbol identifies the compact rail and mobile header; the wordmark remains visible on expanded desktop. Browser checks verify matching boundaries, persisted collapse and keyboard expansion. Actual Local API production captures report both boundaries at x=240 for desktop and x=64 for tablet, no Context panel, no page errors and no page/workspace/topbar overflow. Updated dark/light screenshots at all three widths and both collapsed desktop states were visually reviewed.

The topbar now has only the combined workspace selector, Search, Notifications and Avatar Profile (plus mobile navigation on narrow screens). Environment and Model indicators, account-name text and redundant breadcrumbs are removed. Existing runtime/model information is relocated into Settings, with deferred status requests and explicit unavailable states. No query scope, session, permission enforcement or API contracts changed. Changes reuse existing files and components; no new source files were needed for this refinement. Tests also cover 320px with long organization/project names and rejection of status data belonging to another organization.

Audit corrections: avatar initials now use the foreground token for sufficient light-theme contrast; workspace/profile menus use nonmodal Radix behavior, keeping background controls accessible and avoiding hidden focus targets. All 26 browser tests pass after those corrections.

## Evidence locations

Screenshots and `production-browser.json`: `D:/ARYN/aryn-labs/aryn/.local/studio-shell-v1/`.

- `home-{1440,768,390}-{dark,light}.png`: isolated API contract snapshots, explicitly test data.
- `home-{768,390}-{dark,light}-activity.png`: scrolled activity and footer.
- `home-1440-{dark,light}-collapsed.png`: compact sidebar and aligned logo divider.
- `resource-details-{1440,768,390}-dark.png`: resource details modal.
- `workspace-menu-{1440,390}-dark.png`: keyboard-opened combined selector, isolated contract data.
- `settings-390-dark.png`: contextual runtime/model sections, isolated contract data.
- `production-{1440,768,390}-dark.png`: actual existing Local API and generated production bundle, without fixture interception.
- `production-workspace-{1440,390}-dark.png`: actual organization/project dropdown.
- `production-settings-{1440,390}-dark.png`: actual Settings runtime/model sections.
- `production-browser.json`: actual browser page errors, overflow results, Context/breadcrumb removal, single workspace selector and divider alignment.
- Playwright report: `apps/web/playwright-report/index.html`, generated locally.

At the initial shell release, Home had example feature content; the current adaptive Home implementation and its evidence are documented above. Settings retains read-only shell runtime information. Other routes remain unavailable scaffolds. Notifications and active/default model data remain unavailable because the existing API does not provide those fields. Subscription UI was removed with Context. Hosted login/logout behavior was tested against isolated contract responses, not a real production IdP. Earlier Context/hero screenshots remaining in the ignored shell evidence directory are historical captures, not the current Home implementation.

The private PRD/architecture/security documents are not present in the documentation checkout; its index explicitly marks them absent. No private P0 identifiers or production deployment certification are invented. Implementation follows the user request, repository instructions and inspected existing contracts.
