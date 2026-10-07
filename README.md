# ARYN — Autonomous Agent Infrastructure

**Define. Run. Govern. Evaluate. Evolve.**

This is the private primary monorepo for ARYN Cloud and ARYN Local.

## Bounded domains
- `modules/core/`: identity, organization/project scoping, divisions, workflows, permissions, approvals, audit, and usage authority.
- `modules/agent_factory/`: agent blueprints, immutable versions, promotion and assignments.
- `modules/brief/`: evidence bundles, provenance, contradiction, and abstention.
- `modules/bench/`: generic scenario execution, deterministic graders, evidence validation, accepted baseline comparisons and regression promotion gates. Research Safety is the first suite.
- `modules/relay/`: incident investigation, approved remediation, recovery proof.
- `modules/commercial/`: plans, subscriptions, entitlements and billing usage policy.

## Applications and adapters
- `apps/web/`: Cloud web interface.
- `apps/desktop/`: Windows Local candidate (Tauri evaluation pending).
- services/api/: authoritative application API.
- services/worker/: background execution; never a second policy authority.
- `packages/contracts/`: versioned data contracts.
- `packages/runtime_adapters/`: Hermes runtime boundary (execution engine).
- `packages/model_adapters/`: 9Router model discovery and exact-model policy; no provider credentials.
- `packages/tool_adapters/`: allowlisted tool boundaries.
- `packages/ui/`: reusable user interface components.

## Security invariants
All private resources are organization-scoped and project-scoped where applicable. Sensitive writes require service-side policy enforcement. Agent output is untrusted. Approval binds to exact action payload. Replays never invoke live write tools. Local has no silent cloud sync/fallback. Never commit secrets.

## Current status
Core governance/persistence, Agent Factory, Bench, and the Hermes adapter are implemented. **ARYN Studio** provides a loopback-only development web application for blueprint → version → Bench → approval → publish → assignment → Research Agent execution → result/audit. This is not a production authentication or public deployment claim.

```powershell
Set-Location D:\ARYN\aryn-labs\aryn
.\scripts\start-aryn.ps1
```

9Router must already listen at `http://127.0.0.1:20128/v1`; the combined launcher starts runtime and Studio with matching ephemeral authentication. See [9Router routing, readiness limitations and validation](docs/9router-gateway.md). Open `http://127.0.0.1:8710`. See [Studio setup, security, and capabilities](docs/studio.md) and [validation evidence](docs/studio-validation.md). Brief and Relay are not implemented in Studio.

See [Bench engine contracts and validation](docs/bench-engine.md).

References: ARYN-PRD-001, ARYN-ARCH-001, ARYN-TECH-001, ARYN-SEC-001 and ARYN-PLAN-001 in private `aryn-docs`.
