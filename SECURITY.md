# Security design

This describes the version 0.1.0 test release. Local checks cover the implemented
protections, but this is not an independent security audit or production approval.
See docs/VALIDATION.md for tested behavior and remaining live acceptance.

## Known connection limitation

WARDOGS RCON uses plain HTTP in the supported hosting scenario. Requests expose
the RCON credential and responses to an observer on that network path; responses
may also be altered in transit. Saved-password encryption and a Cloudflare Tunnel
cannot repair that game-server connection. The limitation is documented here;
the website does not display transport warnings or require an acknowledgment.
Do not label the system end-to-end encrypted.

Treat each RCON credential as an admin credential, without assuming it has
read-only permissions. Where a host supports source-IP restrictions, allow only
the service's stable outgoing IP. This limits access; it does not encrypt traffic.
Keep transport code isolated so verified HTTPS can be supported when the game
and hosting provider make it available.

## Protected service boundary

- Use a domain with HTTPS and Cloudflare Tunnel for published instances.
- Bind the application to loopback. Run the Tunnel connector on the same host.
  Do not publish the application port or allow a direct-IP bypass.
- Authenticate in the application, even when Cloudflare Access is enabled.
  Optional Access service credentials are an additional layer, not per-server
  permission checks.
- Do not trust identity headers from arbitrary callers. Use explicit verification
  if Cloudflare identity is incorporated later.
- Disable shared/CDN caching for authenticated API and setup routes. Return
  Cache-Control: no-store and ensure configured Cloudflare rules respect it.
- The domain is not a secret. Cloudflare can process proxied content; this is not
  secrecy from Cloudflare or from an administrator controlling the service host.

## Credential storage and owner setup

Passwords use cryptography's AES-256-GCM with a fresh 96-bit nonce per encryption.
Authenticated encryption detects tampering. The format includes the nonce and
ciphertext; additional authenticated context binds each value to its internal
connection ID, Discord owner ID, server UUID, and format version.

The master key is a separate 32-byte random key in an owner-only file outside
the repository. A protected encrypted sentinel detects wrong keys on startup.
The CLI can re-encrypt all stored passwords and the sentinel atomically while
the service is stopped; see docs/DEPLOYMENT.md. Never reuse the storage key for
API access, Cloudflare, OAuth, or sessions. Older backups still require their old key.

The running service must decrypt a password to use it. A compromise of the full
host can expose keys and credentials. Encryption mainly protects a database stolen
without its key.

Enroll credentials on the service's HTTPS page after Discord OAuth2 sign-in.
Use the authorization-code flow with identify only, a fixed registered HTTPS
callback, and single-use state bound to the initiating browser session. Validate
the callback before exchanging the code and obtain the user ID directly from
Discord, never from form fields. Exchange codes server-side using a maintained
OAuth library. The service never asks for a Discord password or bot token.

OAuth proves Discord identity, not game-server ownership. Separately validate
RCON authentication and the actual server UUID before accepting registration.
Do not retain Discord access/refresh tokens beyond identity lookup when they are
not needed; persist only the minimum identity and protected local session.
Never put RCON credentials or API keys in URLs. Redact OAuth callback codes/state
from request logs, remove them via a clean redirect, and avoid third-party assets
on the callback page.

Keep passwords out of browser responses, HTML after submission, Discord messages,
exceptions, analytics, access logs, and Git. Redact Authorization headers and
sensitive form bodies. Protect browser sessions against forgery with secure
cookies, request-forgery defenses, and fresh checks for sensitive changes.

Owners may replace and remove credentials but cannot read back saved passwords.
Replacing a destination or password requires a new server identity check.
Removing a connection invalidates its API keys and cached data.

## Owner isolation and API access

Use the Discord user ID on each connection to authorize all owner management.
The bot does not supply ownership records, team memberships, or hosted allowances.
Browser sessions must be unguessable, expire, support logout, and use Secure,
HttpOnly, SameSite cookies. Protect state-changing actions against request forgery
and require recent sign-in for credential, deletion, and key operations.

Use a separate high-entropy read-only API key for each registered connection.
Show it once; persist only its digest and metadata. This key is distinct from the
RCON password, encryption key, OAuth client secret, and Cloudflare credentials.
See docs/API.md for generation and verification requirements.

Scope every read to its key's internal connection ID. A key must not enumerate
other users' servers, authorize an arbitrary destination, or manage connections.
Check key validity, connection revision, and enabled state before returning a
cached result and after waiting for RCON. Revocation and deletion persist across
restart. A deleted registration's key cannot authorize a replacement with the
same public UUID. Securely transfer bot pairing keys; never post them publicly.

Only the bot knows whether seeding is active. The service does not claim that a
valid key proves active seeding. It handles authorized on-demand reads without
background scans or bot-state synchronization.

Native browser forms require the exact configured Origin and a session-bound
CSRF token. Normal pages use Referrer-Policy: same-origin so native form posts
retain their Origin while outbound navigation sends no referrer. OAuth callback
responses retain no-referrer to protect callback parameters. Cookie expiration
preserves the Secure and Path=/ requirements of __Host- cookies; logout also
deletes the server-side session.

## Duplicate registration

Enforce uniqueness on normalized, verified server UUIDs within the instance.
Validate the destination and RCON identity before revealing a duplicate warning.
The existing owner can manage their own record; a different registrant gets the
generic warning documented in docs/DESIGN.md, without the owner's identity or
credentials. Anonymous requests cannot discover registrations.

Authentication to RCON is evidence of access, not exclusive ownership: credentials
may be shared with admins. Never auto-transfer another owner's registration.
Privately review disputes and reverify control before an operator-authorized
transfer; revoke old API keys and invalidate cached/in-progress data.
The test-release recovery procedure is in docs/DEPLOYMENT.md; private support is required before public launch.
No cross-instance duplicate registry is planned.

## Safe outbound connections

Users must not be able to make the service contact its own host, private network,
cloud metadata endpoints, or arbitrary URLs. Accept a host and port, not a
user-supplied request path or method. Construct a small allowlist of fixed RCON
read routes in code.

Resolve and validate IPv4 and IPv6 destinations at each new connection, reject
loopback/private/link-local/reserved destinations, and connect to the validated
address to prevent a hostname changing to an internal address between checks.
Refuse HTTP redirects so credentials cannot be forwarded to another destination.
Allow RCON ports from 1 to 65535 while retaining public-address restrictions. Limit connection attempts,
response sizes, and parsing work. Local simulations use isolated test fixtures,
not a public configuration switch disabling these rules.

Apply timeouts, concurrency limits, rate limits, and increasing retry delays.
Never retry authentication failures rapidly. Bound cache size as well as lifetime.
Do not offer arbitrary command execution, kicks, bans, writes, or configuration edits.

## Data minimization and recovery

Return only player Steam IDs and names, a count, the verified server UUID, selected
server name/map/experience/capacity fields, an optional validated public HTTPS
banner URL, and separate player/status observation timestamps.
Never forward raw status/configuration/sponsor responses or fetch sponsor image
bytes. The only additional RCON route is fixed GET /v1/sponsor; its imageUrl is
validated display data and never an HTTP request destination. Banner cache entries
are bounded and tied to the connection ID, revision, owner and UUID; connection
changes invalidate them. See docs/API.md for URL validation and refresh rules.
Do not collect player addresses or unrelated gameplay statistics.
Keep player snapshots in bounded memory by default, not permanent history.
Audit connection creation/removal, owner changes, authorization failures, and
credential replacement with identifiers and times, not secrets or player lists.

Backups containing credentials remain sensitive even if fields are encrypted.
Keep encrypted backups outside the checkout. Protect a recoverable copy of the
encryption key separately, document retention/deletion, and test restoration.
A lost key must never trigger silent key regeneration over an existing database.
Removing live records does not instantly remove them from retained backups.

On an incident, disable affected connections and tokens, rotate exposed RCON
passwords at the game host, rotate compromised service keys, and review sanitized
audit records. Publish deployment-specific retention and incident procedures
before accepting third-party credentials.

## Self-hosted evidence

An instance operator can change the software and fabricate a player list.
HTTPS and signed responses do not prove attendance. Do not automatically use
self-hosted observations for SeedHub payouts. The game-side HTTP limitation also
limits the assurance of managed observations. Reward policy is separate work.

## Reporting an issue

Do not post real passwords, keys, database files, or exploit details in public
issues. Use GitHub's private vulnerability reporting feature if the repository
offers it. A private contact and repository reporting settings must be configured
before a public hosted launch; there is no verified reporting mailbox yet.
For restricted testing, set SUPPORT_URL to your private support destination and
keep ALLOWED_DISCORD_IDS restricted to the participating test accounts.

## References

- [Browser form Origin and referrer policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy#effect_on_the_origin_header)

- [Discord OAuth2](https://docs.discord.com/developers/topics/oauth2)
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/)
- [Cloudflare service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)
- [OWASP outbound request safety](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [Warcon's observed WARDOGS protocol](https://github.com/warcon-app/warcon/blob/main/docs/wardogs-api.md)

## Operational boundaries

The CLI sets a private file-creation mask and binds only to loopback. A process
lock enforces one application instance per database. Docker Compose uses a non-root
user, a read-only container filesystem, dropped capabilities and no privilege
escalation. Only the data directory and temporary storage are writable; the
external key directory is read-only. Linux host networking preserves the local
Tunnel connection but does not isolate the container from the host network. Tests run with injected simulations; no test login or
private-network exception is available through runtime configuration.

SQLite stores only hashes of session IDs, OAuth state/browser binding values,
and API keys. Sessions expire after four hours; sensitive actions require a
sign-in no more than 15 minutes old. Login state expires after five minutes and
is consumed once, before the provider code exchange.

Structured audit records contain identifiers, action labels, and times without
secrets or player lists. Records older than 90 days and expired login/session/rate
records are removed on requests. Raw HTTP access logging is disabled by the
launcher. Unexpected errors produce a generic message without logging exception
text or request data. Operator backup retention is separately configurable
outside this application.

Dependencies are pinned and checked for known published vulnerabilities.
This does not guarantee that a dependency or the application has no unknown flaw.
