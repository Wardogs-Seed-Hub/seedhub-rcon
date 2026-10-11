"""Explicit configuration loading; never read secrets during import."""
import base64
import ipaddress
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    public_url: str
    database: Path
    key: bytes
    client_id: str
    client_secret: str
    allowed_users: frozenset[str]
    bind_port: int = 8080
    timeout: int = 10
    support_url: str = ""

    @property
    def callback(self):
        return self.public_url + "/auth/discord/callback"


def public_origin(value):
    p = urlsplit(value)
    if (p.scheme != "https" or not p.hostname or p.username or p.password
            or p.query or p.fragment or p.path not in ("", "/") or p.port not in (None, 443)):
        raise ValueError("PUBLIC_URL must be an HTTPS domain with no path or credentials.")
    try:
        ipaddress.ip_address(p.hostname)
    except ValueError:
        if not re.fullmatch(r"[a-zA-Z0-9.-]+", p.hostname) or "." not in p.hostname:
            raise ValueError("PUBLIC_URL must use a domain.")
    else:
        raise ValueError("PUBLIC_URL must use a domain.")
    return "https://" + p.hostname.lower()


def load_settings(env_file=".env"):
    load_dotenv(env_file, override=False)
    def get(name):
        value = os.environ.get("SEEDHUB_RCON_" + name, "").strip()
        if not value or value.startswith("REPLACE_"):
            raise ValueError("Configure SEEDHUB_RCON_" + name + ".")
        return value
    origin = public_origin(get("PUBLIC_URL"))
    key_path = Path(get("KEY_FILE")).expanduser()
    if os.name != "nt" and key_path.stat().st_mode & 0o077:
        raise ValueError("Encryption key permissions must be owner-only (chmod 600).")
    key = base64.b64decode(key_path.read_bytes().strip(), validate=True)
    if len(key) != 32:
        raise ValueError("Encryption key must contain 32 random bytes in base64.")
    client_id = get("DISCORD_CLIENT_ID")
    if not re.fullmatch(r"[0-9]{17,20}", client_id):
        raise ValueError("Discord client ID must be a Discord application ID.")
    users = frozenset(x.strip() for x in get("ALLOWED_DISCORD_IDS").split(","))
    if users != {"*"} and not all(re.fullmatch(r"[0-9]{17,20}", x) for x in users):
        raise ValueError("ALLOWED_DISCORD_IDS must list Discord IDs or be *.")
    bind_port = int(os.environ.get("SEEDHUB_RCON_BIND_PORT", "8080"))
    if not 1024 <= bind_port <= 65535:
        raise ValueError("Invalid local listener port.")
    support = os.environ.get("SEEDHUB_RCON_SUPPORT_URL", "").strip()
    if support and (urlsplit(support).scheme != "https" or not urlsplit(support).hostname
                    or urlsplit(support).username or urlsplit(support).password):
        raise ValueError("SUPPORT_URL must be an HTTPS link.")
    return Settings(origin, Path(get("DB_PATH")).expanduser(), key, client_id,
                    get("DISCORD_CLIENT_SECRET"), users, bind_port, 10, support)
