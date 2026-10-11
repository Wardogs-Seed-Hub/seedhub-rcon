"""Run one process, bound only to loopback, behind the host's Tunnel."""
import argparse
import base64
import logging
import os
from pathlib import Path
import sys

from aiohttp import web

from .app import create_app
from .config import load_settings
from .database import Database
from .security import Vault, context


class ProcessLock:
    def __init__(self, path):
        self.path, self.file = path, None

    def __enter__(self):
        self.file = open(self.path, "a+b")
        self.file.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                if self.file.read(1) == b"":
                    self.file.write(b"0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self.file.close()
                raise ValueError("Another instance is using this database.") from None
        else:
            import fcntl
            try:
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.file.close()
                raise ValueError("Another instance is using this database.") from None
        return self

    def __exit__(self, *args):
        if self.file:
            self.file.close()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="SeedHub RCON")
    parser.add_argument("command", choices=["serve", "check", "keygen", "rotate-key"])
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--key-file", help="New key file for keygen or rotate-key")
    args = parser.parse_args()
    try:
        if args.command == "keygen":
            if not args.key_file:
                parser.error("keygen requires --key-file")
            path = Path(args.key_file).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(base64.b64encode(os.urandom(32)) + b"\n")
            print("Created a new key file. Keep it private and back it up separately.")
            return
        settings = load_settings(args.env_file)
        settings.database.parent.mkdir(parents=True, exist_ok=True)
        with ProcessLock(str(settings.database) + ".lock"):
            db = Database(settings.database, settings.key)
            try:
                if args.command == "check":
                    print("Configuration and database encryption verified. No network calls made.")
                elif args.command == "rotate-key":
                    if not args.key_file:
                        parser.error("rotate-key requires --key-file")
                    new = base64.b64decode(Path(args.key_file).expanduser().read_bytes().strip(), validate=True)
                    if len(new) != 32:
                        raise ValueError("New key must contain 32 random bytes.")
                    vault = Vault(new)
                    with db.conn:
                        for row in db.all("SELECT * FROM connections"):
                            db.conn.execute("UPDATE connections SET secret=? WHERE id=?",
                                            (vault.seal(db.password(row), context(row)), row["id"]))
                        db.conn.execute("UPDATE meta SET value=? WHERE name='keycheck'",
                                        (vault.seal("seedhub-rcon", "seedhub:keycheck:v1"),))
                        db.audit("operator", "encryption_key_rotated")
                    print("Database re-encrypted. Update KEY_FILE before restarting. Preserve the old key for old backups.")
                else:
                    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
                    # Access logs include OAuth query strings, so they must be disabled.
                    web.run_app(create_app(settings, db), host="127.0.0.1", port=settings.bind_port,
                                access_log=None, print=None, shutdown_timeout=15)
            finally:
                db.close()
    except Exception:
        print("Startup failed. Check configuration, key file, database permissions, and whether another instance is running. Details suppressed to protect secrets.", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
