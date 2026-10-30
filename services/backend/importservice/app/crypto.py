"""Authenticated archives and domain-separated pipeline messages."""

import base64
import hashlib
import hmac
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


class ArchiveCipher:
    def __init__(self, settings):
        self.current = settings.archive_key_id
        self.keys = {
            key_id: settings.decode_key(value) for key_id, value in json.loads(settings.archive_old_keys_json).items()
        }
        self.keys[self.current] = settings.decode_key(settings.archive_key_b64)

    def seal(self, data, context, key_id=None):
        key_id = key_id or self.current
        nonce = os.urandom(12)
        return key_id, nonce + AESGCM(self.keys[key_id]).encrypt(nonce, data, context.encode())

    def open(self, key_id, value, context):
        return AESGCM(self.keys[key_id]).decrypt(bytes(value[:12]), bytes(value[12:]), context.encode())


def sign(body, key, kind):
    payload = base64.b64encode(canonical(body)).decode()
    signature = hmac.new(key, (kind + "." + payload).encode(), hashlib.sha256).hexdigest()
    return canonical({"kind": kind, "payload": payload, "signature": signature})


def verify(wire, key, kind, max_bytes=2_000_000):
    if len(wire) > max_bytes:
        raise ValueError("Pipeline message is too large")
    envelope = json.loads(wire)
    payload = envelope["payload"]
    expected = hmac.new(key, (kind + "." + payload).encode(), hashlib.sha256).hexdigest()
    if envelope["kind"] != kind or not hmac.compare_digest(expected, envelope["signature"]):
        raise ValueError("Invalid pipeline signature")
    return json.loads(base64.b64decode(payload, validate=True))
