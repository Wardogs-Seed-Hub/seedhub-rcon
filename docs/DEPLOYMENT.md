# Docker Compose test deployment

Deploy from GitHub to an Ubuntu VPS using Docker Compose. Use a test domain,
a dedicated Discord OAuth application, allowed test Discord accounts, and an
authorized game server for initial checks. Source publication and live acceptance
are separate from local preparation.

## Get the source

Use a non-root Ubuntu account with GitHub SSH access and Docker Engine with the
Compose v2 plugin. Docker access grants powerful control over the host; keep it
limited to the operator.

For a new folder, after this source has been pushed to GitHub:

```sh
mkdir -p ~/Apps
git clone git@github.com:Wardogs-Seed-Hub/seedhub-rcon.git ~/Apps/seedhub-rcon
cd ~/Apps/seedhub-rcon
docker compose version
```

If the application folder already exists, preserve its .env and data. Do not
clone over it or delete it to fix Git setup. Connect it to the SSH remote
separately when needed. Never run git clean -fdx.

## Configure the test instance

```sh
cd ~/Apps/seedhub-rcon
umask 077
mkdir -p data ~/.config/seedhub-rcon
chmod 700 data ~/.config/seedhub-rcon
test -e .env || cp .env.example .env
chmod 600 .env
id -u
id -g
```

Edit .env privately:

- RCON_UID and RCON_GID: the two numbers printed above. Use your non-root account,
  not 0. They let the container access files owned by you without running as root.
- RCON_KEY_DIR: the full host path to ~/.config/seedhub-rcon, for example
  /home/youruser/.config/seedhub-rcon. Do not use a literal ~.
- SEEDHUB_RCON_PUBLIC_URL: https://rcon-test.seedhub.gg or your test domain.
- SEEDHUB_RCON_KEY_FILE: leave /run/seedhub-rcon/encryption.key for initial setup.
  This is the path inside the container, not the path on the VPS.
- SEEDHUB_RCON_DISCORD_CLIENT_ID and SEEDHUB_RCON_DISCORD_CLIENT_SECRET:
  values from your dedicated Discord OAuth application.
- SEEDHUB_RCON_ALLOWED_DISCORD_IDS: comma-separated test account IDs.
  An explicit * opens sign-in to everyone; keep initial testing restricted.
- RCON connections accept any port from 1 to 65535. The old
  SEEDHUB_RCON_RCON_PORTS setting is ignored and may be removed from existing .env files.
- SEEDHUB_RCON_SUPPORT_URL: optional HTTPS link to private support.

Compose fixes the database path at /data/seedhub-rcon.sqlite3 inside the container.
The actual files stay in ~/Apps/seedhub-rcon/data on the VPS across rebuilds.
Leave the app port at 8080 unless it is already in use; if changed, update the
Tunnel service address too.

Use single quotes around .env values containing literal dollar signs so Compose
does not interpret them as variable substitutions. Never post .env, rendered
Compose configuration, Docker inspection output, or secrets in chat/issues.
Validate quietly with docker compose config --quiet.

Register this exact callback in the Discord Developer Portal for the test app:

```text
https://rcon-test.seedhub.gg/auth/discord/callback
```

Use your chosen domain if different. Login requests identify only; this OAuth
application does not need installation as a Discord bot.

## Build and create the encryption key

```sh
cd ~/Apps/seedhub-rcon
docker compose config --quiet
docker compose build --pull rcon
```

Generate the key once, using the same host directory configured in RCON_KEY_DIR.
This example uses the default directory from the setup above:

```sh
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --user "$(id -u):$(id -g)" --mount "type=bind,src=$HOME/.config/seedhub-rcon,dst=/run/seedhub-rcon" seedhub-rcon:local keygen --key-file /run/seedhub-rcon/encryption.key
```

The command creates an owner-only key and refuses to overwrite an existing file.
It does not need Discord credentials or network access. This one-time container
can write the key directory; the running application mounts it read-only.
Keep a protected backup of the key separately from database backups.
A lost key cannot be replaced to recover existing encrypted passwords.

## Check and start

```sh
docker compose run --rm --no-deps rcon check
docker compose up -d --wait rcon
docker compose ps
```

check creates a missing database and verifies its encryption key without
contacting Discord or game servers. An existing database with the wrong key
fails closed. Do not run check or another app instance while the service is running.

The container uses a non-root user, a read-only filesystem, restricted process
permissions, bounded logs and memory, and persistent data outside the image.
The health check only calls /healthz; it never queries a game server.

This Ubuntu configuration uses Linux host networking, which shares the VPS
network with the container. The app still binds only to 127.0.0.1 and has no
public port mapping. Run only one instance per database and local port.
Container networking is not isolated from the host in this mode; the app's
outbound destination validation remains required.

## Cloudflare Tunnel

The supplied configuration works with your existing Tunnel connector on the VPS,
either running directly on the host or in a container using host networking.

For a dashboard-managed Tunnel, add a published application:

- Hostname: the domain in SEEDHUB_RCON_PUBLIC_URL.
- Service: HTTP at 127.0.0.1:8080.
- HTTP Host Header: that domain, without a scheme.

For a locally managed Tunnel, adapt
[deploy/cloudflared.example.yml](../deploy/cloudflared.example.yml) in the
connector's protected configuration. Keep credentials outside this checkout and
retain the final http_status:404 catch-all.

A Tunnel container on a separate bridge network cannot reach this app using its
own 127.0.0.1. Use host networking for the connector on this Linux VPS too;
do not change the app to listen publicly as a workaround.

Keep the app port closed to public traffic and bypass Cloudflare caching for this
hostname. The app sends Cache-Control: no-store; do not override it with Cache
Everything. Do not retain OAuth callback query strings in proxy access logs.
Optional Cloudflare Access requires additional machine authentication for API
clients as well as their per-server read keys.

```sh
curl --fail https://rcon-test.seedhub.gg/healthz
```

For a local check before Tunnel routing, use the configured domain in the header:

```sh
curl --fail -H 'Host: rcon-test.seedhub.gg' http://127.0.0.1:8080/healthz
```

## Test acceptance

These checks remain pending until performed on the actual test deployment:

1. Confirm Compose builds, starts and reports healthy. Confirm the listener is
   local-only and the HTTPS domain routes through the Tunnel.
2. Sign in with an allowed Discord account; verify another account is rejected.
   Confirm sign-out ends access.
3. Register an authorized server. The UUID is discovered automatically. A wrong
   password or invalid server identity response must fail. Editing a connection
   to point to a different server must fail. Check the saved password remains
   hidden and editing/testing work.
4. Try duplicate registration with the same account and another allowed account.
   Confirm warnings without revealing the original owner's details.
5. Create a server read key. Send it privately in the Authorization header.
   Confirm a wrong key or key for another server fails.
6. Check populated, empty and unavailable servers. Verify timestamps on cached
   lists. Each fresh API/preview lookup reads identity, players and status; cached
   reads contact none. Confirm server name, map, experiences and capacity match
   the game. Verify separate player/status timestamps, server: null on optional
   status failure, and Retry-After behavior while polling around every 30 seconds.
   An ordinary status failure should skip status for five minutes but continue
   fresh roster observations. A genuine upstream rate limit must still delay reads.
7. Revoke/replace a key, disable and delete a disposable registration. Confirm old
   access fails, including after restart.
8. Leave the app idle and confirm it makes no unsolicited game-server requests.
9. Rebuild/recreate the container and confirm registrations persist. Verify backup
   restoration in a separate test directory using its matching encryption key.
10. Check mobile rendering, private notices and the 15-minute recent-login rule.

Complete these checks and establish private support before public signup.

## Updates through Git

Build the new image while the current container runs. If the build fails, stop
and resolve it before touching the running container.

```sh
cd ~/Apps/seedhub-rcon
git pull --ff-only origin main
docker compose config --quiet
docker compose build --pull rcon
docker compose stop rcon
```

Now take a restorable backup as described below. Preserve the previous matching
image/source version for rollback. Then:

```sh
docker compose run --rm --no-deps rcon check
docker compose up -d --wait rcon
docker compose ps
```

If check fails, do not start the new service. Resolve configuration or restore the
previous compatible image. Review migration notes before updates; code rollback
must remain compatible with the database. Never restore an old database silently
and discard newer registrations. Git pulls and image rebuilds do not replace
.env, data, or the external key directory.

## Backup and restore

Stop the service with docker compose stop rcon and verify it has stopped.
Copy data/seedhub-rcon.sqlite3 and any -wal, -shm, and -journal companions into a
new protected backup directory outside the checkout. Keep an encrypted backup
of .env and the key separately from database backups.

Test restoring into a separate empty directory first, with matching source,
dependencies, encryption key and file ownership. Do not point a test restoration
at live data or reuse an occupied local listener port. Run check before starting.
Never silently regenerate a key, delete data, or run docker compose down -v to
fix startup. Define backup retention before accepting important credentials.

## Encryption key rotation

Stop the service and make a restorable backup with its current key. Create a new
key without overwriting the old one:

```sh
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --user "$(id -u):$(id -g)" --mount "type=bind,src=$HOME/.config/seedhub-rcon,dst=/run/seedhub-rcon" seedhub-rcon:local keygen --key-file /run/seedhub-rcon/encryption-next.key
docker compose run --rm --no-deps rcon rotate-key --key-file /run/seedhub-rcon/encryption-next.key
```

Use your configured RCON_KEY_DIR as the host source if different from the example.
After successful rotation, change SEEDHUB_RCON_KEY_FILE in .env to
/run/seedhub-rcon/encryption-next.key, run check, and recreate with
docker compose up -d --wait rcon. If rotation fails, it rolls back; keep the old
configuration. Preserve the old key for old backups. This rotates storage
encryption, not RCON passwords or API keys.

## Duplicate disputes

There is no automatic ownership transfer or password-reveal feature.
The existing owner can delete a registration after privately confirming a
transfer, allowing the new owner to register. If they cannot sign in, handle
the dispute privately with the operator; do not overwrite records based only
on a typed UUID or screenshot. Operator-assisted recovery requires separate
verified authorization and a stopped-service backup and is not exposed by this version.

## References

- [Docker Compose service settings](https://docs.docker.com/reference/compose-file/services/)
- [Docker host networking](https://docs.docker.com/engine/network/drivers/host/)
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/)
- [Discord OAuth2](https://docs.discord.com/developers/topics/oauth2)
