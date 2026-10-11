"""One explicit SQLite owner. No data is opened by import."""
import sqlite3
import time

from .errors import Problem
from .security import Vault, context, digest, token

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS connections (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, server_uuid TEXT NOT NULL UNIQUE,
 label TEXT NOT NULL, host TEXT NOT NULL, port INTEGER NOT NULL, secret TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 1,
 key_hash TEXT UNIQUE, created_at REAL NOT NULL, updated_at REAL NOT NULL,
 checked_at REAL, check_status TEXT, next_read REAL NOT NULL DEFAULT 0,
 failures INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS owner_connections ON connections(owner);
CREATE TABLE IF NOT EXISTS sessions (
 hash TEXT PRIMARY KEY, owner TEXT NOT NULL, csrf TEXT NOT NULL,
 created_at REAL NOT NULL, expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS oauth (
 state_hash TEXT PRIMARY KEY, browser_hash TEXT NOT NULL, expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_limits (
 id TEXT PRIMARY KEY, count INTEGER NOT NULL, expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, at REAL NOT NULL, actor TEXT NOT NULL,
 action TEXT NOT NULL, connection_id TEXT
);
"""


class Database:
    def __init__(self, path, key):
        self.vault = Vault(key)
        self.conn = sqlite3.connect(str(path), timeout=5)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute("PRAGMA foreign_keys=ON")
            version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported database version; refusing to open.")
            self.conn.executescript(SCHEMA)
            saved = self.one("SELECT value FROM meta WHERE name='keycheck'")
            if saved:
                if self.vault.open(saved["value"], "seedhub:keycheck:v1") != "seedhub-rcon":
                    raise ValueError("Wrong encryption key.")
            else:
                if self.one("SELECT id FROM connections LIMIT 1"):
                    raise ValueError("Database key check is missing; refusing to reset it.")
                with self.conn:
                    self.conn.execute("INSERT INTO meta VALUES ('keycheck',?)",
                                      (self.vault.seal("seedhub-rcon", "seedhub:keycheck:v1"),))
            self.conn.execute("PRAGMA user_version=1")
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=FULL")
        except Exception:
            self.conn.close()
            raise

    def close(self):
        self.conn.close()

    def one(self, sql, *args):
        row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def all(self, sql, *args):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def audit(self, actor, action, cid=None):
        self.conn.execute("INSERT INTO audit(at,actor,action,connection_id) VALUES (?,?,?,?)",
                          (time.time(), actor, action, cid))

    def cleanup(self):
        now = time.time()
        with self.conn:
            for table in ("sessions", "oauth", "rate_limits"):
                self.conn.execute(f"DELETE FROM {table} WHERE expires<=?", (now,))
            self.conn.execute("DELETE FROM audit WHERE at<?", (now - 90*86400,))

    def limit(self, bucket, maximum, seconds):
        now = time.time()
        key = digest(bucket)
        with self.conn:
            row = self.one("SELECT * FROM rate_limits WHERE id=?", key)
            if row and row["expires"] > now:
                if row["count"] >= maximum:
                    raise Problem(429, "rate_limited", "Please wait before trying again.",
                                  max(1, int(row["expires"] - now) + 1))
                self.conn.execute("UPDATE rate_limits SET count=count+1 WHERE id=?", (key,))
            else:
                self.conn.execute("INSERT OR REPLACE INTO rate_limits VALUES (?,?,?)",
                                  (key, 1, now + seconds))

    def new_session(self, owner):
        raw, csrf = token(), token()
        now = time.time()
        with self.conn:
            self.conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?)",
                              (digest(raw), owner, csrf, now, now + 4*3600))
        return raw

    def session(self, raw):
        if not raw or len(raw) > 128:
            return None
        return self.one("SELECT * FROM sessions WHERE hash=? AND expires>?", digest(raw), time.time())

    def owned(self, cid, owner):
        row = self.one("SELECT * FROM connections WHERE id=? AND owner=?", cid, owner)
        if not row:
            raise Problem(404, "not_found", "Connection not found.")
        return row

    def password(self, row):
        return self.vault.open(row["secret"], context(row))
