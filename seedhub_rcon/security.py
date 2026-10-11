import base64
import hashlib
import hmac
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def token():
    return secrets.token_urlsafe(32)


def equal(a, b):
    return hmac.compare_digest(str(a).encode(), str(b).encode())


class Vault:
    def __init__(self, key):
        self.cipher = AESGCM(key)

    def seal(self, value, context):
        nonce = os.urandom(12)
        return base64.b64encode(nonce + self.cipher.encrypt(
            nonce, value.encode("utf-8"), context.encode("utf-8"))).decode("ascii")

    def open(self, value, context):
        raw = base64.b64decode(value, validate=True)
        return self.cipher.decrypt(raw[:12], raw[12:], context.encode("utf-8")).decode("utf-8")


def context(row):
    return f"rcon:v1:{row['id']}:{row['owner']}:{row['server_uuid']}"
