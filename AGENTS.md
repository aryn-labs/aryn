# Instructions for coding agents — ARYN

1. Read this README and relevant PRD/architecture/security docs before proposing code.
2. Do not replace the agreed four domains (Factory, Relay, Brief, Bench) with unrelated products; Core is internal authority.
3. Honor ownership: organization -> project -> division -> assignment -> workflow/task/run. Blueprint, version, deployment, assignment, run are distinct.
4. Enforce permissions, budgets, tool grants, approval hashes, and scoped data **on the backend**, not solely via UI or prompts.
5. Never grant unrestricted host access or secret access to model/runtime. Sandbox generated websites and Relay remediation.
6. Any replay/evaluation must use isolated/mocked write adapters. Record actual model/provider and evaluation version.
7. Do not add paid vendors, outbound uploads, silent model fallback, auto-publishing, or Local/Cloud sync without explicit approval.
8. Keep PRD P0 IDs and tests traceable. For every implemented behavior include positive AND relevant negative tests. Do not fabricate PASS evidence.
9. Work on `development` or feature branches; no push/merge into `main` unless the owner requests it.
10. Inspect existing code before editing. Report modifications, tests actually run, outstanding risks and API/contract changes.
