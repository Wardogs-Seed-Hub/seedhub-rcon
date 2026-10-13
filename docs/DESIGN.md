# Service design

## Scope and deployment

The Discord bot runs on Bisect. SeedHub RCON runs on a VPS behind Cloudflare
Tunnel at https://rcon.wardogseedhub.com. Self-hosters use their own domain and
are recommended to use the same Tunnel setup. Nothing runs alongside game servers.

Version 0.1.0 implements the player-list reader using Python, aiohttp, SQLite,
Jinja2, Authlib with httpx2, and cryptography AES-256-GCM. The application is
prepared for restricted test deployment, not accepted for production.
See DEPLOYMENT.md for configuration and VALIDATION.md for actual checks.

Hosting region is outside this integration's scope. Do not add region collection,
Pragma backend access, server-browser authentication, IP geolocation or an
owner-entered region as part of this project. The service uses the fixed RCON
read routes documented in API.md; it does not query server-list websites.

## Independent Discord sign-in

Users open the RCON website directly and sign in with Discord OAuth2.
Request only the identify permission needed to obtain their Discord user ID.
The service does not need guild membership, team membership, email, or a bot token.
Use Discord's authorization-code flow with a server-side code exchange and
single-use session-bound state validation.

Create a local session after verified sign-in. Store the stable Discord user ID,
not a typed username or a client-supplied ID, as the owner of each connection.
A Discord login proves the person's Discord identity; it does not prove they own
a game server. Successful RCON authentication and verified server identity are
separate registration checks.

The RCON service does not synchronize solo/team accounts, subscription plans, or
selected seeding servers with the bot. Owners can register and test connections
while the bot is offline.

## Registration and duplicate handling

A signed-in user enters a connection name, one RCON address:port field, and a
password. Accept IP:port, hostname:port, or [IPv6]:port. Store the parsed host
and port separately. Accept any port from 1 to 65535 while retaining public
destination restrictions.
Validate the destination before contacting it. Authenticate to the fixed RCON
identity route and discover the server UUID from its response, then check the
player-list response before saving. No UUID or join code is entered by the user;
any client-supplied UUID is ignored during registration. Existing connections
must still match their saved identity when edited or read.

Only persist an enabled registration after successful identity verification.
If that identity cannot be read, return a clear setup failure; do not reserve
an unverified UUID or silently accept a name match.

Each registration stores:
- An internal connection ID and its revision.
- The owner's Discord user ID as a string.
- The normalized, verified WARDOGS server UUID/join code.
- RCON host, port, encrypted password, with a versioned encryption context.
- Creation/update times, enabled state, and sanitized connection-test status.
- A separately generated read-only API key digest and key metadata.

Users may save any number of servers on hosted and self-hosted instances.
Request throttles, concurrency bounds, and storage-abuse protections still apply.

Enforce a database unique constraint on the normalized server UUID across the
whole instance, not on the combination of user ID and server UUID. Check and
write atomically so concurrent registrations cannot create duplicates.

After identity verification, handle a duplicate as follows:
- Same Discord owner: direct them to their existing connection to update it.
- Different owner: refuse the duplicate and show:
  "This server is already registered. Contact the server owner. If you own the
  server and need help, contact this service's support."
- Do not reveal the registrant's Discord ID, RCON address, password, API key, or
  player list. A duplicate warning is not permission to view the existing record.

RCON credentials may be shared among admins, so possession does not prove
exclusive ownership. Never automatically overwrite or transfer another person's
registration. Ownership disputes need private operator review with fresh evidence;
support cannot recover a password from the website for a claimant.
Operator-assisted account recovery is not exposed in this release; see the private dispute procedure in DEPLOYMENT.md. Any eventual transfer
invalidates old keys, cached data, and in-progress reads.

Duplicate detection applies within one instance. There is no global registration
registry or cross-instance synchronization.

## Owner management

Owners can list their own connections, explicitly test them, change credentials,
disable them, remove them, and rotate or revoke their read-only API keys.
Use fresh sign-in confirmation for sensitive actions. Other signed-in users do
not gain access merely by knowing a server UUID.

Updating credentials or the destination must reverify the same server identity.
Changing the UUID requires a new registration rather than retargeting an existing
key. Update revisions atomically and invalidate old cached/in-progress results.
Deletion revokes keys before a replacement registration can become available;
old keys must never authorize a later registration with the same server UUID.

Tests run only after an explicit owner action and are rate-limited. Loading the
dashboard does not contact all saved servers. Display last-tested time and state,
not an invented current health result.

## Bot access

The bot is an API client, not the owner-directory provider for the website.
All bot traffic goes outward to the service; no API hosted on Bisect is needed.

The owner generates a read-only API key for a registered server and securely
pairs the instance URL, server UUID, and key with the bot. The exact bot setup
interface is separate work. Keys must never be sent through public Discord
messages or URL parameters.

The service verifies that key is current, enabled, and bound to the requested
connection. A key only allows reading that server's player list. It cannot list
other registrations, edit connections, test arbitrary destinations, or retrieve
RCON passwords. No shared master key that reads every user's server is exposed.

The bot alone decides whether a server is currently seeding and stops requesting
when seeding ends. The RCON service has no independent active-request knowledge
or request lifecycle synchronization. An authorized key holder can call its read
endpoint outside seeding, subject to throttling; preventing that would require
additional bot-state coupling and is not part of this simpler design.

## Reading player lists

There is no independent service polling timer. The bot normally requests every
approximately 30 seconds while seeding; fresh-fetch spacing is at least 30 seconds
after the previous successful player observation, subject to cache/backoff.
No request means no RCON read, except explicit owner connection tests.

For each read:
1. Authenticate the key and verify permission for the enabled connection.
2. Reuse a matching authorized snapshot at most 30 seconds old.
3. Otherwise share one in-progress lookup for that connection.
4. Verify the UUID, then fetch the fixed player-list route with bounded time and response size.
5. Validate players and record their observation time, then fetch selected status
   fields with the remaining timeout. Preserve Steam IDs as strings. Status has
   its own observation time; failure returns null metadata and retains valid players.
   Readable mode and mod labels come from exact recognized active experience IDs.
   Keep the raw experiences for compatibility and unknown IDs; no additional
   catalog read is required. API.md defines unknown and unmodified results.
6. Recheck key validity, enabled state, and connection revision after the network
   wait before delivering the result.

Cache keys include internal connection identity and revision, not just the public
UUID. Reused results retain their original observation time. Never count cached
reads as new evidence.

Stopping bot requests stops subsequent polling. A request already sent may finish;
the bot must ignore a late response after its seeding request has ended.
The service cannot detect that event by itself. Deletion, disabling, or key
revocation during a lookup must prevent delivery under the old permission.

Timeouts, invalid responses, and unreachable servers are unavailable observations,
not empty lists. A validated successful read may legitimately contain zero players.
Snapshots do not prove continuous presence between reads.

## Data and restart

Persist Discord owner IDs, verified connections, encrypted RCON credentials,
hashed read-only API keys, connection revisions, owner sessions as needed, and
sanitized administrative events. Player snapshots default to bounded memory and
disappear on restart. No player-history archive is introduced.

Startup validates configuration and encryption-key availability. Restart does not
scan saved servers. Disabled connections and revoked keys remain unusable across
restarts, and ownership must be checked before every operation.

## Runtime boundaries and acceptance

One CLI process owns the SQLite database and a process lock. Imports do not open
data or read dotenv. The service creates no polling/background network tasks.
Default settings require an explicit allowlist of Discord IDs for test access;
an explicit * opens sign-in to everyone without adding per-user server limits.

Owner sessions last four hours. Mutating operations require sign-in within the
last 15 minutes and both a same-origin request and a valid form token.
Login attempts are bound to the browser and expire after five minutes.

One fresh API/preview read requests /v1/server-id, /v1/players and /v1/status in order.
Registration/edit/test checks use only the first two routes. Public IPs are
validated and pinned for the read. All destination ports from 1 to 65535 are allowed.
The total operation timeout is 10 seconds, concurrency is eight, and responses
are capped at 256 KiB, 512 players, and 256 characters per name.

Successful cache entries are reused for less than 30 seconds; at most 256 snapshots
are retained in memory. Rate-limit and next-read state persists in SQLite.
Requests are limited globally and per caller, and setup/testing has separate
owner, destination, and connection throttles. Failures delay later calls up to
five minutes; no autonomous retry is scheduled.
Optional status failure also preserves shared backoff and Retry-After, without
extending the valid roster's cache lifetime or reusing older status as fresh.
See API.md for the exact selected fields, validation and adapter handoff.

Local automated checks and simulated browser inspection are recorded in
VALIDATION.md. Real Discord login, game-server compatibility, Ubuntu service
startup, Tunnel routing, and owner-operated backup restoration remain live
acceptance work. Public launch also requires private support and dispute handling.
