# Studio workspace interaction contract

## Agent lifecycle interaction specification

Current audit source: `40df9d1f894b257df3a277c4623466d6d03541dc`. At 1440 px the Agent Builder uses semantic React Flow sections and an adjacent typed inspector. At 768/390 px the inspector stacks or closes; a complete structured form alternative remains available. Identity/Objective, Instructions, Model Policy, Output Contract, Constraints, Tool Policy, Budget Policy and Evaluation Reference are definition sections, not executable tasks. Connections are fixed explanatory relationships with no execution gesture.

Explicit save shows dirty/saved/conflict state; undo/discard/reload are deliberate and preserve unsaved input on conflict. Candidate creation is separate from save/drag. Model options come from server discovery; unavailable saved models are labeled accurately. Tools are read-only denied. Version detail exposes canonical hash, actual verified receipts, comparisons and immutable status. Registry/diffs, Bench, exact-hash approval, manual Operations and captured Execution Console reuse Core evidence with read-only viewer states. Filtered history/audits page at the server and request details lazily. Existing lifecycle links remain compatible. No direct-turn node trace or usage/cost is invented.

R02 uses semantic filtered/paged tables; R03 [React Flow custom nodes](https://reactflow.dev/learn/customization/custom-nodes) informs typed semantic sections and keyboard alternatives; R05 [Langfuse observability](https://langfuse.com/docs/observability/best-practices) informs actual captured provenance/evidence without adopting its service or inventing traces; R06/R09 retain attention, definitions, focus, reflow and contrast. Browser evidence covers both themes at 390/768/1440 plus keyboard/axe. React Flow controls follow the active theme; semantic section buttons provide selection without relying on canvas gestures.

Captured Console uses the run's exact claim/assignment/version, with reservation, actual effective limits, settlement and unavailable usage shown separately. Stop requests report Core acknowledgement and only actual terminal cancellation confirms cancelled. A missing or unauthorized run shows a resource error and no substitute agent configuration. Operations remains manual; runtime readiness/evidence/permission guard the action. Approval/audit inventory displays authenticated receipts without inferring new authority. Field-path validation is sanitized, draft generation conflicts retain local input, and explicit reload offers restoration before saving again. No prompt or credential is kept in browser storage.

The implementation source, synthetic screenshots, observed checks and exact-SHA CI are recorded in [delivery evidence](studio-redesign-progress.md). The following workspace source/CI record is historical.

Implementation source: `80bac7dfa59bd27a6ac1e7e5493f11285b625b2d`. Current source workflow: [ARYN Quality 37835952417](https://github.com/aryn-labs/aryn/actions/runs/37835952417); terminal completed/success, 14/14 jobs; evidence-only closure is verified separately before the final report. Subsequent evidence-only commits do not change this source.
Source baseline: `3a8ddb69b855ea37d1a33721c6c57a02f14ad881`. Reviewed 9 October 2026 (Asia/Bangkok).

The workspace delivery implements PRD sections 5–7 and workspace acceptance in package 01. This specification precedes implementation; validation evidence is recorded in studio-redesign-progress.md.

## Composition and interactions

At 1440 px: fixed 248 px sidebar, grouped navigation, active project selector, breadcrumb/header and a two-column Overview. Attention comes first, then defined inventory metrics, recent runs and authenticated audit references. Projects uses a filter toolbar, semantic table, bounded pages and a detail view with real divisions. At 768 px: compact sidebar and single-column content where needed. At 390 px: dismissible navigation dialog with keyboard focus containment/return, stacked cards, scrollable table inside its own container and full-width forms. No page-level horizontal overflow.

Groups are WORKSPACE, BUILD, OPERATE, INTELLIGENCE & RELIABILITY and CONTROL. Existing root/factory/bench/runs/approvals/governance/settings links remain. Future routes resolve to a truthful unavailable explanation without enabled feature actions. Existing run query links remain supported. Agent Builder and Workflow Builder remain distinct concepts.

Reuse licensed packaged Geist/Geist Mono, existing Radix dialog/Button, React Router, React Query and dark/light tokens in styles.css. Workspace-specific styles belong in workspace.css. Dark tokens: background #070a13, solid surface #0d1527, elevated #152037, primary #8b7cf6, cyan #38bdf8, success #10b981, warning #f59e0b, error #f43f5e. Text and focus contrast are checked in both themes. Avoid inferred uptime, billing, traces or tool readiness.

Project selection immediately hides the previous scope, cancels reads, removes scoped cache/selection, closes forms and navigates to Overview. Keys include organization/project/resource/filters/cursor. Reads receive AbortSignal. Permissions are supplied by Core; mutations invalidate summary, scoped lists and legacy snapshot. Pending lifecycle mutations block user switching; division mutation callbacks retain the captured organization/project scope. Revoked membership and session expiry hide cached resource data.

Each page represents loading, empty and filtered-empty, fresh data, stale/revalidation failure, API/offline errors, 401, 403 and not-found. A retry control revalidates. Division create/edit has field errors, explicit save, generation conflict and preserved user input. No division membership or permissions are inferred. Metrics show source, scope, definition and refreshed_at; unknown values read Tidak tersedia.

Keyboard: skip link, semantic links/buttons/tables, visible focus, navigation Escape/Tab handling, Radix modal focus return, labeled filter inputs/selects, live loading/error/status announcements. Respect prefers-reduced-motion. Selection never depends solely on color. Datetimes display the browser timezone explicitly.

## Reference adoption

- R01 [shadcn dashboard/sidebar](https://ui.shadcn.com/blocks?category=dashboard): grouped sidebar, breadcrumbs and metric cards; ARYN uses real Core data instead of sample charts.
- R02 [Carbon data table](https://carbondesignsystem.com/components/data-table/usage/): toolbar, named columns, scoped filtering and pagination; no unsupported batch mutation.
- R06 [Grafana dashboard guidance](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/): actionable attention, defined measurements and drilldown; no availability/SLA inference.
- R09 [WCAG 2.2](https://www.w3.org/TR/WCAG22/): keyboard/focus, labels, reflow and contrast; automated axe complements explicit keyboard and responsive browser checks, not a claim of complete conformance.
