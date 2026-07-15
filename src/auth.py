"""Authentication for adb-websocket-proxy.

Supports two schemes:

* **Static API tokens** — a list of accepted bearer tokens (good enough for a
  single shared secret between the proxy and trusted clients).
* **HMAC request signing** — clients sign the request path + timestamp with a
  shared secret; the server validates the signature and a short TTL to avoid
  replay.

Both are optional: if no secret/tokens are configured the proxy runs in
open mode (useful for a LAN device lab behind a firewall).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Iterable, Optional


class TokenAuth:
    def __init__(
        self,
        secret: Optional[str] = None,
        tokens: Optional[Iterable[str]] = None,
        ttl: int = 60,
    ):
        self.secret = secret or os.environ.get("ADB_PROXY_SECRET", "")
        self.ttl = ttl
        self.tokens = set(tokens or [])
        env_tokens = os.environ.get("ADB_PROXY_TOKENS")
        if env_tokens:
            self.tokens.update(t.strip() for t in env_tokens.split(",") if t.strip())

    # -- static token scheme -------------------------------------------------
    def add_token(self, token: str) -> None:
        self.tokens.add(token)

    def validate_token(self, token: Optional[str]) -> bool:
        if not self.tokens:
            return True  # open mode
        return token in self.tokens

    # -- HMAC signed-request scheme ------------------------------------------
    def sign(self, path: str, timestamp: Optional[str] = None) -> str:
        if not self.secret:
            raise ValueError("no secret configured")
        timestamp = timestamp or str(int(time.time()))
        payload = f"{path}:{timestamp}".encode()
        digest = hmac.new(self.secret.encode(), payload, hashlib.sha256).hexdigest()
        return f"{timestamp}.{digest}"

    def validate_signature(self, path: str, signed: Optional[str]) -> bool:
        if not self.secret:
            return True  # open mode
        if not signed or "." not in signed:
            return False
        timestamp_str, _, digest = signed.partition(".")
        try:
            ts = int(timestamp_str)
        except ValueError:
            return False
        if abs(time.time() - ts) > self.ttl:
            return False
        expected = hmac.new(
            self.secret.encode(), f"{path}:{timestamp_str}".encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, digest)

    # -- unified entry point -------------------------------------------------
    def authorize(self, token: Optional[str], path: str = "", signature: Optional[str] = None) -> bool:
        return self.validate_token(token) or self.validate_signature(path, signature)
