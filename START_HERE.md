# SeedHUB RCON: start here

**New owner? The full guide is
[HANDOFF_GUIDE.md in seed-hub-bot](https://github.com/Wardogs-Seed-Hub/seed-hub-bot/blob/main/HANDOFF_GUIDE.md).
Read that first.**

## What this is

A small website at **rcon.seedhub.gg** for **game server owners**.

```
Server owner logs in with Discord
   → adds their game server (address + RCON password, stored encrypted)
   → gets a private key for that server
   → gives the key to the SeedHUB bot
Bot uses the key to see who is on the server right now
   → that's how it knows who really helped seed
```

"RCON" is the remote-control connection game servers offer. This service only
**reads** the player list. It can't kick, ban or change anything.

## Do I need it?

It's **optional**. The bot also works with **Warguardian** and **Warcon**, two other
services server owners can use instead. If you don't run this one, owners who used it
just reconnect through one of those.

## What it needs

- Its own small database file (not MySQL) and an **encryption key** file.
  To keep the existing servers connected, get both from the previous owner.
  If either is lost, server owners have to add their servers again.
- Its own **Discord login app**.
- The address **rcon.seedhub.gg** pointed at your server through Cloudflare.

## Working on it with Claude

Open Claude in this folder and start with:

> "Read docs/HANDOFF_TECHNICAL.md and docs/DEPLOYMENT.md first. Then explain this
> service to me in plain English."

When you want a change:

> "I want [your idea]. Propose a plan first and don't change anything until I say OK."
