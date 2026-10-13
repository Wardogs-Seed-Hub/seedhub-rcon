# Version 0.1.0 validation

## Region scope decision — 2026-10-13

Region collection and Pragma backend access were removed from the proposed scope
at the owner's request. Inspection found no implemented region field, lookup or
game-backend authentication in the RCON application or local helper scripts, so
no runtime code or stored data needed removal. API.md and DESIGN.md now explicitly
exclude this work. Documentation links and diff whitespace were checked; runtime
tests were not repeated for this documentation-only change. No application was
started, and no bot code or live service was changed.

## RCON server-information extension — 2026-10-13

Added selected server name, map, experience identifiers and capacity to the existing
authenticated player-list response. Identity, players and status come from fixed
game RCON routes; no external server-list website or sponsor image is fetched.
Player and status observations have separate timestamps. Optional status failure
returns null metadata with a valid roster and preserves shared backoff. Existing
keys, encrypted credentials, database schema and connection controls are unchanged.

57 offline regression tests passed on Windows/Python 3.14.2. These include existing
core authorization/cache/encryption/validation and mocked OAuth tests plus the new
transport, service and API-handler checks. Coverage includes selected-field
validation, populated/empty rosters, count independence from status population,
separate/cached timestamps, malformed and oversized bodies, redirects, partial
failures, the total timeout, identity mismatch, concurrent full/partial reads,
revocation and connection changes during status collection, and increasing bounded
backoff with Retry-After. The HTTP handler and response headers were exercised
without opening a listener. All game responses were synthetic; the supplied
discovery capture was used only as schema evidence and was not copied into source.

Python syntax compilation, pip check, diff whitespace and documentation/example
checks passed. Local regression files remain ignored by Git and excluded from the
Docker build context. No application startup, live RCON traffic, Discord bot edit,
commit, push or deployment was performed. Existing tests that start an application
or a local HTTP fixture were deliberately not run for this task.

Pending live acceptance: confirm fields against an authorized populated and empty
game server; verify actual three-request latency within the shared 10-second budget;
check approximately 30-second polling, status failures, cached observations and
upstream rate limits through HTTPS/Tunnel. After publication and deployment are
authorized, use the existing Git pull, backup and Docker rebuild/check/recreate
procedure in DEPLOYMENT.md. No data migration, replacement API keys or .env changes
are required. The Discord adapter handoff and sanitized response are in API.md.

The entries below record earlier work and are not claims that those checks were
repeated for this extension.

Checked locally on 2026-10-11. This is a restricted test-deployment candidate,
not production acceptance or an independent security audit.

## Automated results

48 isolated tests passed using Python 3.14.2 on Windows, after a clean virtual
environment install from requirements.txt. The final run completed in 5.337 seconds.
All external identity/player data was simulated; databases and encryption keys
were disposable fixtures.

Coverage includes:
- Encrypted credential storage, authenticated context binding, tampering and
  wrong-key rejection, key generation without overwrite, and atomic key rotation.
- Discord authorization-code exchange through the real Authlib/httpx2 client
  with a simulated provider; identify-only scope, callback state/browser binding,
  single-use callbacks, sessions, logout, and recent-login checks.
- Owner isolation, duplicate registration and simultaneous conflicts, escaped
  display names, form-origin and request-forgery protection.
- Per-server API keys, rotation/revocation, disabled/deleted connections,
  cross-server denial, and changed permissions during an in-flight read.
- On-demand behavior, concurrent lookup sharing, cache observation timestamps,
  expired-cache failures, restart persistence, and backoff without autonomous reads.
- Real local HTTP RCON simulations for identity-then-player reads, wrong server
  identity, rejected redirects, bounded payloads, and unsupported compression.
- Destination validation including private/special IPv4/IPv6 and mixed DNS answers.
- Fresh-process import safety, one-process database locking, configuration failure,
  and real CLI listener startup with health and unauthorized-API checks.

Syntax compilation passed for app and local test sources.
pip check found no broken requirements in the fresh release environment.

## Dependencies

requirements.txt pins the complete runtime dependency set.
pip-audit 2.10.1 checked all listed versions with --no-deps --disable-pip and
reported no known vulnerabilities after cryptography was updated to 50.0.0.
The initial 48.0.0 pin had published advisories and is not in the release.

All pinned packages resolved and downloaded as Linux x86-64/Python 3.12 compatible
wheels. This checks package availability, not Linux runtime execution.
The application has not yet been run inside Docker or through the VPS's Cloudflare Tunnel.

## Browser inspection

A loopback-only, ignored fixture served the actual templates using disposable
sample connections and simulated identity/RCON providers. Landing, dashboard,
connection details, and edit-form navigation were inspected through the browser's
page structure. The edit form had no horizontal overflow at the normal desktop
width and a phone-width viewport. The stored password field was blank.

Screenshot capture was unavailable through the browser tool, so full visual
screenshot review remains pending. No real Discord session or server credential
was used. The preview fixture is excluded from the Git and Docker build context.

## Git and Docker deployment

Deployment uses GitHub SSH pulls and Docker Compose. The earlier ZIP packaging
script, generated ZIP and systemd user unit have been removed.

Dockerfile copies only pinned requirements and the application package.
.dockerignore uses an explicit runtime-file allowlist, excluding credentials,
databases, logs, tests, assistant files and other checkout content.

Docker Compose v2.40.3 parsed and resolved the configuration successfully using
disposable placeholder settings. Checks confirmed the non-root user, persistent
data mount, read-only key mount, local host-network setup, container restrictions
and syntactically valid healthcheck. The build context was reviewed against the
explicit 15-file runtime/build allowlist; representative secret, test, cache and
assistant paths are excluded. Public documentation links and whitespace passed. The local Docker Engine is unavailable, so an image
build and container startup have not been verified. They remain required VPS
test-deployment checks. The 48 application tests above predate this deployment
change; application Python code was not changed.

Useful regression/security tests remain local and ignored. Publishing the source
does not establish Docker runtime or live-service acceptance.

## Pending owner checks

Use docs/DEPLOYMENT.md for the test setup and acceptance checklist:
- Docker image build, container startup, file permissions and persistence on the VPS.
- Real Discord OAuth application/callback and allowed-account sign-in.
- Cloudflare Tunnel routing, HTTPS, host-header settings, and cache bypass.
- One explicitly authorized real WARDOGS server, including protocol fields,
  empty player lists, timeouts, and UUID verification.
- Live key revocation, restart, idle behavior, backup/restore, and mobile rendering.
- A private support destination and duplicate-dispute procedure before public launch.

The existing Discord bot is unchanged. Automatic pairing and attendance-based
rewards are separate work. No production credentials, live data, DNS, or hosted
services were changed during this implementation.

## Branding and form update

After the owner confirmed VPS startup and successful Discord sign-in, the UI
was updated to the supplied SeedHub logo and orange/black branding. Website
HTTP notices, their acknowledgment requirement and the footer source link were
removed. The RCON port is a numeric-keyboard text field; the address has no
placeholder. The operator's approved-port checks remain enforced.

51 isolated tests passed on Windows/Python 3.14.2 (6.168 seconds), including
registration and editing without acknowledgment, invalid/unapproved port
rejection before network access, and safe logo delivery. The Docker build context
includes the supplied logo; its bytes match the original attachment.

Local browser checks confirmed the logo loads, the background is black, the
accent is orange, the port is a text field and the address placeholder is absent.
The form and landing page had no horizontal overflow at the checked mobile width;
the desktop form also fit. Screenshot capture timed out, so final visual review
remains an owner check. This UI update still requires a VPS pull and rebuild.

## Browser sign-out fix

Reproduced the owner's sign-out error by clicking the real form in the local
browser with a disposable session. The global no-referrer policy caused the
native form's Origin to be null, which the existing exact-origin check rejected.
Synthetic HTTP tests had supplied Origin explicitly and missed this browser behavior.

Normal pages now use same-origin referrer policy; OAuth callback responses keep
no-referrer. Origin and CSRF validation remain strict. Cookie expiry now uses
the same Secure, HttpOnly, SameSite=Lax, Path=/ attributes as cookie creation,
including for OAuth browser-binding cleanup.

52 isolated tests passed (5.713 seconds) on Windows/Python 3.14.2. Coverage includes
session invalidation without affecting another session, correct cookie-expiry
attributes, rejection of missing/null/foreign Origin and wrong CSRF tokens,
and OAuth success/failure privacy and cleanup.

The local browser reproduced the error before the change. After the change,
clicking Sign out returned to the logged-out landing page, and server setup
required signing in again. The preview uses only disposable simulated identity
and data. VPS pull/rebuild and an owner sign-out check remain pending.

## Automatic registration identity — 2026-10-11

Registration now discovers the UUID from the authenticated RCON identity route,
then validates the player list before saving. The form no longer accepts a join
code. All 55 isolated tests passed, including real local HTTP fixtures for UUID
discovery and normalization, ignored submitted UUIDs, duplicate refusal, and
failed authentication/identity/player responses leaving no registration. Existing
connections cannot be edited to a different identity. Python compilation and
diff whitespace checks passed. Tests use disposable data and simulated game
servers; owner testing against a real WARDOGS server remains pending.

## Combined RCON address field — 2026-10-11

Add and Edit use one address:port field. IPv4, hostnames and bracketed IPv6 are
parsed into the existing stored host and port fields; no data migration is needed.
All 59 isolated tests passed, including registration and editing with the combined
field, IPv6 round trips, invalid input rejection before transport calls, and
continued private-network blocking. Python compilation and whitespace checks
passed. Tests used local fixtures; VPS rollout and real-server acceptance remain
pending.

## All valid RCON ports — 2026-10-11

Removed the operator port allowlist at the owner's request. Registration, edits,
tests and API reads accept destination ports 1–65535. Existing RCON_PORTS settings
are ignored; no .env or database migration is needed. Public-address checks,
fixed read-only routes, redirect refusal, authentication and rate limits remain.
All 62 isolated tests passed, including low/high port acceptance, invalid-port
rejection and configuration with missing or legacy allowlists. Python compilation
and diff checks passed. No live game-server requests or VPS deployment performed.

## Owner player-list preview — 2026-10-11

Added View player list beside Test connection. It displays copyable, formatted
JSON with the same fields and player data as the bot API. Owner access requires
an active session and valid form protection, but no API key. API access still
requires its server-specific key. Both paths share the cache, lock, rate limits
and retry delays, and recheck permission/revision after waiting.

All 68 isolated tests passed, including matching API/preview data, escaped player
names, text Steam IDs, empty lists, no credentials in the response, unauthorized
and disabled access, logout/deletion/edit during reads, shared concurrent reads,
and failure backoff. Python compilation and diff checks passed. Real-server data,
visual layout and browser clipboard behavior await owner testing on the VPS.
