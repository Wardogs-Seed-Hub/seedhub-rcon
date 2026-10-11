"""Fixed read-only routes, with public destination validation and pinned IPs."""
import asyncio
import ipaddress
import json
import re
import socket
import uuid

import aiohttp
from yarl import URL

from .errors import Problem

MAX_BYTES = 256 * 1024


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
        if path not in ("/v1/server-id", "/v1/players"):
            raise ValueError("Unsupported RCON operation")
        url = URL.build(scheme="http", host=ip, port=port, path=path)
        host_header = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        async with session.get(url, headers={"Host": host_header,
                "Authorization": "Bearer " + password, "Accept": "application/json",
                "Accept-Encoding": "identity"}, allow_redirects=False) as response:
            if response.status == 429:
                try:
                    delay = max(30, min(300, int(response.headers.get("Retry-After", "60"))))
                except ValueError:
                    delay = 60
                raise Problem(503, "rcon_unavailable", "The server asked us to wait.", delay)
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
        host = host_name(host)
        if type(port) is not int or port not in self.settings.ports:
            raise Problem(400, "invalid_destination", "This RCON port is not approved by the operator.")
        if not password or len(password) > 512 or any(ord(c) < 32 or ord(c) > 126 for c in password):
            raise Problem(400, "invalid_request", "Enter a valid RCON password.")
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
                        if actual != expected_uuid:
                            raise Problem(409, "server_mismatch", "The server does not match that UUID / join code.")
                        return players(await self._get(session, ip, host, port, password, "/v1/players"))
        except TimeoutError:
            raise Problem(504, "rcon_timeout", "The game server took too long to respond.", 60) from None
        except (aiohttp.ClientError, OSError):
            raise Problem(503, "rcon_unavailable", "The game server could not be checked.", 60) from None
