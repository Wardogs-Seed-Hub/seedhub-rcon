"""Fixed read-only routes, with public destination validation and pinned IPs."""
import asyncio
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import ipaddress
import json
import math
import re
import socket
import time
import uuid
from urllib.parse import parse_qsl, unquote, urlsplit

import aiohttp
from yarl import URL

from .errors import Problem

MAX_BYTES = 256 * 1024

# Exact IDs observed in the game's experience catalog. The catalog describes
# available choices; only /v1/status supplies the active experiences for a read.
BASE_EXPERIENCES = frozenset({"Madrid_KOTH_01", "Bakurani_KOTH_01", "Detroit_KOTH_01"})
MOD_EXPERIENCES = {"KOTH_InfantryOnly": "Infantry Only", "KOTH_Hardcore": "Hardcore"}


@dataclass
class Snapshot:
    players: list
    observed_at: float
    server: dict | None = None
    status_observed_at: float | None = None
    metadata_retry: int | None = None
    upstream_retry: int | None = None
    banner_url: str | None = None
    sponsor_checked: bool = False


def server_uuid(value):
    try:
        return str(uuid.UUID(str(value).strip()))
    except (ValueError, AttributeError):
        raise Problem(400, "invalid_request", "Enter a valid server UUID / join code.") from None


def host_name(value):
    value = value.strip()
    if not value or len(value) > 253 or any(c in value for c in "/@?#%\\"):
        raise Problem(400, "invalid_destination", "Enter a hostname or IP without a URL or path.")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        try:
            ascii_host = value.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise Problem(400, "invalid_destination", "Invalid hostname.") from None
        if not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", ascii_host):
            raise Problem(400, "invalid_destination", "Enter a public hostname or IP.")
        return ascii_host


def rcon_address(value):
    value = value.strip()
    match = re.fullmatch(r"(?:\[([^\[\]]+)\]|([^:\[\]]+)):([0-9]{1,5})", value)
    if not match:
        raise Problem(400, "invalid_destination", "Enter the RCON address as IP:port or hostname:port.")
    bracketed, hostname, port_text = match.groups()
    if bracketed:
        try:
            host = str(ipaddress.IPv6Address(bracketed))
        except ValueError:
            raise Problem(400, "invalid_destination", "Enter IPv6 addresses as [IPv6]:port.") from None
    else:
        host = hostname
    host = host_name(host)
    port = int(port_text)
    if not 1 <= port <= 65535:
        raise Problem(400, "invalid_request", "Enter a valid RCON port from 1 to 65535.")
    return host, port


def public_ip(value):
    ip = ipaddress.ip_address(value)
    if (not ip.is_global or ip.is_multicast or ip.is_reserved
            or (ip.version == 6 and (ip.ipv4_mapped or ip.sixtofour or ip.teredo))):
        raise Problem(400, "invalid_destination", "Private or special network addresses are not allowed.")
    return str(ip)


def players(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("players"), list):
        raise Problem(502, "invalid_rcon_response", "The server returned an invalid player list.")
    data = payload["players"]
    if len(data) > 512 or type(payload.get("count")) is not int or payload["count"] != len(data):
        raise Problem(502, "invalid_rcon_response", "The server returned an invalid player count.")
    result, seen = [], set()
    for p in data:
        if (not isinstance(p, dict) or not isinstance(p.get("steamId"), str)
                or not re.fullmatch(r"[0-9]{17}", p["steamId"])
                or not isinstance(p.get("name"), str) or len(p["name"]) > 256
                or p["steamId"] in seen):
            raise Problem(502, "invalid_rcon_response", "The server returned invalid player details.")
        seen.add(p["steamId"])
        result.append({"steam_id": p["steamId"], "name": p["name"]})
    return result


def experience_labels(experiences):
    """Label known active IDs without treating unknown values as no modifiers."""
    bases = BASE_EXPERIENCES.intersection(experiences)
    mode = "King of the Hill" if len(bases) == 1 else None
    understood = all(value in BASE_EXPERIENCES or value in MOD_EXPERIENCES
                     for value in experiences)
    mods = (list(dict.fromkeys(MOD_EXPERIENCES[value] for value in experiences
                              if value in MOD_EXPERIENCES))
            if mode is not None and understood else None)
    return mode, mods


def server_info(payload):
    """Select only the documented display fields; never forward raw status."""
    def text(value):
        return (isinstance(value, str) and 1 <= len(value) <= 256
                and bool(value.strip()) and not any(ord(c) < 32 or ord(c) == 127 for c in value))

    if not isinstance(payload, dict):
        raise Problem(502, "invalid_rcon_response", "The server returned invalid status details.")
    population = payload.get("players")
    experiences = payload.get("experiences")
    if (not text(payload.get("serverName")) or not text(payload.get("map"))
            or not isinstance(population, dict) or type(population.get("max")) is not int
            or not 1 <= population["max"] <= 512
            or not isinstance(experiences, list) or len(experiences) > 32
            or not all(text(value) for value in experiences)):
        raise Problem(502, "invalid_rcon_response", "The server returned invalid status details.")
    mode, mods = experience_labels(experiences)
    return {"name": payload["serverName"], "map": payload["map"],
            "experiences": list(experiences), "mode": mode, "mods": mods,
            "max_players": population["max"]}


def banner_url(payload, password):
    """Select only a public HTTPS image URL; never resolve or fetch that URL."""
    value = payload.get("imageUrl") if isinstance(payload, dict) else None
    if (not isinstance(value, str) or not 1 <= len(value) <= 2048
            or any(ord(c) < 33 or ord(c) > 126 for c in value)
            or any(c in value for c in '\\<>"`{}|^')
            or re.search(r'%(?![0-9a-fA-F]{2})', value)):
        return None
    try:
        url = urlsplit(value)
        if (url.scheme != "https" or not url.hostname or url.username is not None
                or url.password is not None or url.fragment or url.path in ("", "/")
                or (url.port is not None and not 1 <= url.port <= 65535) or '%' in url.netloc):
            return None
        host = host_name(url.hostname)
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if (host.split('.')[-1].isdigit()
                    or host.endswith(('.localhost', '.local', '.internal', '.lan', '.home', '.onion', '.test', '.invalid'))):
                return None
        else:
            public_ip(host)
        decoded = unquote(value)
        if (password in decoded or any(ord(c) < 32 or ord(c) == 127 for c in decoded)
                or any(re.search(r'key|token|secret|password|credential|signature|authorization', key, re.I)
                       for key, _ in parse_qsl(url.query))):
            return None
    except (Problem, ValueError, TypeError, UnicodeError):
        return None
    return value


class Rcon:
    def __init__(self, settings):
        self.settings = settings
        self.slots = asyncio.Semaphore(8)

    async def address(self, host, port):
        try:
            direct = ipaddress.ip_address(host)
        except ValueError:
            addresses = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM)
            valid = [public_ip(a[4][0]) for a in addresses]
            if not valid:
                raise Problem(503, "rcon_unavailable", "The game server could not be checked.")
            return valid[0]
        return public_ip(str(direct))

    async def _get(self, session, ip, host, port, password, path):
        if path not in ("/v1/server-id", "/v1/players", "/v1/status", "/v1/sponsor"):
            raise ValueError("Unsupported RCON operation")
        url = URL.build(scheme="http", host=ip, port=port, path=path)
        host_header = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        async with session.get(url, headers={"Host": host_header,
                "Authorization": "Bearer " + password, "Accept": "application/json",
                "Accept-Encoding": "identity"}, allow_redirects=False) as response:
            if response.status != 200 and (response.status == 429 or "Retry-After" in response.headers):
                raw = response.headers.get("Retry-After", "60")
                try:
                    delay = (int(raw) if re.fullmatch(r"[0-9]{1,10}", raw)
                             else math.ceil(parsedate_to_datetime(raw).timestamp() - time.time()))
                    delay = max(30, delay)
                except (ValueError, TypeError, OverflowError):
                    delay = 60
                raise Problem(503, "rcon_unavailable", "The server asked us to wait.", delay,
                              upstream_retry=True)
            if response.status != 200:
                raise Problem(503, "rcon_unavailable", "The game server could not be checked.", 60)
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise Problem(502, "invalid_rcon_response", "Unsupported server response.")
            buf = bytearray()
            async for chunk in response.content.iter_chunked(16384):
                buf.extend(chunk)
                if len(buf) > MAX_BYTES:
                    raise Problem(502, "invalid_rcon_response", "The server response was too large.")
            try:
                return json.loads(buf)
            except (ValueError, UnicodeError, RecursionError):
                raise Problem(502, "invalid_rcon_response", "The server response was invalid.") from None

    async def read(self, host, port, password, expected_uuid):
        _, data = await self._read(host, port, password, expected_uuid)
        return data.players

    async def collect(self, host, port, password, expected_uuid, *, metadata=True, sponsor=False):
        _, data = await self._read(host, port, password, expected_uuid, metadata=metadata, sponsor=sponsor)
        return data

    async def discover(self, host, port, password):
        identity, _ = await self._read(host, port, password, None)
        return identity

    async def _read(self, host, port, password, expected_uuid, metadata=False, sponsor=False):
        host = host_name(host)
        if type(port) is not int or not 1 <= port <= 65535:
            raise Problem(400, "invalid_destination", "Enter a valid RCON port from 1 to 65535.")
        if not password or len(password) > 512 or any(ord(c) < 32 or ord(c) > 126 for c in password):
            raise Problem(400, "invalid_request", "Enter a valid RCON password.")
        snapshot = None
        try:
            async with asyncio.timeout(self.settings.timeout):
                async with self.slots:
                    ip = await self.address(host, port)
                    # Literal validated address prevents DNS rebinding. No cookies, proxy,
                    # redirects, decompression or reused connections to other destinations.
                    async with aiohttp.ClientSession(
                        trust_env=False, cookie_jar=aiohttp.DummyCookieJar(),
                        auto_decompress=False,
                        connector=aiohttp.TCPConnector(force_close=True),
                        timeout=aiohttp.ClientTimeout(total=self.settings.timeout)) as session:
                        identity = await self._get(session, ip, host, port, password, "/v1/server-id")
                        if not isinstance(identity, dict) or not isinstance(identity.get("serverId"), str):
                            raise Problem(502, "invalid_rcon_response", "Server identity could not be verified.")
                        try:
                            actual = server_uuid(identity["serverId"])
                        except Problem:
                            raise Problem(502, "invalid_rcon_response", "Server identity could not be verified.") from None
                        if expected_uuid is not None and actual != expected_uuid:
                            raise Problem(409, "server_mismatch", "The server does not match that UUID / join code.")
                        roster = players(await self._get(session, ip, host, port, password, "/v1/players"))
                        snapshot = Snapshot(roster, time.time())
                        if metadata:
                            try:
                                info = server_info(await self._get(session, ip, host, port, password, "/v1/status"))
                                snapshot.status_observed_at = time.time()
                                snapshot.server = info
                            except Problem as exc:
                                snapshot.metadata_retry = exc.retry or 30
                                if exc.upstream_retry:
                                    snapshot.upstream_retry = exc.retry
                        if sponsor and snapshot.server is not None and snapshot.upstream_retry is None:
                            snapshot.sponsor_checked = True
                            try:
                                payload = await self._get(session, ip, host, port, password, "/v1/sponsor")
                                snapshot.banner_url = banner_url(payload, password)
                            except Problem as exc:
                                if exc.upstream_retry:
                                    snapshot.upstream_retry = exc.retry
                            except (TimeoutError, aiohttp.ClientError, OSError):
                                pass  # Optional image failures never invalidate status or players.
                        return actual, snapshot
        except TimeoutError:
            if snapshot is not None:
                if not snapshot.sponsor_checked:
                    snapshot.metadata_retry = 60
                return actual, snapshot
            raise Problem(504, "rcon_timeout", "The game server took too long to respond.", 60) from None
        except (aiohttp.ClientError, OSError):
            if snapshot is not None:
                if not snapshot.sponsor_checked:
                    snapshot.metadata_retry = 60
                return actual, snapshot
            raise Problem(503, "rcon_unavailable", "The game server could not be checked.", 60) from None
