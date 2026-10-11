# Projects audit — development

Audit baseline: `e00056e59df05fb86fd780f21aac09ef34ca9e81`. Implementation and validation were completed locally before the owner subsequently authorized committing and pushing to `development`.

The requested reference directory was missing. The eight user attachments were inspected for the audit; the reference copies now remain in ignored local storage at `.local/projects-validation/design-references`, outside product source documentation. All six screenshots were inspected; the HTML was opened in a loopback browser and its empty/list/detail states, five tabs, creation dialog, result drawer and light theme were inspected. Its demonstration toolbar, shell and illustrative data are not product requirements or authorization.

## Existing foundations

- App Shell, workspace selector, authenticated context, semantic dark/light tokens, bilingual preferences and TanStack routing/query are retained. `/projects` currently renders a feature scaffold.
- Studio authenticates sessions, validates CSRF and Origin, binds trusted Core identity, sanitizes errors and revalidates effective organization/project membership.
- `WorkspaceReads` provides bounded signed cursors and scoped project, division, assignment, run, version, evaluation and audit projections. Run claims, publication/assignment provenance, Bench evidence and audit signatures already have verification paths.
- Core WorkflowExecutor persists authenticated definitions, versions, workflow runs, artifacts and reviewed deliverables, including independent history commitments and safe download/preview routes. These are actual governed outputs, not a universal artifact registry.
- ProjectModel stores name/slug/organization/timestamps. OrganizationRepository creates projects internally. There is no Studio project creation/edit contract, objective, optimistic generation or mutation receipt.
- Divisions and explicit project memberships exist. Human display names and human division membership do not have a contract. Organization admin oversight is distinct from project membership. Assignment is distinct from blueprint creation.

## Implementation gaps and decisions

1. Add minimal organization-scoped Core project create and project-scoped edit. Both are human organization-admin operations; zero-project creation does not require a project ID. Validate name/objective, derive slug server-side, reject conflicts, require an expected generation for edit, and persist signed idempotency receipts plus authenticated audit in the same transaction.
2. Add an additive migration for objective/generation and mutation receipts. Do not expose delete or archive: existing project cascades can remove governance records, and archive admission/retention semantics have not been defined.
3. Implement compact list and five detail routes inside the existing shell. Synchronize selected project and cancel stale private queries without changing shell appearance.
4. Build read-only work/team/results/activity projections from existing authority. Results comprise verified non-chat/non-Bench execution outputs, verified workflow artifacts and verified Bench evaluations. Formats come from actual contracts; unsupported formats expose metadata/provenance rather than invented previews. No new artifact store, task domain or builder is introduced.
5. Preserve unknown outcomes. Only permitted, verified pending review/regression/incident items are actionable. Existing Home read/attention logic can be reused without changing Home UI.
6. Human names, project lifecycle status/environment and arbitrary media/dataset/external-record viewers remain unavailable unless an existing record supplies them. Never substitute example data or label an inventory row active by assumption.

## Validation plan

Exercise actual API/Core transactions and persistence, positive/negative RBAC, CSRF, tenant/project isolation, idempotency, concurrent edits and immutable receipts; run migration/security regressions. Frontend component and browser tests cover list/empty/create/edit/deep-link/switching/detail states, supported/unsupported previews, both locales, keyboard and dark/light layouts at 1920/1440/1024/768/390px. Test-only fixtures are identified separately from live product validation. Screenshot evidence and exact executed gate results will be recorded after implementation.
