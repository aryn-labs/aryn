# ARYN Studio — Home & Chat V1.0 validation

Validation of the local `development` working tree, 11 October 2026.
HEAD remains `e8a56d040fa5ba6bfff541dc16bf1652173e9a9f`. No commit, push,
merge or change to `main`. **Real AI chat works; full acceptance remains open**
for the PostgreSQL environment and gateway provenance limitations below.
This report supersedes the earlier Home-only and pre-consent validation reports.

## Implemented and reviewed

- Existing shell, logo, navigation and workspace selector preserved; semantic
  dark/light surfaces replace decorative separators. Dark tokens match the V1.0 request.
- Home: local-time greeting, minimal bounded composer, actual model picker,
  horizontal Send arrow, centered quick actions, at most three attention items,
  four mixed work items and four actual activities. Backend inventories and
  effective permissions distinguish New, Active, Issues and unavailable/error states.
- Persistent chat: server acknowledgement before navigation, follow-ups, refresh/
  resume, optional scoped history, safe Markdown/Copy, pinned header/input and
  message-only scrolling. Replies do not move someone reading earlier messages.
- First-use consent: short dialog before transfer or metered readiness check;
  signed, revocable Core receipts replace per-conversation checkboxes.
- Indonesian default and English through Settings → Preferences → Language;
  server-persisted personal preference, locale-aware dates, no language control on Home.
- Request deduplication, exact retry after ambiguous acknowledgement, cancellation
  on scope/unmount, and account/organization/project cache isolation.

## Results actually obtained

| Check | Result |
| --- | --- |
| Frontend format, ESLint, strict TypeScript, production build | PASS |
| Frontend unit/component tests | 73 PASS across 9 files; final locale refinement also rechecked |
| Home/App Shell E2E | 90 PASS; New/Active/Issues, keyboard, permissions, recovery and navigation |
| Chat integration browser E2E | 14 PASS, real API/Core/database with explicitly isolated runtime |
| Full non-PostgreSQL backend regressions | 905 PASS, 5 optional SKIP, 92 PostgreSQL deselected at that collection |
| Final chat/settings/model/migration integration suite | 38 PASS after consent receipt-read optimization |
| Installed native Hermes boundary | 1 PASS, isolated network/model doubles; not live inference proof |
| PostgreSQL suite collection | 99 cases collected; execution BLOCKED, not PASS |
| Actual API Home and persisted Chat visual/Axe checks | 20 views PASS; five widths × dark/light for both pages |
| Ruff, repository hygiene, actionlint, Python lock consistency | PASS |
| Python dependency audit | 73 distributions, no known advisories |
| npm dependency audit | No reported vulnerabilities at any severity |
| Redacted working-tree/new-source secret scan | PASS |
| Real model first answer, follow-up, refresh/resume | PASS, three completed `ds/deepseek-flash` turns through Core/Hermes/9Router |

The two backend warnings are upstream Authlib deprecations. The five full-suite
skips are optional native/live tests; the installed native boundary was executed
separately. PostgreSQL cases added after the full run explain 92 deselected versus
99 now collected. Old PostgreSQL PASS evidence at revision 021 is not proof of 022.
Browser fixture responses are confined to tests and are not represented as real AI.

## Real AI evidence

Production Studio, no browser interception or runtime fixture:
`http://127.0.0.1:8710/chat/chat_c2c341edf7484ce1abb6ce5e42be85bf`.

1. Asked why rainbows form; received an actual Indonesian explanation.
2. Asked why red is on the outside, referring to the prior answer; received an
   actual contextual explanation in the same conversation.
3. Reloaded, asked which color is outermost; received “Merah”, then reloaded and
   verified all three persisted responses. Consent was not requested again.

The signed Core records have exact requested/actual `ds/deepseek-flash`, gateway
9Router, runtime Hermes, completed status and measured total tokens 3443, 4039,
3826. These totals exclude separately governed readiness probes. Configured
provider is `9router`; underlying `actual_provider` is null, never fabricated.

Ignored local evidence under `.local/chat-finalization/`:

- `live-v1-final.log`: first-use consent and first two real answers. Its initial
  third-turn browser helper timed out before sending while capability was loading.
- `live-v1-resume.log`: corrected helper waits for Send readiness; third real turn
  and refresh succeed on the same conversation, with no repeated consent.
- `live-v1-core-proof.json`: read-only database extraction of the three signed
  turns, linked attested Core runs, measured usage and signed consent receipt.
- `backend-final.xml`, `backend-final.log`, `backend-chat-final.log`,
  `native-final.log`, `unit-final.log`, `home-e2e-final.log`, `chat-e2e-final.log`.
- `live-home-visual-review.json`, `live-chat-visual-review.json` and
  `live-home-{width}-{theme}.png` / `live-chat-{width}-{theme}.png`.
- `home-{new,active,issues}-*` and `chat-offline-core-*` are test-only fixtures.
- `changed-files.txt` is the complete pending working-tree file inventory.

## Visual comparison

Reviewed the supplied shell screenshot and rendered
`ARYN_Home_Interactive_Concept.html` from the user's Downloads folder. Preserved
its compact content hierarchy, whitespace, neutral surfaces and turquoise accent.
The latest V1.0 instructions replace the prototype's title, explanatory composer,
scenario picker, sample records, gradients and two-column lists with the greeting,
minimal composer and bounded mixed list. The prototype shell was not copied.

Actual visual/interaction checks cover 1920, 1440, 1024, 768 and 390px in dark/light.
No page/workspace horizontal overflow, page errors or Axe WCAG A/AA violations were
found in the 20 actual API views. Desktop/mobile images were visually inspected,
including light contrast, button/input spacing and readable conversation alignment.
E2E covers IME, Enter/Shift+Enter, blank/duplicate prevention, short mobile viewport,
focus traps/Escape restoration, language persistence, consent decline/revocation,
scoped history and preserving scroll position while reading earlier messages.

## Quality gates and remaining blockers

The latest inspected remote failed run is
[38039055095](https://github.com/aryn-labs/aryn/actions/runs/38039055095).
Its hygiene failure was the redundant `apps/web/.gitkeep`. Pending deletion repairs
that root cause. Required frontend, browser and dependency gates are configured;
existing backend/security/native/PostgreSQL gates are retained. No security check
was weakened. Remote CI has not run for these uncommitted changes.

Docker Desktop's Linux engine fails during startup, reporting inaccessible
`sailor-ingest.sock` while initializing its ingest server. WSL's docker-desktop
instance remains stopped; the Linux engine pipe is absent. No reset, reinstall,
Docker data deletion or security bypass was attempted. Re-run all 99 PostgreSQL
cases against disposable PostgreSQL with the restricted application writer once
that external environment is repaired; revision 022 is not yet validated there.

Current public Hermes/9Router evidence reports the exact model and gateway, but
not an attested downstream provider identity or local-only transfer classification.
All uncertain routes therefore require consent. A loopback gateway is never
presented as local inference. Changes to gateway/route namespace/policy invalidate
consent; material remapping hidden behind an unchanged namespace cannot be
independently detected without trusted gateway routing evidence. That contract
is needed for full provider-identity/reconsent/local-exemption acceptance.

Streaming and Stop are absent because runtime cancellation/token streaming is not
supported. Connect Apps and full builders remain honest unavailable scaffolds,
without fake success or hidden mutations. Context, token, rate and Core budget
limits remain in force. No production hosted deployment certification is claimed.

See [contracts, architecture and changed files](../../docs/chat-workspace.md).
