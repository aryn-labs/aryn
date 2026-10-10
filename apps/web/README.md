# ARYN Studio — App Shell and Home

React + Vite, TypeScript strict, Tailwind CSS v4, source-owned shadcn-style Radix primitives, Lucide, TanStack Router and Query. Home is implemented within the existing App Shell; Settings displays existing runtime/model information. Other feature routes render unavailable scaffolds. The intentionally deleted frontend has not been restored.

## Development

Node 22.12+ (tested with 22.14). Install with `npm ci`, then `npm run dev` from `apps/web`. Open http://127.0.0.1:5173. The existing ARYN API must already be running at http://127.0.0.1:8710. Vite proxies `/api` and `/auth` to that loopback endpoint and matches its Host/Origin boundary. No credentials belong in Vite environment variables.

`npm run build` writes `dist`, which the existing API serves at its own origin. Start the backend through the existing launcher; this implementation does not change launchers or backend configuration. Hosted authentication remains server-managed OIDC.

## Validation

- `npm run typecheck`
- `npm run lint`
- `npm test`
- `npm run build`
- `npx playwright install chromium` once, then `npm run test:e2e`
- `npm audit`

Fixtures live only in `src/test` and `src/features/home/tests`; they are never imported by the application. Browser tests intercept same-origin API contracts and cover New, Active and Important Issues in both themes at 1440, 768 and 390px. Checks include keyboard/focus behavior, bounded textarea growth, single-border focus, honest unavailable conversation, explicit draft selection, Axe, project isolation, cancelled requests, denied/revoked access, unavailable services, recovery and navigation without business mutations. Existing shell tests also cover 320px with long names. See `VALIDATION.md` for current test counts, actual results and limitations.

Current Home audit screenshots are written to ignored `.local/home-audit-v2`; earlier Home/shell evidence remains in `.local/home-v1` and `.local/studio-shell-v1`. `node scripts/capture-home.mjs [baseUrl] [referenceHtmlPath]` captures the local reference and existing production API without fixtures, reusing one browser session across viewports. The default reference is `C:/Users/User/Downloads/ARYN_Home_Interactive_Concept.html`. A backend denying new sessions must be inspected through an already authorized session; the helper does not bypass session limits.

## Home behavior

`src/features/home` owns the page, components, scoped queries, validated contracts, pure workspace/attention derivation and tests. Home uses the existing Standard layout, providers, theme tokens and routing; sidebar, topbar, global navigation and selectors are unchanged by the Home implementation.

Home content follows `ARYN_Home_Interactive_Concept.html`: project header, assistant composer, three quick actions, compact agent/workflow lists, actionable attention and recent recorded activity. A confirmed new project shows Getting Started and hides empty work/activity sections. Active projects retain a compact composer. Important issues appear before Continue Working, prioritized from actual server evidence and effective permissions. Missing, failed or unknown inventories never imply a new workspace. Partial service failures preserve known work and offer scoped retry controls.

The composer has one border and focus cue, an automatically sized textarea with a height cap, and a separate button row. Continue opens a conversation surface in the main Home workspace, not a drawer. **No safe Home conversation endpoint exists in the audited API.** The user's input is marked **Not sent**, the absence of an AI response is explicit, and follow-up Send is disabled. No artificial loading, streaming or assistant reply is shown; no prompt is sent to Core runs, Hermes, 9Router or another service. Input exists only in this page's memory and is cleared on scope/access change. Draft creation permissions are not treated as chat authorization.

Only explicit Agent/Workflow draft choices or quick actions open the existing keyboard-accessible Guided Creation drawer. Review passes an ephemeral, organization/project/user-scoped brief to the corresponding existing route. Only an opaque ID enters router history; private input is not put in URLs or browser storage. Reload discards the brief. The destination explicitly identifies the builder as unavailable and shows the unsaved brief for review. No draft persistence contract is assumed; there are no publish, approval, grant, retry-run or execution mutations.

Unavailable workspace services are summarized in one collapsed, keyboard-accessible disclosure with per-service retry controls inside. Agent rows show actual descriptions and creation dates. Recorded internal event codes use customer-facing labels while IDs, status, scope and detail requests remain unchanged; unknown events never infer success.

Resource rows open a closable detail drawer using existing endpoints. Attention is bounded to recent verified evidence; it is not a complete incident/approval inbox. Rows offer inspection only. Low/informational/closed incidents and unverified approvals are excluded. Relay's current contract represents disposable test incidents; those are clearly labeled and never presented as production infrastructure health.

## API contract and honest states

| Behavior                                              | Existing endpoint / source                                                |
| ----------------------------------------------------- | ------------------------------------------------------------------------- |
| Session bootstrap                                     | `POST /api/session`, empty body, same-origin cookies                      |
| Current organization, accessible projects, user, mode | `GET /api/workspace/context`                                              |
| Project inventory and recent activity                 | `GET /api/projects/{id}/summary`                                          |
| Home agent definitions                                | `GET /api/projects/{id}/resources/blueprints?limit=4&sort=newest`         |
| Home workflow definitions and details                 | `GET /api/projects/{id}/workflows?limit=4`, `/workflows/{id}`             |
| Home Relay records and details                        | `GET /api/projects/{id}/relay?limit=8`, `/relay/{id}`                     |
| Home workflow output reviews and details              | `GET /api/projects/{id}/review-queue?limit=6`, `/workflow-runs/{id}`      |
| Home Bench comparison evidence                        | `GET /api/projects/{id}/lifecycle?limit=8[&version_id={id}]`              |
| Global resource search                                | `GET /api/projects/{id}/resources/{blueprints,runs,projects}?q=…&limit=8` |
| Selected resource details                             | `GET /api/projects/{id}/resources/{resource}/{id}`                        |
| Runtime readiness and discovered model catalog        | `GET /api/workspace/status`, in Settings                                  |
| Hosted login/logout                                   | Server `/auth/login`; `POST /api/logout` with session CSRF                |

Runtime response schemas reject malformed data, mismatched envelope/item scope and inconsistent resource/comparison identity. Server 401/403 hides cached private identity/data until a fresh session succeeds. This is display hygiene; ARYN Core remains the permission authority. Organization switching beyond the single current organization is unavailable in the existing contract. Project preferences are validated against the server-returned list. Query keys include organization and project; requests consume AbortSignal. Scope/access changes clear Home input, dialogs and foreign-scope handoffs.

There is no notifications feed, subscription entitlement or project active/default model in the consumed contract. These explicitly show unavailable. A discovered model is never displayed as active. Home has no statistic cards or invented timestamps/statuses. The footer reports workspace loading state, not runtime connectivity. The local server inspected on 10 October 2026 returns 404 for workflows, Relay and workflow output reviews; Home explicitly shows those services as unavailable while retaining available agents, activity and Bench evidence. Source contracts were audited; no backend endpoint or response field was added.

## Reusable layouts and interaction

`StandardLayout`, `ExplorerLayout` and `CanvasLayout` in `src/app/shell/MainWorkspace.tsx` share a named workspace landmark. Redundant breadcrumbs are removed; the page heading, route announcement and sidebar active state identify the current location. Explorer accepts an `explorer` React node; Canvas provides a full workspace surface for future tools. Full builders and other feature pages are outside this release.

The topbar contains one combined organization/project workspace dropdown, Search, Notifications and Avatar Profile. The switcher labels the current scope, offers only server-returned projects as checked radio menu items, and explains that additional organizations are unavailable in the current contract. Its trigger remains useful on mobile and truncates long names without hiding the selected project. Search retains Ctrl+K/Cmd+K. Theme, account details and hosted sign-out remain in the avatar menu. Environment/runtime readiness and the model catalog are contextual, read-only sections in the existing Settings route; their API request is deferred until that route is opened. Dropdown menus use nonmodal Radix behavior with arrow-key navigation and Escape focus restoration.

Desktop: 60px topbar, 240px sidebar (64px collapsed), flexible workspace. The logo area and sidebar share one width token, keeping their dividing borders aligned in expanded, collapsed and tablet layouts. Tablet uses a 64px rail; mobile uses a navigation dialog. The right Context panel and its entry points remain removed. Home details use a drawer; global search retains its existing details modal. Both provide loading/error states and focus restoration. Preferences store only theme, project ID and sidebar presentation, never tokens or roles. Radix manages menu/dialog keyboard behavior and modal focus traps. Global search supports Ctrl+K and Cmd+K, arrow keys, Enter and Escape. A skip link and route announcements support keyboard and screen-reader navigation. Fonts are self-hosted for the backend CSP; dark and light colors share semantic tokens.

Design sources: the supplied screenshot for the existing shell and `ARYN_Home_Interactive_Concept.html` for Home content. The prototype's shell and scenario selector are not copied. Home removes the previous hero illustration and activity table, using neutral surfaces, thin separators and restrained turquoise accents.

Library reference: [TanStack code-based routing](https://tanstack.com/router/latest/docs/routing/code-based-routing), [Tailwind Vite installation](https://tailwindcss.com/docs/installation/using-vite), [shadcn Radix dropdown](https://ui.shadcn.com/docs/components/radix/dropdown-menu).
