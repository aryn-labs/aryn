# ARYN Studio — App Shell, Home and Chat

React + Vite, TypeScript strict, Tailwind CSS v4, source-owned shadcn-style Radix primitives, Lucide, TanStack Router and Query. Home is implemented within the existing App Shell; Settings displays existing runtime/model information. Other feature routes render unavailable scaffolds. The intentionally deleted frontend has not been restored.

## Development

Use the repository `.node-version` (22.23.3). Install with `npm ci`, then `npm run dev` from `apps/web`. Open http://127.0.0.1:5173. The ARYN API must already be running at http://127.0.0.1:8710. Vite proxies `/api` and `/auth` to that loopback endpoint and matches its Host/Origin boundary. No credentials belong in Vite environment variables.

`npm run build` writes `dist`, which the existing API serves at its own origin. Start the backend through the existing launcher; this implementation does not change launchers or backend configuration. Hosted authentication remains server-managed OIDC.

## Validation

- `npm run typecheck`
- `npm run lint`
- `npm test`
- `npm run build`
- `npx playwright install chromium` once, then `npm run build` before `npm run test:e2e` (production preview on 5175)
- `npm audit`
- `npm run format:check`
- `npm run test:chat:e2e` after building; real API/Core/temporary database with an explicitly isolated runtime, never live AI proof

Fixtures live only in test modules and are never imported by the application. Home browser tests intercept same-origin API contracts and cover New, Active and Important Issues in both themes at 1920, 1440, 1024, 768 and 390px. Chat browser tests use real API/Core with a disposable database and an explicitly isolated runtime. Checks cover keyboard/IME, bounded input, first-use consent, language persistence, scope isolation, denied/revoked access, recovery, scroll position, focus and Axe. Existing shell tests also cover 320px with long names. See `VALIDATION.md` for actual results and limitations.

Current evidence is written to ignored `.local/chat-finalization`; earlier Home/shell evidence remains in `.local/home-v1`, `.local/home-audit-v2` and `.local/studio-shell-v1`. `node scripts/capture-chat-readiness.mjs [baseUrl]` captures the actual Home API at 1920/1440/1024/768/390px in both themes. `node scripts/capture-home.mjs [baseUrl] [referenceHtmlPath]` captures the supplied concept and existing production API, reusing one browser session across viewports. The default reference is `C:/Users/User/Downloads/ARYN_Home_Interactive_Concept.html`. The helpers do not bypass session limits.

## Home behavior

`src/features/home` owns the page, components, scoped queries, validated contracts, pure workspace/attention derivation and tests. Home uses the existing Standard layout, providers, theme tokens and routing; sidebar, topbar, global navigation and selectors are unchanged by the Home implementation.

Home follows `ARYN_Home_Interactive_Concept.html` and the final V1.0 specification: local-time greeting, minimal composer, three quick actions, compact mixed agent/workflow/conversation list, up to three attention items and four actual activities. A confirmed new project shows short Getting Started guidance and hides empty sections. Important issues appear before Continue Working. Missing, failed or unknown inventories never imply a new workspace. Partial service failures preserve known work and offer scoped retry controls.

The reusable composer has one focus cue, a six-line height cap, real model picker and horizontal Send arrow. Enter sends; Shift+Enter inserts a line; IME is respected. Session/CSRF-protected sending requires Core permission, exact model validation and signed provider consent. A valid acknowledgement opens `/chat/{conversationId}`; it never opens Guided Creation automatically. Server history supports follow-ups, refresh/resume, Copy and optional scoped history. First-use consent is stored and can be revoked in Settings. Chat polls actual processing; streaming/Stop are unavailable. Ambiguous retries retain the original input/key. See [conversation contract and safeguards](../../docs/chat-workspace.md).

**Real multi-turn AI is verified with ds/deepseek-flash** through ARYN API/Core/Hermes/9Router, including a third response after refresh. Listed candidates are verified by a bounded metered Core probe on explicit send after consent; viewing Home does not invoke inference. Other model routes are not certified. Full acceptance still requires PostgreSQL execution and trusted downstream provider/local-only routing evidence; see `VALIDATION.md`.

Only explicit Agent/Workflow draft choices or quick actions open the existing keyboard-accessible Guided Creation drawer. Review passes an ephemeral, organization/project/user-scoped brief to the corresponding existing route. Only an opaque ID enters router history; private input is not put in URLs or browser storage. Reload discards the brief. The destination explicitly identifies the builder as unavailable and shows the unsaved brief for review. No draft persistence contract is assumed; there are no publish, approval, grant, retry-run or execution mutations.

Unavailable services use one collapsed disclosure with scoped retry controls. Compact work rows show real names, types/statuses and available timestamps; longer details are on demand. Internal event codes use customer-facing labels; unknown events never imply success.

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

Runtime schemas reject malformed or mismatched scope/identity. Server 401/403 hides private cached data until a fresh session succeeds; Core remains authority. Organization switching beyond the current organization is unavailable. Project preferences are validated against server-returned access. Private query keys include person, organization and project; requests consume AbortSignal. Scope/access changes clear input, dialogs and foreign handoffs. UI language uses i18next, defaults to id-ID and is persisted per person/organization through Settings → Preferences → Language; en-US is supported. No Home/topbar language selector is added.

There is no notifications feed, subscription entitlement or project active/default model in the consumed contract. These explicitly show unavailable. A discovered model is never displayed as active. Home has no statistic cards or invented timestamps/statuses. The footer reports workspace loading state, not runtime connectivity. Home preserves actual agent/activity/Bench evidence and reports individual unavailable services compactly, rather than inferring an empty project. Existing domain contracts are preserved; the new conversation contracts are documented separately.

## Reusable layouts and interaction

`StandardLayout`, `ExplorerLayout` and `CanvasLayout` in `src/app/shell/MainWorkspace.tsx` share a named workspace landmark. Redundant breadcrumbs are removed; the page heading, route announcement and sidebar active state identify the current location. Explorer accepts an `explorer` React node; Canvas provides a full workspace surface for future tools. Full builders and other feature pages are outside this release.

The topbar contains one combined organization/project workspace dropdown, Search, Notifications and Avatar Profile. The switcher labels the current scope, offers only server-returned projects as checked radio menu items, and explains that additional organizations are unavailable in the current contract. Its trigger remains useful on mobile and truncates long names without hiding the selected project. Search retains Ctrl+K/Cmd+K. Theme, account details and hosted sign-out remain in the avatar menu. Environment/runtime readiness and the model catalog are contextual, read-only sections in the existing Settings route; their API request is deferred until that route is opened. Dropdown menus use nonmodal Radix behavior with arrow-key navigation and Escape focus restoration.

Desktop: 60px topbar, 240px sidebar (64px collapsed), flexible workspace. Logo/sidebar share one width token. Soft surface contrast replaces structural separators. Tablet uses a rail; mobile a navigation dialog. Context remains removed; Home details and chat history are optional drawers with loading/error/focus handling. Browser preferences contain theme, project ID and sidebar presentation, never credentials or roles. Language and signed consent persist server-side. Radix handles keyboard/focus traps; global Search supports Ctrl/Cmd+K. A skip link and route announcements remain. Fonts are self-hosted under backend CSP; dark/light share semantic tokens.

Design sources: supplied shell screenshot and `ARYN_Home_Interactive_Concept.html`, with the final V1.0 specification taking precedence. The prototype shell, scenario selector and sample data are not copied. Home has no hero illustration or statistic table; neutral surfaces and restrained turquoise retain ARYN identity.

Library reference: [TanStack code-based routing](https://tanstack.com/router/latest/docs/routing/code-based-routing), [Tailwind Vite installation](https://tailwindcss.com/docs/installation/using-vite), [shadcn Radix dropdown](https://ui.shadcn.com/docs/components/radix/dropdown-menu).
