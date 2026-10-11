import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
import sqlite3
import time
import uuid
import weakref

from .errors import Problem
from .rcon import rcon_address
from .security import context, digest, equal, token


def stamp(at=None):
    return datetime.fromtimestamp(time.time() if at is None else at, timezone.utc).isoformat().replace("+00:00", "Z")


class Service:
    def __init__(self, db, transport):
        self.db, self.transport = db, transport
        self.cache = OrderedDict()
        self.locks = weakref.WeakValueDictionary()

    def lock(self, cid):
        return self.locks.setdefault(cid, asyncio.Lock())

    def invalidate(self, cid):
        self.cache.pop(cid, None)

    def authorize(self, raw, sid):
        if not isinstance(raw, str) or len(raw) < 40 or len(raw) > 128:
            raise Problem(401, "unauthorized", "A valid server API key is required.")
        row = self.db.one("SELECT * FROM connections WHERE key_hash=?", digest(raw))
        if not row or not equal(row["key_hash"], digest(raw)):
            raise Problem(401, "unauthorized", "A valid server API key is required.")
        if row["server_uuid"] != sid:
            raise Problem(404, "server_not_found", "Server not found.")
        if not row["enabled"]:
            raise Problem(403, "access_denied", "This connection is disabled.")
        return row

    def connection_input(self, form):
        label = str(form.get("label", "")).strip()
        if not 1 <= len(label) <= 80:
            raise Problem(400, "invalid_request", "Give the connection a name of 1 to 80 characters.")
        host, port = rcon_address(str(form.get("address", "")))
        if port not in self.transport.settings.ports:
            raise Problem(400, "invalid_destination", "This port is not approved by the operator.")
        return label, host, port

    def setup_limit(self, owner, host, port):
        self.db.limit("setup-owner:" + owner, 6, 60)
        self.db.limit(f"setup-destination:{host}:{port}", 3, 60)

    async def save(self, owner, form, guard, cid=None):
        label, host, port = self.connection_input(form)
        old = self.db.owned(cid, owner) if cid else None
        password = str(form.get("password", ""))
        if old and not password:
            password = self.db.password(old)
        self.setup_limit(owner, host, port)
        if old:
            sid = old["server_uuid"]
            await self.transport.read(host, port, password, sid)
        else:
            sid = await self.transport.discover(host, port, password)
        guard()  # logout/session expiry during the network wait must cancel the write
        now = time.time()
        with self.db.conn:
            if old:
                current = self.db.owned(cid, owner)
                if current["revision"] != old["revision"]:
                    raise Problem(409, "connection_changed", "The connection changed. Reload and try again.")
                sealed = self.db.vault.seal(password, context(old))
                self.db.conn.execute("""UPDATE connections SET label=?,host=?,port=?,secret=?,
                    revision=revision+1,updated_at=?,checked_at=?,check_status='Connected',
                    next_read=0,failures=0 WHERE id=?""",
                    (label, host, port, sealed, now, now, cid))
                self.db.audit(owner, "connection_updated", cid)
            else:
                existing = self.db.one("SELECT owner FROM connections WHERE server_uuid=?", sid)
                if existing:
                    if existing["owner"] == owner:
                        message = "You already registered this server. Open its existing connection to edit it."
                    else:
                        message = ("This server is already registered. Contact the server owner. "
                                   "If you own the server and need help, contact this service's support.")
                    raise Problem(409, "server_already_registered", message)
                cid = str(uuid.uuid4())
                row = {"id": cid, "owner": owner, "server_uuid": sid}
                sealed = self.db.vault.seal(password, context(row))
                try:
                    self.db.conn.execute("""INSERT INTO connections
                        (id,owner,server_uuid,label,host,port,secret,created_at,updated_at,checked_at,check_status)
                        VALUES (?,?,?,?,?,?,?,?,?,?,'Connected')""",
                        (cid, owner, sid, label, host, port, sealed, now, now, now))
                except sqlite3.IntegrityError:
                    raise Problem(409, "server_already_registered", "This server is already registered.") from None
                self.db.audit(owner, "connection_created", cid)
        self.invalidate(cid)
        return cid

    def change(self, owner, cid, action):
        row = self.db.owned(cid, owner)
        raw = None
        with self.db.conn:
            if action == "key":
                raw = token()
                self.db.conn.execute("UPDATE connections SET key_hash=?,revision=revision+1 WHERE id=?",
                                     (digest(raw), cid))
            elif action == "revoke":
                self.db.conn.execute("UPDATE connections SET key_hash=NULL,revision=revision+1 WHERE id=?", (cid,))
            elif action in ("enable", "disable"):
                self.db.conn.execute("UPDATE connections SET enabled=?,revision=revision+1 WHERE id=?",
                                     (int(action == "enable"), cid))
            elif action == "delete":
                self.db.conn.execute("DELETE FROM connections WHERE id=?", (cid,))
            else:
                raise Problem(400, "invalid_request", "Unknown action.")
            self.db.audit(owner, action, cid)
        self.invalidate(cid)
        return raw

    async def test(self, owner, cid, guard):
        self.db.owned(cid, owner)
        self.db.limit("test:" + cid, 1, 30)
        async with self.lock(cid):
            row = self.db.owned(cid, owner)
            self.setup_limit(owner, row["host"], row["port"])
            error = None
            try:
                await self.transport.read(row["host"], row["port"], self.db.password(row), row["server_uuid"])
            except Problem as exc:
                error = exc
            guard()
            current = self.db.owned(cid, owner)
            if current["revision"] != row["revision"]:
                raise Problem(409, "connection_changed", "The connection changed. Reload and try again.")
            with self.db.conn:
                self.db.conn.execute("UPDATE connections SET checked_at=?,check_status=? WHERE id=?",
                                     (time.time(), "Unavailable" if error else "Connected", cid))
                self.db.audit(owner, "connection_test_failed" if error else "connection_tested", cid)
            if error:
                raise error

    async def read(self, raw, sid):
        initial = self.authorize(raw, sid)
        cid = initial["id"]
        self.db.limit("read:" + cid, 60, 60)
        async with self.lock(cid):
            row = self.authorize(raw, sid)
            now = time.time()
            hit = self.cache.get(cid)
            if hit and hit[0] == row["revision"] and now - hit[1] < 30:
                self.cache.move_to_end(cid)
                return dict(hit[2], cached=True, served_at=stamp())
            if row["next_read"] > now:
                raise Problem(429, "rate_limited", "The next check is not due yet.",
                              max(1, int(row["next_read"] - now) + 1))
            with self.db.conn:
                self.db.conn.execute("UPDATE connections SET next_read=? WHERE id=?", (now + 30, cid))
            try:
                data = await self.transport.read(row["host"], row["port"], self.db.password(row), sid)
            except Problem as exc:
                current = self.db.one("SELECT * FROM connections WHERE id=?", cid)
                if current and current["revision"] == row["revision"]:
                    delay = max(exc.retry or 0, min(300, 30 * 2 ** min(row["failures"] + 1, 4)))
                    with self.db.conn:
                        self.db.conn.execute("""UPDATE connections SET failures=failures+1,next_read=?,
                            checked_at=?,check_status='Unavailable' WHERE id=?""",
                            (time.time() + delay, time.time(), cid))
                self.authorize(raw, sid)
                if exc.code == "server_mismatch":
                    raise Problem(503, "rcon_unavailable", "The game server identity changed.", 60) from None
                raise
            current = self.authorize(raw, sid)
            if current["revision"] != row["revision"]:
                raise Problem(503, "service_unavailable", "The connection changed during the check.", 30)
            observed = time.time()
            result = {"server_uuid": sid, "observed_at": stamp(observed), "served_at": stamp(),
                      "cached": False, "count": len(data), "players": data}
            with self.db.conn:
                self.db.conn.execute("""UPDATE connections SET failures=0,next_read=?,
                    checked_at=?,check_status='Connected' WHERE id=?""", (observed + 30, observed, cid))
            self.cache[cid] = (row["revision"], observed, result)
            self.cache.move_to_end(cid)
            while len(self.cache) > 256:
                self.cache.popitem(last=False)
            return result
