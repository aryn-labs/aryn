# Security guidelines

- Do not commit API tokens, `.env`, credentials, signing keys, payment secrets, personal data, or private customer documents.
- Treat LLM outputs and third-party content as untrusted. Authorization belongs to ARYN Core.
- Use least-privileged runtime scopes and no unrestricted host tool execution.
- Keep local runtime API loopback-bound with session authentication and origin protection.
- Never upload Local project data to remote model/provider without user selection and disclosure.
- Report suspected vulnerabilities **privately to the repository owner**. Do not paste secrets into GitHub Issues or logs.
- A repository scaffold is not a security audit; release gates are defined by ARYN-SEC-001.

Local development identity requires explicit `ARYN_ENV=development` and `ARYN_AUTH_MODE=local-development`, direct loopback and exact Origin/Host. Forwarded traffic cannot bootstrap Local admin. Hosted requires configured HTTPS OIDC, server sessions/CSRF and database provisioned issuer/subject mapping; login never grants membership/admin. Identity headers are not authority. Core revalidates current session/mapping and membership at authorization/commit.

Run only the dedicated ARYN Hermes wrapper on private same-host loopback. Its explicit route application excludes native jobs/cron, session administration, profiles/plugins and browser-control transports even with a valid native API key. Do not separately expose native Hermes listeners or gateway/provider credentials. Existing signed claims, immutable governance receipts, independent history commitments and single execution authority remain required.

See [deployment security](docs/deployment-security.md) for exact proxy/cookie/session/runtime contract, migration 015 and trust limits. Real IdP/PostgreSQL/TLS/VPS/firewall/UAT are not yet verified; no compromised host/database-superuser or production-ready claim is made. Restrict application, runtime, secret/commitment files and log access; enforce operational log/session retention and protect backups.
