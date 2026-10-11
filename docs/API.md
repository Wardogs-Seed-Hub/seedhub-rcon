# Player list API contract

This is the version 0.1.0 test-release contract. The owner has deployed the app
for testing; live player-list acceptance remains pending. Bot pairing is separate.

## Route and identity

```http
GET /api/<server-uuid>/playerlist
Authorization: Bearer <server-read-api-key>
Accept: application/json
```

Hosted base URL: https://rcon.wardogseedhub.com

The server UUID is the verified WARDOGS server identity, bound to one registered
connection and Discord owner within the instance. It is not authentication.
Clients never send an RCON password, destination address, or arbitrary command
through this route. Secrets and authorization tokens must not appear in URLs.

## Read-only API key

An authenticated owner generates one active key per connection. Generate at least
32 random bytes using the operating system's secure random generator, encode them
for transport, and show the key only once. Store a SHA-256 digest for comparison,
not its plaintext value. High-entropy generated keys do not use human passwords.
Use constant-time verification and never log the Authorization header.

A key is bound to an internal connection ID and that instance's database, not
merely to a reusable server UUID. It permits only playerlist:read on that
connection. A key cannot manage registrations or reveal an RCON password.

Owner actions can revoke or rotate the key. Rotation invalidates the old key
immediately. Disabling or deleting a connection blocks reads, and re-registering
the same UUID requires a new key. Enforce these changes after network waits as
well as before cache access, including when other callers share a lookup.
Key and enabled-state changes persist across restart.

The owner securely provides the key, instance HTTPS URL, and UUID to the bot.
The bot stores the key as a secret and does not send it to another instance or
follow API redirects with credentials. Exact bot pairing UI is separate work.

The bot is responsible for only issuing automatic reads during active seeding.
The RCON service authenticates the caller's permission for the server but does
not independently check seeding state. There is no request_id, team/plan claim,
signed bot grant, or membership synchronization requirement.
Possession of a valid read key permits a throttled read even outside seeding.

Cloudflare Access, if configured, adds separate machine credentials; it does not
replace the server-specific API key. Discord owner sessions authorize management,
not this bot endpoint. UUID knowledge or Discord login alone cannot read another
person's registered server.

## Owner login and registration

Use Discord OAuth2 authorization-code sign-in with identify only. Verify the
callback state and obtain the user ID from Discord on the server side.
The callback is /auth/discord/callback and must match the HTTPS redirect
URI registered for that instance. OAuth login does not require a Discord bot
installation or team data.

Verify RCON credentials and the actual server UUID/join code before finalizing a
registration. The database must enforce one registration per UUID per instance,
with no per-user server-count limit.
The same owner is directed to their existing connection; a different owner gets
a server_already_registered conflict (HTTP 409) after verification, with the message:
"This server is already registered. Contact the server owner. If you own the
server and need help, contact this service's support."

Do not return the existing owner's identity or connection details. This deliberate
duplicate warning is limited to verified registration attempts, not a public UUID
lookup. Never let a second registrant overwrite the first registration.
Owner routes use server-rendered forms and a session cookie, not the API key:
- GET /auth/discord and GET /auth/discord/callback for sign-in.
- POST /logout for ending the current session.
- GET / for the owner's connection list.
- GET/POST /connections/new for verified registration.
- GET /connections/<internal-id> for owner-only details.
- GET/POST /connections/<internal-id>/edit for verified updates.
- POST /connections/<internal-id>/players for an owner-only JSON preview.
- POST /connections/<internal-id>/<action> for test, key, revoke, enable, disable, delete.

All POSTs require the session's csrf form value and an Origin matching PUBLIC_URL.
Sessions last four hours; mutations require sign-in within 15 minutes.
Mutations other than test/edit/add/logout require a confirmation form.
A successful key creation returns the new key once in a no-store owner page.
Passwords are never returned. A connection test returns a status, not a player list.
The separate View player list button displays the successful API response as
formatted, copyable JSON. It requires an active owner session and CSRF protection,
but no API key or recent-sign-in confirmation. It shares the API's cache, lock,
rate limits and retry delays, and refuses disabled connections. Permissions and
session validity are rechecked after waits. The public API still requires a key.
GET /healthz returns a minimal local service/database status and does not check RCON.

## Successful response

```json
{
  "server_uuid": "8b579bf0-77da-44b8-b8cf-c926246be187",
  "observed_at": "2026-10-11T15:00:00Z",
  "served_at": "2026-10-11T15:00:12Z",
  "cached": true,
  "count": 1,
  "players": [
    {
      "steam_id": "76561198000000000",
      "name": "Example Player"
    }
  ]
}
```

The identifiers above are illustrative, not evidence of a live server or player.
Steam IDs remain strings to avoid numeric rounding in clients.
count must equal the length of the validated players array.
Names are untrusted display text: escape them when rendering and prevent Discord
mentions if later displayed there.

observed_at is when this service completed the successful game-server read,
not a game-supplied attendance timestamp. served_at is when this response was
created. cached indicates reuse; reused observations keep their original time.
Use the server UUID and observed_at to avoid counting one snapshot repeatedly.

For a validated empty server, return count: 0 and players: [].
Never return that response for a timeout, missing credentials, or parsing failure.

Return Content-Type: application/json and Cache-Control: no-store.
Cloudflare and other shared caches must bypass this route. The service may use its
own isolated in-memory snapshot cache for at most 30 seconds.
Do not serve older snapshots as a successful current player list.

## Errors

Use a small, stable, sanitized error body:

```json
{
  "error": {
    "code": "rcon_unavailable",
    "message": "The game server could not be checked."
  }
}
```

| HTTP status | Code | Meaning |
| --- | --- | --- |
| 400 | invalid_request | Malformed UUID or unsupported request shape |
| 401 | unauthorized | Missing or invalid API key, including a revoked key |
| 403 | access_denied | Authenticated connection is disabled |
| 404 | server_not_found | Unknown server or server outside the key's permission |
| 429 | rate_limited | Per-server, caller, or instance request limit reached |
| 502 | invalid_rcon_response | Upstream response cannot be safely validated |
| 503 | rcon_unavailable | Connection failure or rejected RCON credentials |
| 503 | service_unavailable | Required local configuration or storage unavailable |
| 504 | rcon_timeout | Game-server read exceeded its allowed time |

Do not return raw upstream bodies, addresses, passwords, headers, or stack traces.
A rejected RCON password is not the same as an invalid API key.
Return a bounded Retry-After value on rate limits and temporary failures where
appropriate. A more specific credential fault may appear only in the authenticated
owner setup/status flow, never in a cross-owner discovery response.

## Timing and limits

- Recommended bot interval: 60 seconds; minimum fresh-fetch spacing: 30 seconds.
- Successful snapshots may be reused for up to 30 seconds after observation.
- One in-progress lookup per connection; simultaneous callers share it only
  after individual authorization.
- Upstream timeout: 10 seconds total for DNS, slot wait, identity, and player reads.
- Eight concurrent RCON operations; 256 KiB per response, 512 players,
  256 characters per name, and 256 cached connection snapshots.
- 1,200 requests/minute globally; 120/minute per caller IP; 60 API reads/minute
  per connection. The latter can reuse cached results without new RCON traffic.
- Setup: six attempts/minute per owner and three/minute per destination.
  Saved-connection testing also has a 30-second per-connection interval.
- Next-read delays survive restart; a missing in-memory cache can therefore
  produce a temporary 429 after a restart until the saved delay expires.
- On transient failures, increase delay up to five minutes and honor applicable
  Retry-After responses. Do not immediately retry invalid credentials.
- Validate API keys on every read, including cached reads and retries.
- Setups/tests have separate strict limits and require the connection owner's session.
- A retry delay schedules no autonomous read; another authorized call is required.

## Bot interpretation

Presence means only that the server reported that Steam ID in that observation.
Absence, unavailable, and cached presence are distinct results.
No attendance-duration claim, automatic payout, population-policy replacement,
or continuous-presence guarantee is included.
