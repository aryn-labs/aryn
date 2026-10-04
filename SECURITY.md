# Security guidelines (private development)

- Do not commit API tokens, `.env`, credentials, signing keys, payment secrets, personal data, or private customer documents.
- Treat LLM outputs and third-party content as untrusted. Authorization belongs to ARYN Core.
- Use least-privileged runtime scopes and no unrestricted host tool execution.
- Keep local runtime API loopback-bound with session authentication and origin protection.
- Never upload Local project data to remote model/provider without user selection and disclosure.
- Report suspected vulnerabilities **privately to the repository owner**. Do not paste secrets into GitHub Issues or logs.
- A repository scaffold is not a security audit; release gates are defined by ARYN-SEC-001.
