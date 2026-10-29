# seedhub-rcon: technical handoff

Audience: an AI assistant or developer. The master map of all three repositories is
[SYSTEM_OVERVIEW.md in seed-hub-bot](https://github.com/Wardogs-Seed-Hub/seed-hub-bot/blob/main/docs/SYSTEM_OVERVIEW.md).
Read it first. This page orients you in this repository.

## What it does

Small web service at **rcon.seedhub.gg**. Game-server owners sign in with Discord,
save their server's RCON address and password (encrypted), and create a read-only
API key per server. The SeedHUB bot uses that key to fetch the live player list
(names + SteamIDs), map, capacity and banner when it needs them. No background
scanning: reads happen on demand with a 30-second cache.

It is one of four RCON providers the bot supports. The others are Warguardian,
Warcon Hosted and Warcon Self-hosted. It is optional if server owners use those.
It does **not** use the SeedHUB MySQL database.

## Code map

```
seedhub_rcon/__main__.py   CLI: serve, check, keygen, rotate-key
seedhub_rcon/app.py        aiohttp routes, Host check, cookies, CSRF/origin check
seedhub_rcon/oauth.py      Discord sign-in (identify scope only)
seedhub_rcon/service.py    connections, API keys, player-list reads, caching
seedhub_rcon/rcon.py       game RCON protocol (fixed read-only commands)
seedhub_rcon/security.py   Fernet encryption, key digests
seedhub_rcon/database.py   SQLite schema and access
seedhub_rcon/config.py     settings (all prefixed SEEDHUB_RCON_)
seedhub_rcon/templates, static   single-page UI
```

API contract for the bot: [API.md](API.md). Design and threat model: [DESIGN.md](DESIGN.md), [SECURITY.md](../SECURITY.md).

## Run and deploy

- [DEPLOYMENT.md](DEPLOYMENT.md) is the full install/update/backup/key-rotation guide.
- Compose project `seedhub-rcon`, service `rcon`, `network_mode: host`, listens on
  `127.0.0.1:8080`, behind a Cloudflare Tunnel hostname.
- `.env` in the checkout (from [.env.example](../.env.example)); data in `./data`;
  encryption key in `RCON_KEY_DIR` (outside the checkout, mounted read-only).
- `SEEDHUB_RCON_PUBLIC_URL=https://rcon.seedhub.gg`. Requests with any other Host are
  rejected, and the Discord callback is derived from it.
- `SEEDHUB_RCON_ALLOWED_DISCORD_IDS` limits who can sign in (`*` = everyone).
- Tests are kept local-only (git-ignored `tests/`) and are not in the repository.

## Data and handoff

- To keep existing server connections, the new host needs the old
  `data/seedhub-rcon.sqlite3` (taken while stopped, with any `-wal`/`-shm`) **and**
  the original `encryption.key`. Without the key, stored RCON passwords are unreadable.
- Starting fresh is also valid: owners re-add servers, create new keys, and update
  their connection in the bot.
- API keys are stored only as digests. A lost key is replaced, not recovered.

## Things that break easily

- Changing the domain requires changing `PUBLIC_URL`, the Discord OAuth callback, the
  tunnel hostname **and** the hard-coded URL in the bot (SYSTEM_OVERVIEW section 6),
  all at once.
- Never regenerate the key file over an existing one. `keygen` refuses to overwrite.
- `AGENTS.md`/`CLAUDE.md` are git-ignored here by design. Repository rules for
  assistants are in `SECURITY.md` and `docs/`.
