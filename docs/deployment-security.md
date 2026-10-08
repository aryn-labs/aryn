# Deployment authentication dan runtime isolation

Baseline: `27c3f0e66840ef4dee671dc5852fe4c3142d9465`, branch `development`.
Boundary ini adalah fondasi integration verification; **hosted production readiness belum dibuktikan**.
Tidak ada deployment VPS, inference live/berbayar, credential IdP production, atau perubahan `main`.

## Audit dan root cause

**H4:** `create_app` selalu membuat shared development principal dan `/api/session`
tanpa mempertimbangkan deployment environment. Check peer loopback merupakan check
jaringan, bukan authentication: reverse proxy lokal membuat pengguna internet terlihat
sebagai koneksi loopback. Host/Origin tidak dapat membuktikan identitas pengguna.

**M6:** `_http_route_table` wrapper menambahkan route pada seluruh native Hermes table.
Lebih jauh, native `connect` memasang `/p/{profile}` ingress, plugin handlers dan background
native work di luar route table. Menyaring daftar route saja belum menutup jalur tersebut.
Native session headers juga dapat memilih conversation pada route teks yang sah;
`X-Hermes-Session-Id` dan `X-Hermes-Session-Key` kini ditolak sebelum handler native.
Audit memakai installed Hermes revision `937f23db2d707cde1c87337fde3aafee514d117c`.

Perbaikan menggunakan Studio/API, Core identity/PermissionEngine, schema dan Hermes
existing. Tidak ada authorization engine kedua, scheduler, worker framework atau runtime pengganti.

## Local versus Hosted

| Boundary | Local development | Hosted OIDC |
|---|---|---|
| Mode | `ARYN_ENV=development`, `ARYN_AUTH_MODE=local-development` wajib eksplisit | `ARYN_AUTH_MODE=oidc`; semua environment selain development memerlukan mode ini |
| Exposure | Loopback peer, exact loopback Host/Origin; forwarded headers ditolak | Exact configured public HTTPS origin/host; trusted proxy exact IP atau direct TLS |
| Principal | Fixed local owner yang hanya diprovisikan pada Local | Verified issuer/subject → administrator provisioned DB mapping → current membership |
| Cookie | `aryn_studio_session`, HttpOnly, Strict, `/api`, 8 jam; memory/process | `__Host-aryn_session`, Secure, HttpOnly, Lax, `/`, tanpa Domain; DB, default 1 jam |
| Core policy | Existing permissions, membership, approvals, governance, execution claim | Kebijakan Core yang sama; signed session reference dan commit revalidation tambahan |

Mode default authentication adalah disabled/fail closed. `testing=True` bukan bypass
production. Launcher Windows Local memilih local-development secara eksplisit, menolak
non-development environment dan tidak mengganti pilihan OIDC secara diam-diam.
Local development tetap merupakan akses perangkat tepercaya, bukan released Windows
production authentication atau proteksi terhadap proses/administrator host yang compromised.

## OIDC dan trusted Core principal

`GET /auth/login` memulai Authorization Code + S256 PKCE menggunakan Authlib. State,
nonce dan code verifier acak disimpan sebagai transaksi lima menit; state/browser secret
disimpan sebagai keyed digests. Cookie login `__Host-aryn_login` Secure/HttpOnly/Lax
mengikat callback ke browser yang memulai login. Query redirect/scope/role tidak diterima.

`GET /auth/callback` menerima hanya satu `code` dan `state`. Transaksi dikunci dan
dihapus/commit **sebelum** await token exchange. Replay, callback browser lain,
expired transaction, provider error, state/nonce mismatch dan redirect substitution ditolak.
Exchange hanya menuju configured HTTPS token endpoint dengan configured callback,
tanpa HTTP redirects, ambient proxy environment atau provider fallback.

PyJWT memverifikasi ID token dengan pinned issuer/client audience, RS256 atau ES256,
JWKS signing key, expiry, issued-at, subject, nonce dan authorized party untuk multi-audience.
Algoritma `none`/HMAC dan token-controlled key URLs tidak digunakan. JWKS HTTPS cache
berumur maksimum 300 detik; unknown kid memicu satu refresh. Rotation memakai kid baru
diuji. Reuse kid dengan key baru dapat ditolak sampai cache refresh; UAT provider diperlukan.
Authorization/token/JWKS endpoints dikonfigurasi eksplisit, bukan ditemukan dari browser input.
Tidak ada email/username/role claim sebagai bukti atau pemetaan principal.

`external_identities` hanya diisi administrator tepercaya: exact `(issuer, subject)` unik
dipetakan ke `actor_id`, `organization_id`, status. Login tidak membuat mapping, organization,
membership, project, ataupun admin. Pemetaan ke shared development actor/organization ditolak.
Operator deployment harus memverifikasi subject provider dan existing authorized membership
sebelum provisioning; tidak ada public signup/provisioning endpoint pada scope ini.
Reprovisioning issuer/subject/actor/organization dilakukan oleh administrator tepercaya:
cabut sessions yang mereferensikan mapping sebelum mengubah binding, lalu wajibkan login
ulang. Mapping/session database tetap berada dalam trusted administration boundary.
Interactive OIDC principal menjadi Core `ActorType.USER`; browser/provider role atau
actor-type claims tidak dapat membuat human approval authority. Organization/project
membership tetap diputuskan PermissionEngine, termasuk existing org-admin oversight.

Session opaque baru selalu dibuat setelah login, old session browser dicabut, dan session
ID tidak diterima dari payload. DB hanya menyimpan HMAC token digest dan identity reference,
expiry/revocation. Access token/ID token tidak dipersist atau dikirim ke frontend.
Session-secret rotation menginvalidasi seluruh old session; jangan rotasi Core evidence key
untuk mengatasi session expiry. Hosted session tetap berlaku setelah restart dengan secret
dan DB yang sama; local process sessions tetap invalid setelah restart.

Core binder menandatangani `auth_session_id` bersama identity. Menghapus/mengganti reference
membuat context invalid. PermissionEngine memeriksa current session/mapping dan existing
membership dalam authorization transaction; mutation session mengunci session/mapping dan
membership rows (`BEGIN IMMEDIATE` SQLite, `FOR UPDATE` PostgreSQL). Logout/revocation dan
mutation mempunyai urutan commit, bukan janji membatalkan runtime yang sudah di-claim.
Tidak ada DB transaction ditahan selama provider login atau inference. Existing Core
reservation/settlement, owner fencing, BN-06, AF-07, immutable receipts dan 013 commitments
tetap menjadi authority. Revalidation tidak mengubah historical approvals atau run provenance.

## Session, CSRF dan transport

Semua `/api/` memerlukan sesi hosted, termasuk SSE initiation dan workspace. Mutation
memerlukan exact Origin, same-origin Fetch metadata jika tersedia, dan keyed CSRF token
yang terikat opaque session. `/api/session` mempertahankan POST compatibility tetapi pada
hosted **hanya membaca** csrf/mode untuk sesi yang sudah authenticated: tidak menerbitkan,
memperpanjang, atau mengganti identity; karena itu bootstrap read ini tidak meminta CSRF
yang belum bisa diperoleh browser. Origin dan authentication tetap wajib.

`POST /api/logout` memerlukan CSRF, mencabut DB session dan menghapus cookie. Expired,
revoked session/mapping atau revoked membership tidak dapat melakukan privileged mutation.
Logout ini mengakhiri sesi ARYN; IdP SSO/global logout/backchannel revocation belum diimplementasi.
Account revocation provider saja tidak langsung mencabut sesi ARYN yang sudah diterbitkan:
administrator harus mencabut mapping/session/membership atau menunggu expiry. Tidak ada refresh-token storage.

CORS credentialed cross-origin tidak diaktifkan; hanya configured same origin. Debug,
diagnostics, OpenAPI dan API documentation paths ditolak. Tidak ada Studio WebSocket route.
Public SPA/assets tidak membawa identity/runtime credentials. Frontend menampilkan login
link hanya untuk literal `/auth/login`; arbitrary redirect dari error tidak digunakan.
JSON/SSE errors memakai existing sanitized code/IDs; internal provider exception/token tidak
ditampilkan. Diagnostic log records disanitasi dan dependency traceback dihapus; log access,
rotation/retention dan backup tetap tanggung jawab deployment. Sanitation tidak dapat
mengenali seluruh arbitrary unlabeled sensitive text.

## Konfigurasi

Local: `.env.example` dan `scripts/start-aryn.ps1`; runtime/gateway tetap loopback.
Hosted memakai `python -m services.api` pada satu host bersama proxy/runtime. Supply via
restricted environment/secret manager, jangan menyimpan production secret dalam repository.

| Variable | Hosted requirement |
|---|---|
| `ARYN_ENV` | `production` |
| `ARYN_AUTH_MODE` | `oidc` |
| `ARYN_PUBLIC_ORIGIN` | Satu exact HTTPS origin, mis. `https://studio.example.org`, tanpa path/query/credentials |
| `ARYN_OIDC_ISSUER` | Exact verified provider issuer HTTPS, termasuk path/trailing slash yang ditentukan provider |
| `ARYN_OIDC_CLIENT_ID` | Registered client/audience |
| `ARYN_OIDC_CLIENT_SECRET` | Confidential client secret jika provider mensyaratkan Basic client authentication; public PKCE client boleh tanpa secret |
| `ARYN_OIDC_AUTHORIZATION_ENDPOINT` / `ARYN_OIDC_TOKEN_ENDPOINT` / `ARYN_OIDC_JWKS_URI` | Explicit trusted HTTPS provider endpoints |
| `ARYN_OIDC_REDIRECT_URI` | Tepat `${ARYN_PUBLIC_ORIGIN}/auth/callback`; register exact URI pada provider |
| `ARYN_SESSION_SECRET` / `ARYN_IDENTITY_SECRET` | Distinct explicit random secrets, minimum 32 karakter; satu secret/session domain tidak menjadi key Core evidence |
| `ARYN_SESSION_TTL` | 60–28800 detik, default 3600 |
| `ARYN_TRUSTED_PROXIES` | Comma-separated exact peer IP; tidak ada wildcard/CIDR. Same-host Nginx dapat memakai `127.0.0.1` |
| `ARYN_STUDIO_HOST` / `ARYN_STUDIO_PORT` | Explicit upstream loopback/port, mis. `127.0.0.1`, `8710` |
| `ARYN_DATABASE_URL` | Explicit database connection; no hosted fallback to local Studio DB |
| `ARYN_EVIDENCE_SECRET` | Explicit existing Core evidence key; backup/rotation harus menjaga historical verification |
| `ARYN_HISTORY_COMMITMENT_PATH` | Independent protected durable commitment path dengan ACL existing 013/014 |
| `ARYN_RUNTIME_BASE_URL` | Explicit same-host loopback Hermes, mis. `http://127.0.0.1:8642` |
| `API_SERVER_KEY` | Explicit private random runtime transport credential, minimum 32 karakter; shared hanya API dan dedicated runtime |
| `ARYN_9ROUTER_BASE_URL` / `ARYN_9ROUTER_API_KEY` | Loopback gateway `/v1`, optional server credential; provider keys tidak dibaca ARYN |

Semua endpoint runtime tetap loopback pada deployment yang didukung sekarang. Separate
runtime container/private network belum merupakan konfigurasi yang diimplementasi/diuji;
kontrak ini tidak membuka bind `0.0.0.0` untuk mempermudah deployment. Hosted HTTP requests
tidak memakai local client-loopback identity check: proxy yang sah dapat membawa user
internet ke authenticated API melalui loopback upstream.

## Reverse proxy contoh kontrak

Browser → HTTPS reverse proxy → ARYN API/Core loopback → private same-host Hermes → 9Router.
Jangan publish/forward port Hermes/9Router. Backend bind loopback dan firewall harus
membatasi port upstream; process lain pada host tetap berada dalam trusted host boundary.
Single execution authority 014 tetap wajib; tidak ada multiworker scale-out.

Contoh Nginx berikut adalah konfigurasi untuk review/UAT, **belum dijalankan pada server**:

```nginx
server {
    listen 443 ssl;
    server_name studio.example.org;
    # Supply certificate/key outside repository; configure TLS per operational policy.
    ssl_certificate /etc/aryn/tls/fullchain.pem;
    ssl_certificate_key /etc/aryn/tls/private.key;
    location / {
        proxy_pass http://127.0.0.1:8710;
        proxy_set_header Host studio.example.org;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host studio.example.org;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Forwarded "";
        proxy_set_header X-User "";
        proxy_set_header X-Role "";
        proxy_set_header X-Forwarded-User "";
        proxy_set_header X-Auth-Request-User "";
        proxy_buffering off; # Core SSE
    }
    location = /auth/callback {
        access_log off; # Never persist authorization code/state query strings.
        proxy_pass http://127.0.0.1:8710;
        proxy_set_header Host studio.example.org;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host studio.example.org;
        proxy_set_header Forwarded "";
        proxy_set_header X-User "";
        proxy_set_header X-Role "";
        proxy_set_header X-Forwarded-User "";
        proxy_set_header X-Auth-Request-User "";
    }
}
```

Proxy harus reject unknown incoming hosts pada default vhost dan menimpa/clear incoming
forwarded/identity headers. ARYN juga memeriksa exact Host/Origin. `Forwarded` format tidak
didukung; X-Forwarded-Proto harus satu literal `https` dari trusted peer. Forwarded-For
tidak pernah menjadi identity authority. Uvicorn proxy-header rewriting dinonaktifkan
agar middleware melihat peer transport asli. Direct HTTP upstream tanpa trusted proxy
headers ditolak; mengirim forged headers dari peer dipercaya sekalipun tetap tidak dapat
melewati verified OIDC/session/Core authorization. Proxy trust tidak menjadi admin trust.

## Runtime allowlist aktual

Wrapper membangun aplikasi aiohttp dan listener sendiri memakai native Hermes handler
yang diperlukan. Native `connect`, profile middleware, plugin wiring dan orphan sweeper
tidak dipanggil. API bind `127.0.0.1`; browser Origin/Upgrade/native session-ID/session-key selection
ditolak. Health minimal tanpa credential hanya untuk liveness; route lain membutuhkan
runtime transport authentication dan confinement check. HTTP body maksimum 64 KiB.

| Method | Route | Operation |
|---|---|---|
| GET | `/health` | Minimal actual Hermes version/liveness, tanpa administrative metadata |
| GET | `/health/detailed` | Authenticated minimal health, tanpa native diagnostic internals |
| GET | `/v1/toolsets` | Authenticated verified empty toolsets |
| GET | `/v1/capabilities` | Only actual allowlisted operations; jobs/scheduler/admin/streaming false |
| GET | `/aryn/gateway` | Existing exact gateway/model evidence contract |
| POST | `/v1/chat/completions` | Single text turn with exact 9Router model/provider, no native streaming |
| POST | `/v1/runs` | Existing bounded asynchronous text execution |
| GET | `/v1/runs/{run_id}` | Existing run result/evidence |
| POST | `/v1/runs/{run_id}/stop` | Stop request; Core still treats acknowledgement as unconfirmed runtime outcome |

Tidak tersedia: `/api/jobs/*`, `/api/cron/fire`, `/api/sessions/*`, profile `/p/*`,
platform callbacks, native `/v1/responses`, model options/admin, skills/artifacts,
room grants, browser-control WebSocket/register, run approval/steer/events, plugin
endpoints dan unknown routes. Valid shared API key tetap tidak memberi operasi tersebut.
Native execution bukan Core approval authority. Runtime key trusted untuk allowlisted
text/result operations di private host, bukan perlindungan terhadap compromised Core/host
atau pencuri credential yang mendapat network access internal. Tidak ada klaim per-run
cryptographic runtime fencing di luar existing Core owner/claim contract.

Request allowlist juga memblokir tools/tool_choice/fallback/provider substitution,
session selection dan internal `_aryn_receipt` dari HTTP. Model options hanya temperature
dan output cap, dengan typed/range validation. Agent construction memaksa toolsets kosong,
fallback disabled, one iteration, no compression/memory/background/title model calls.
Existing ExactGatewayTransport memverifikasi actual model dan credential confinement;
physical provider calls dalam tes selalu HTTP doubles, bukan model live.
Top-level dan `model_options` limits harus sama bila keduanya diberikan; handler sync/async
memakai lokasi berbeda, sehingga alternate/duplicate limit yang diabaikan tidak boleh
menampilkan batas palsu. Konflik ditolak sebelum dispatch, bukan dipilih secara diam-diam.

## Database migration dan compatibility

`015_authentication_boundary` melanjutkan `014_execution_authority`, menambah hanya
`external_identities`, `auth_sessions`, `login_transactions`. Tidak ada seeded identity,
membership, backfill approval/receipt, atau perubahan history/run/budget schema.
SQLite fresh metadata/migrations dan 015 ↔ 014 downgrade/upgrade diuji. Disposable
live PostgreSQL migrations, restricted non-owner writer, locking, history triggers,
signed-provider/API sessions dan governance concurrency kini diuji melalui
[CI verification](ci-validation.md); VPS operational configuration tetap perlu UAT.
Downgrade menghapus sessions/mappings/login transactions sehingga memerlukan login/
provisioning ulang bila kembali upgrade; history/evidence existing tetap dipertahankan.
Stop old binaries sebelum migration; mixed revisions atau multiple authority processes
tidak didukung. Jangan jalankan Local admin mode di hosted origin.

Read-only copies database aktual berhasil upgrade 009 dan 004 → 015. Studio copy
mempertahankan 8 runs, 13 versions, 84 audit events, 4 approvals dan 1 membership;
database kedua kosong tetap kosong. Ketiga auth tables kosong, integrity_check `ok`,
foreign-key check kosong, hash file sumber tidak berubah. Legacy evidence tetap readable
dalam scope yang sah dengan compatibility restrictions existing 013/014.

## Validation dan residual

Hasil dan commands aktual final dicatat pada [deployment validation](deployment-validation.md).
Dedicated signed-provider/API/Core tests dan installed native Hermes route dispatch
merupakan bukti H4/M6 dalam boundary yang didukung, bukan bukti deployment internet.
TestClient HTTPS adalah ASGI scheme fixture; tidak melakukan TLS handshake production.
Installed Hermes menggunakan isolated home/config dan network-denied model doubles.

IdP nyata (registration, policies/MFA, account revocation/logout, unique kid rotation),
PostgreSQL VPS operations, TLS termination, Caddy/Traefik/Nginx config, firewall, container networking,
VPS ACLs, protected backups, log access/retention dan disaster recovery tetap perlu UAT.
SSO backchannel logout, session inventory/admin UI, rate limiting di edge, and multiworker
tidak ditambahkan. Pending login transactions dibatasi 256 dan expired entries dibersihkan;
session rows expired/revoked memerlukan operational retention cleanup. Global IdP account
revocation harus diteruskan sebagai ARYN session/mapping/membership invalidation.
History/ledger/key/host trust boundaries dan provider hard-limit limitations dari
013/014 tetap berlaku. Hosted freeze **BLOCKED** sampai bukti deployment nyata tersedia.

Referensi implementation protocol: [Authlib OAuth HTTP client/PKCE](https://docs.authlib.org/en/stable/oauth2/client/http/index.html)
dan [PyJWT verification API](https://pyjwt.readthedocs.io/en/stable/api.html).
