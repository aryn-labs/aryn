# ARYN Web

ARYN Web is the control plane for Agent Factory, Relay, Brief and Bench,
with scoped Projects, Workflows, Runs, Automations, Chat and Settings. Core owns
authorization, approval, budgets and evidence; browser state never grants authority.
React/Vite, strict TypeScript, TanStack Router/Query, Radix and existing design
tokens provide the interface. Credentials never belong in Vite variables.

## Development

Use Node from the repository `.node-version` and `npm ci --ignore-scripts`.
`npm run dev` serves loopback port 5173 and proxies `/api` and `/auth` to ARYN API
port 8710. `npm run build` produces `dist`, served by the application API at its
own origin. The repository's `scripts/start-aryn.ps1` starts the product services;
hosted authentication remains server-managed OIDC.

## Verification

Run `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
`npm run build` and `npm audit`. Install Chromium with
`npx --no-install playwright install chromium` before browser checks.

The supported browser suites are `npm run test:e2e`, `test:chat:e2e`,
`test:projects:e2e`, `test:agents:e2e`, `test:workflows:e2e`,
`test:operations:e2e` and `test:intelligence:e2e`. They own their disposable API,
Core/database fixtures or scoped HTTP doubles. Set `ARYN_TEST_PYTHON` to the
locked repository interpreter when needed. They never invoke a live model.

Browser suites cover responsive themes, keyboard/focus, Axe, persistence,
cross-user/project denial, consent, exact retry, deletion and recovery. Screenshots,
traces and reports are ignored test artifacts. Manual capture scripts and the
preconfigured live Projects harness have been superseded by these suites.

## Contracts

Home and Chat share the existing composer and exact model selection. Sending
requires current Core permission, gateway verification and signed provider consent.
Model listing and offline fixtures do not establish live provider availability.
Ambiguous retries retain their original request; unsupported streaming or Stop
controls are not simulated. Settings exposes the Core-controlled runtime inventory
and write-only gateway credential lifecycle; native administration is never called
directly from the browser.

Engineering references are maintained in sibling `aryn-docs/engineering/aryn`.
Approved normative documents remain separately controlled by that repository's
document index. See [maintenance evidence](../../docs/repository-maintenance.md)
and [CI contracts](../../docs/ci-delivery.md) for actual verification and limitations.
