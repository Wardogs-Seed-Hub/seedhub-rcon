# SeedHUB RCON

SeedHUB RCON lets WARDOGS community-server owners connect their servers and provide trusted services with on-demand player lists through a private API key.

## Features

- Sign in with Discord.
- Add, test, edit, enable, or remove your server connections using one address:port field.
- Automatically read each server's UUID through RCON before registration.
- Store RCON passwords encrypted.
- Create, replace, or revoke a read-only API key for each server.
- Retrieve player lists on demand, with a 30-second cache. No background scanning.
- Read verified join UUID, server name, current map, experience/game-mode identifiers
  and capacity directly from game RCON; no external server-list website is required.
- Get readable mode and mod labels alongside the original active experience IDs.
- Supply the server's optional sponsor/banner URL for active SeedHUB seeding cards,
  with on-demand ten-minute caching and no manual banner setup.
- View and copy the bot API response, including player names and Steam IDs, from each connection.

## Setup

You'll need Docker with Docker Compose, a Discord OAuth application, WARDOGS RCON access, and an HTTPS domain routed to the service.

```bash
git clone git@github.com:Wardogs-Seed-Hub/seedhub-rcon.git
cd seedhub-rcon
cp .env.example .env
```

Configure the environment, create the encryption key, and start the container using the [deployment guide](docs/DEPLOYMENT.md).

## Player-list API

```http
GET /api/<server-uuid>/playerlist
Authorization: Bearer <server-read-api-key>
```

A successful response keeps the existing fields and adds `server`. Each existing
read-only key still accesses only its assigned server. Sanitized example:

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
    "banner_url": "https://images.example.com/banner.png",
    "observed_at": "2026-10-13T15:00:01Z"
  }
}
```

`server_uuid` is verified against `/v1/server-id`. `count` always equals the
validated `/v1/players` list length; Steam IDs are strings. Top-level `observed_at`
records successful player-list validation. `server.observed_at` separately records
successful `/v1/status` validation. `served_at` is response creation time. Cached
responses retain both observation times. These timestamps are UTC, not game event times.
The examples are illustrative and contain no live attendance evidence.

If status fails or is malformed, `server` is `null`; the valid roster still succeeds.
Old status metadata is never carried into a new roster. Identity mismatch or failed player
collection fails the request; neither becomes a fresh empty list. A validated empty
roster has `count: 0` and `players: []`.

The bot may request approximately every 30 seconds during active seeding. Reads are
on demand, concurrent callers share collection, and snapshots are reused for less
than 30 seconds after player observation. This does not guarantee a new snapshot
on every poll. All game reads share a 10-second timeout. Optional status failures
pause status reads for five minutes while identity/player reads continue normally.
Explicit upstream rate limits or `Retry-After` still delay all game reads; required
identity/player failures retain increasing backoff. Honor `Retry-After` on errors.
Optional `/v1/sponsor` reads share that timeout and refresh a bounded,
connection/revision-bound banner cache every ten minutes on demand. Missing or
invalid banners return `banner_url: null`; ordinary sponsor failures preserve
status and players. No image bytes, background polling, migration or new key is
needed. See the API reference for validation, invalidation and rate-limit behavior.

The SeedHub adapter should use `server_uuid` for registration identity, `count` for
population/seed-success decisions, and `players[].steam_id`, `players[].name` plus
top-level `observed_at` for attendance. Read display details from `server.name`,
`server.map`, `server.mode`, `server.mods`, `server.max_players` and optional
`server.banner_url` when `server` is
non-null. `server.experiences` preserves the original game-provided identifiers.
Mode and mod labels are derived from recognized active experience IDs, with no
extra game requests. `mode: null` means the mode could not be identified uniquely.
`mods: []` means the recognized experiences report no modifiers; `mods: null`
means the list cannot be interpreted completely and should display as unavailable.
Unknown IDs remain in `experiences` for the bot to inspect. See the API reference
for the exact mappings and fallback rules.
Treat unavailable metadata as unknown and deduplicate attendance snapshots by UUID
and player observation time. Do not count `served_at` or metadata time as new attendance.

See the [API reference](docs/API.md) for responses and error codes.

## Documentation

- [Deployment and updates](docs/DEPLOYMENT.md)
- [API reference](docs/API.md)
- [Security notes](SECURITY.md)

**Security:** WARDOGS RCON uses unencrypted HTTP between this service and the game server. Review the security notes before deploying.

## License

MIT — see [LICENSE](LICENSE).
