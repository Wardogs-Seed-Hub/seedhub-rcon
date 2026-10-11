# SeedHUB RCON

SeedHUB RCON lets WARDOGS community-server owners connect their servers and provide trusted services with on-demand player lists through a private API key.

## Features

- Sign in with Discord.
- Add, test, edit, enable, or remove your server connections.
- Automatically read each server's UUID through RCON before registration.
- Store RCON passwords encrypted.
- Create, replace, or revoke a read-only API key for each server.
- Retrieve player lists on demand, with a 30-second cache. No background scanning.

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

A successful response includes the player count, Steam IDs, player names, and observation time. Each key can access only its assigned server.

See the [API reference](docs/API.md) for responses and error codes.

## Documentation

- [Deployment and updates](docs/DEPLOYMENT.md)
- [API reference](docs/API.md)
- [Security notes](SECURITY.md)

**Security:** WARDOGS RCON uses unencrypted HTTP between this service and the game server. Review the security notes before deploying.

## License

MIT — see [LICENSE](LICENSE).
