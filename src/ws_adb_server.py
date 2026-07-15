#!/usr/bin/env python3
"""WebSocket ADB server.

Exposes the Android Debug Bridge over WebSocket so remote clients can drive
devices through a single, firewall-friendly port.

Endpoints
---------
* ``ws://host:8765/ws``                       transparent ADB tunnel
* ``GET /api/devices``                        list registered devices (JSON)
* ``GET /api/connect?serial=...``             ``adb connect`` a TCP device
* ``GET /healthz``                            liveness probe

Auth: pass ``?token=<TOKEN>`` or a signed ``?sig=<timestamp>.<hmac>`` query
parameter. Open mode when no tokens/secret are configured.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
from typing import Optional

import websockets

from auth import TokenAuth
from device_registry import DeviceRegistry
from tunnel import AdbTunnel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("adb_proxy.server")

ADB_HOST = os.environ.get("ADB_HOST", "127.0.0.1")
ADB_PORT = int(os.environ.get("ADB_PORT", "5037"))
WS_PORT = int(os.environ.get("WS_PORT", "8765"))
ADB_BIN = os.environ.get("ADB_BIN", "adb")

auth = TokenAuth()
registry = DeviceRegistry()
tunnel = AdbTunnel(ADB_HOST, ADB_PORT)


def _query_params(websocket) -> dict:
    path = getattr(websocket, "request", None)
    raw = getattr(path, "path", "") if path else ""
    if not raw and hasattr(websocket, "path"):
        raw = websocket.path
    parsed = urllib.parse.urlparse(raw or "/")
    return dict(urllib.parse.parse_qsl(parsed.query))


def _authorized(websocket) -> bool:
    params = _query_params(websocket)
    token = params.get("token")
    sig = params.get("sig")
    return auth.authorize(token=token, path=websocket.path if hasattr(websocket, "path") else "/", signature=sig)


async def ws_handler(websocket, path: Optional[str] = None) -> None:
    if not _authorized(websocket):
        await websocket.close(code=4401, reason="unauthorized")
        return
    log.info("tunnel opened from %s", getattr(websocket, "remote_address", "?"))
    await tunnel.proxy(websocket)
    log.info("tunnel closed")


async def process_request(connection, request) -> Optional[tuple]:
    """Serve plain HTTP endpoints (device list, health, connect)."""
    parsed = urllib.parse.urlparse(request.path)
    path = parsed.path
    params = dict(urllib.parse.parse_qsl(parsed.query))

    if path == "/healthz":
        return (200, {"Content-Type": "text/plain"}, b"ok")

    if path == "/api/devices":
        devices = registry.refresh_from_adb(ADB_BIN)
        body = json.dumps([d.to_dict() for d in devices]).encode()
        return (200, {"Content-Type": "application/json"}, body)

    if path == "/api/connect":
        serial = params.get("serial")
        if not serial:
            return (400, {"Content-Type": "application/json"},
                    json.dumps({"error": "serial required"}).encode())
        proc = await asyncio.create_subprocess_exec(
            ADB_BIN, "connect", serial,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        registry.register(serial, status="connecting")
        body = json.dumps({"serial": serial, "output": (out + err).decode().strip()}).encode()
        return (200, {"Content-Type": "application/json"}, body)

    if path == "/":
        html = b"<html><body><h1>adb-websocket-proxy</h1><p>WS endpoint: /ws</p></body></html>"
        return (200, {"Content-Type": "text/html"}, html)

    return None


async def main() -> None:
    log.info("starting adb-websocket-proxy on :%d (adb %s:%d)", WS_PORT, ADB_HOST, ADB_PORT)
    async with websockets.serve(
        ws_handler, "0.0.0.0", WS_PORT, process_request=process_request
    ):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("shutdown")
