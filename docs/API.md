# Player list API contract

This is the version 0.1.0 test-release contract with additive server information
and readable mode/mod labels. The server-information extension is running on the
owner's VPS; the mode/mod additions have only been tested locally. Existing route,
authorization, keys and player fields remain compatible. Live acceptance of the
new labels remains pending.

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
  "observed_at": "2026-10-13T15:00:00Z",
  "served_at": "2026-10-13T15:00:12Z",
  "cached": true,
  "count": 1,
  "players": [
    {
      "steam_id": "76561198000000000",
      "name": "Example Player"
    }
  ],
  "server": {
    "name": "Example Community Server",
    "map": "Ozeti",
    "experiences": ["Madrid_KOTH_01", "KOTH_InfantryOnly"],
    "mode": "King of the Hill",
    "mods": ["Infantry Only"],
    "max_players": 100,
    "observed_at": "2026-10-13T15:00:01Z"
  }
}
```

The identifiers above are illustrative, not evidence of a live server or player.
Steam IDs remain strings to avoid numeric rounding in clients.
count must equal the length of the validated players array.
Names and server strings are untrusted display text: escape them when rendering and prevent Discord
mentions if later displayed there.

Top-level observed_at is when this service finished collecting and validating
/v1/players, before any status fetch. It is not a game-supplied attendance timestamp.
server.observed_at is when /v1/status was successfully collected and validated.
served_at is when this response was created, including on cache hits. All times
are UTC ISO 8601 strings ending in Z, optionally including fractional seconds.
cached indicates reuse of the snapshot; both observation timestamps remain unchanged.
Use server_uuid and top-level observed_at to avoid counting one snapshot repeatedly.
The endpoints are separate observations, not an atomic game snapshot.

The new server field is either the complete object above or null. Its source mapping:

| API field | Game source | Validation and meaning |
| --- | --- | --- |
| server_uuid | /v1/server-id: serverId | Normalized UUID; must match the registered connection on every fresh collection |
| server.name | /v1/status: serverName | Nonblank string, at most 256 characters; not the owner's local connection label |
| server.map | /v1/status: map | Nonblank string, at most 256 characters; returned unchanged |
| server.experiences | /v1/status: experiences | Array of 0–32 nonblank strings, each at most 256 characters; raw game-mode/experience identifiers |
| server.mode | Derived from active experiences | Readable mode string, or null when no unique recognized base experience is present |
| server.mods | Derived from active experiences | Array of readable modifier labels; [] for recognized unmodified mode, null when interpretation is incomplete |
| server.max_players | /v1/status: players.max | Integer 1–512; booleans, strings and fractional values rejected |
| server.observed_at | Service clock | Successful status validation time, independent of player observation |
| players[].steam_id | /v1/players: players[].steamId | Unique 17-digit string; never converted to a number |
| players[].name | /v1/players: players[].name | String, at most 256 characters |
| count | Validated /v1/players array length | Upstream count must agree with the array; never /v1/status players.current |

Server strings reject ASCII control characters. Missing or invalid selected status
fields invalidate the entire server object. Unknown upstream fields are ignored;
configuration, passwords, addresses, scores and unrestricted responses are not exposed.
No sponsor/image URL is included and neither /v1/sponsor nor image bytes are fetched.

### Mode and mods

The service translates these exact, case-sensitive experience IDs. The mappings
are based on the supplied game catalog evidence; a live catalog request is not
needed for each read. Only IDs in the active /v1/status experiences array count.

| Active experience ID | Classification | Display label |
| --- | --- | --- |
| Madrid_KOTH_01 | Base mode | King of the Hill |
| Bakurani_KOTH_01 | Base mode | King of the Hill |
| Detroit_KOTH_01 | Base mode | King of the Hill |
| KOTH_InfantryOnly | Modifier | Infantry Only |
| KOTH_Hardcore | Modifier | Hardcore |

- mode is "King of the Hill" when exactly one distinct recognized base ID is
  present. Without one, or with multiple distinct base IDs, mode is null.
- mods is an array only when there is one recognized base and every experience
  ID is recognized. Labels retain upstream order, with duplicate labels removed.
  A recognized base alone produces []; do not display that as unavailable.
- If any experience ID is unknown, mods is null rather than an incomplete list
  or a misleading []. A recognized base may still supply mode in that case.
- Empty experiences or modifiers without a recognized base produce null for both
  mode and mods. Unknown/ambiguous IDs do not invalidate otherwise valid status
  or players and do not trigger failure backoff. Raw experiences are always kept
  unchanged, including order and duplicates, for future parser support.
- map remains the exact /v1/status map value. These labels do not rename maps.
- The new fields share server.observed_at; deriving labels is not a new observation.
  Cached replies retain the same labels, raw IDs and observation times. No new
  endpoints, background jobs or upstream requests are introduced.

The bot should render mode: null and mods: null as unavailable, mods: [] as None,
and a nonempty mods array as a comma-separated list. When server itself is null,
all its display details are unavailable. Attendance still uses the player fields.

Hosting region is intentionally not part of this API. The examined RCON responses
do not expose it. Region collection and Pragma backend access are out of scope;
there is no region lookup, estimate or owner-entered fallback. The SeedHub adapter
must not require a region field from this response or infer one from the server
name, map or experience identifiers.

If status times out, fails, is unsupported, or is malformed after a valid player
collection, return HTTP 200 with the existing player fields and server: null.
There is no status observation timestamp in that case. Never carry metadata from a
previous snapshot into the new one or give it a new timestamp. A cache hit reuses
the whole original snapshot (including null if status failed), without more requests.
Failure backoff still applies; partial success does not bypass upstream Retry-After.
No raw upstream error details are exposed. A failed identity/player read remains
an error, even if an older valid snapshot or metadata exists.

For a validated empty server, return count: 0 and players: [].
Never return that response for a timeout, missing credentials, or parsing failure.

Return Content-Type: application/json and Cache-Control: no-store.
Cloudflare and other shared caches must bypass this route. The service may use its
own isolated in-memory snapshot cache for less than 30 seconds after player observation.
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

- Bot polling approximately every 30 seconds is supported; 60 seconds is also valid.
  There is no exact refresh guarantee: polling time, collection duration, cache age,
  scheduling, rate limits and backoff affect when a new observation is available.
- Successful snapshots may be reused for less than 30 seconds after player observation.
  The next fresh fetch is allowed 30 seconds after that observation on full success,
  not 30 seconds after the later status fetch or API response. A just-early poll
  can reuse a snapshot and delay the next observation until another request arrives.
- One in-progress lookup per connection; simultaneous callers share it only
  after individual authorization.
- Upstream timeout: 10 seconds total for slot wait, DNS, identity, players and status.
  Fresh API/owner-preview collection makes at most three sequential fixed GETs:
  /v1/server-id, /v1/players, /v1/status. Status uses only the remaining time;
  timeout after valid players yields server: null. Registration/edit/test checks
  still require only identity and players. No immediate upstream retries occur.
  Waiting for another caller's per-connection lock is outside that transport budget.
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
- Optional status failures also increment the shared persistent failure counter:
  delay 60, 120, 240, then 300 seconds after collection, or the larger bounded
  upstream Retry-After. Full success resets the counter. Integer Retry-After is
  bounded to 30–300 seconds; missing/unparseable values on upstream 429 use 60.
  During this delay a still-valid roster cache may be served with server: null;
  after its 30-second lifetime, return 429 with Retry-After until collection is due.
  This deliberately reduces attendance availability during status trouble instead
  of repeatedly contacting a server that asked the service to wait.
- Validate API keys on every read, including cached reads and retries.
- Setups/tests have separate strict limits and require the connection owner's session.
- A retry delay schedules no autonomous read; another authorized call is required.

## Bot interpretation

SeedHub adapter handoff (bot changes are separate):

- Keep the same authenticated route and existing per-server key. Verify returned
  server_uuid equals the paired join UUID; fresh collections verify it via RCON.
- Use count for population and seed-success policy, and players[].steam_id and
  players[].name for the roster. Status population is intentionally not exposed.
- Deduplicate attendance using server_uuid plus top-level observed_at. Check its
  age even when cached is false; never use served_at or server.observed_at as
  attendance evidence. cached: true is reused evidence, not a new observation.
- When server is non-null, read name, map, mode, mods and max_players for server
  display, using server.observed_at to judge their age. Preserve experiences when
  inspecting unknown IDs. Treat null as unknown, not blank name/map, zero capacity
  or an unmodified game. Any bot-retained display fallback must keep
  its old observation time and be labeled stale. Do not infer absence from null.
- Poll on demand during active seeding at approximately 30 seconds; honor errors
  and Retry-After. Failed reads mean unavailable, never zero players. Stop processing
  late results after seeding ends. Neither server-list website is required for these fields.

Presence means only that the server reported that Steam ID in that observation.
Absence, unavailable, and cached presence are distinct results.
No attendance-duration claim, automatic payout, population-policy replacement,
or continuous-presence guarantee is included.
