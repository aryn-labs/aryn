# ARYN — Autonomous Agent Infrastructure

**Define. Run. Govern. Evaluate. Evolve.**

This is the private primary monorepo for ARYN Cloud and ARYN Local.

## Bounded domains
- `modules/core/`: identity, organization/project scoping, divisions, workflows, permissions, approvals, audit, and usage authority.
- `modules/agent-factory/`: agent blueprints, immutable versions, promotion and assignments.
- `modules/brief/`: evidence bundles, provenance, contradiction, and abstention.
- `modules/bench/`: safety evaluation, replay, regression gates.
- `modules/relay/`: incident investigation, approved remediation, recovery proof.
- `modules/commercial/`: plans, subscriptions, entitlements and billing usage policy.

## Applications and adapters
- `apps/web/`: Cloud web interface.
- `apps/desktop/`: Windows Local candidate (Tauri evaluation pending).
- `services/api/`: authoritative application API.
- `services/worker/`: background execution; never a second policy authority.
- `packages/contracts/`: versioned data contracts.
- `packages/runtime-adapters/`: replaceable runtime adapters (Hermes candidate).
- `packages/model-adapters/`: explicit BYOK/local/managed model routing.
- `packages/tool-adapters/`: allowlisted tool boundaries.
- `packages/ui/`: reusable user interface components.

## Security invariants
All private resources are organization-scoped and project-scoped where applicable. Sensitive writes require service-side policy enforcement. Agent output is untrusted. Approval binds to exact action payload. Replays never invoke live write tools. Local has no silent cloud sync/fallback. Never commit secrets.

## Current status
**Initial repository scaffold only.** No implementation, runtime integration, API, tests, security guarantee, or deployment is implied by the existence of directories.

References: ARYN-PRD-001, ARYN-ARCH-001, ARYN-TECH-001, ARYN-SEC-001 and ARYN-PLAN-001 in private `aryn-docs`.
