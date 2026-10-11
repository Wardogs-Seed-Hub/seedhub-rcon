# SeedHub RCON

A small, self-hostable WARDOGS player-list service. Users sign in with Discord,
register their server connections, and create private read-only API keys.
The service reads only the server requested by an authorized client, plus explicit
owner connection tests. It never scans every registered server.

**Version 0.1.0 is prepared for restricted test deployment.** Local automated checks
use disposable data and simulated external services. Real Discord sign-in,
Cloudflare Tunnel, Docker container startup, and a real WARDOGS server still require
the deployment checklist. This is not a production acceptance or security audit.

## What works

The interface uses SeedHub's orange-and-black branding and existing logo.
Server addresses have no placeholder text; RCON ports are typed directly and
checked against the operator's approved ports.

- Discord sign-in with the identify permission only.
- Owner-only server registration, editing, testing, disabling, and removal.
- Verification of the server UUID/join code before a registration is saved.
- Duplicate-server protection without exposing the other registrant's identity.
- Unlimited saved connections per user; request and resource limits still apply.
- AES-256-GCM encryption for saved RCON passwords, using a separate key file.
- Per-server read-only API keys, shown once and stored only as SHA-256 digests.
- Key replacement/revocation and permission checks after network waits.
- On-demand player lists with a 30-second cache and shared concurrent lookups.
- Restricted network destinations, timeouts, response bounds, and retry delays.
- Docker Compose deployment and Cloudflare Tunnel configuration.

The Discord bot remains separate and decides when seeding is active. The RCON
service does not require team, account-plan, or seeding-state synchronization.
Anyone holding a valid read key can request that server's list, subject to limits;
the service cannot independently prove that seeding is active.

## API

```text
GET https://rcon.wardogseedhub.com/api/<server-uuid>/playerlist
Authorization: Bearer <server-read-api-key>
```

A response contains Steam IDs, names, player count, and the observation time.
An unavailable server returns an error, never an invented empty list.
A fresh read verifies server identity and then requests players: two read-only
RCON HTTP requests for that server. A cache hit makes neither request.

See [the API contract](docs/API.md). Credentials and keys must never appear in URLs.

## Test deployment

Follow [the step-by-step Ubuntu deployment guide](docs/DEPLOYMENT.md).
Use a separate test domain such as `rcon-test.wardogseedhub.com`, a dedicated
Discord OAuth application, an allowlist of test Discord users, and fresh test data.

Docker Compose builds the app from your Git checkout. It preserves the database
in ./data and mounts the external encryption-key directory read-only.
No Python installation on the VPS is needed outside Docker.

After the one-time setup in the deployment guide:

```sh
docker compose build --pull rcon
docker compose run --rm --no-deps rcon check
docker compose up -d --wait rcon
```

Run check only while the service is stopped. It opens/initializes the database
and verifies the key without contacting Discord or game servers.
Preserve any existing .env, data and key files.

The supplied Compose file targets Ubuntu/Linux using host networking.
The app binds only to 127.0.0.1, where your host's Cloudflare Tunnel connects.
Public access uses your HTTPS domain. There is no public app port, debug login
or insecure-network setting.

## Security and privacy

See [SECURITY.md](SECURITY.md) before hosting for others.

Saved RCON passwords are encrypted; API keys are stored as digests; session
cookies use HTTPS, HttpOnly, and SameSite protections. Secrets are excluded from
application logs, Git and the Docker image. Never enable raw request/access logging
on the OAuth callback, which contains short-lived authorization codes.

The game-side connection still uses unencrypted HTTP, an accepted WARDOGS
limitation. Cloudflare Tunnel does not encrypt that final network connection.

Local simulations and tests are not shipped. Runtime code contains no test login,
private-destination bypass, or production bot changes. Self-hosted observations
are not automatically trusted evidence for token rewards.

## Source and updates

Preferred Ubuntu location: ~/Apps/seedhub-rcon. After source publication,
clone into a new destination using SSH:

```sh
git clone git@github.com:Wardogs-Seed-Hub/seedhub-rcon.git ~/Apps/seedhub-rcon
```

For updates, use git pull --ff-only origin main, then rebuild and recreate the
container following the deployment guide's backup/check steps. Do not wipe an
existing application folder or configuration.

The Docker build context allows only runtime source and pinned requirements.
Credentials, databases, logs, local tests and assistant files are excluded.
Deploy directly from the repository with Compose.

## Further reading

- [Design and ownership](docs/DESIGN.md)
- [Validation results and pending live checks](docs/VALIDATION.md)
- [Deployment, updates, backup and key recovery](docs/DEPLOYMENT.md)

MIT licensed; see [LICENSE](LICENSE). Self-hosting, modification, and commercial
use are allowed under its terms.
