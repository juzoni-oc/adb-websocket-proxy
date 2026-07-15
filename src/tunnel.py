"""Connection tunnel management for adb-websocket-proxy.

The tunnel bridges a WebSocket connection to a raw TCP socket on the local ADB
server (``localhost:5037`` by default). Bytes received on one side are copied to
the other, so any ADB client that speaks the ADB protocol can drive a device as
if it were connected locally — only the transport is WebSocket instead of TCP.

This is a *transparent* tunnel: authentication, device selection and the ADB
handshake are all performed by the ADB client over the websocket, exactly as
they would be over a normal socket.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Tuple

log = logging.getLogger("adb_proxy.tunnel")


class AdbTunnel:
    def __init__(self, adb_host: str = "127.0.0.1", adb_port: int = 5037):
        self.adb_host = adb_host
        self.adb_port = adb_port

    async def _pump(
        self, reader, writer, label: str, stop: asyncio.Event
    ) -> None:
        try:
            while not stop.is_set():
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError, OSError) as exc:
            log.debug("%s pump ended: %s", label, exc)
        finally:
            stop.set()

    async def proxy(self, websocket) -> None:
        """Relay `websocket` <-> ADB server TCP socket until either side closes."""
        try:
            reader, writer = await asyncio.open_connection(self.adb_host, self.adb_port)
        except OSError as exc:
            log.warning("cannot reach ADB server %s:%s: %s",
                        self.adb_host, self.adb_port, exc)
            await websocket.close(code=1011, reason="adb_unreachable")
            return

        stop = asyncio.Event()
        # WebSocket -> TCP  (client sends ADB protocol frames to us)
        ws_to_tcp = asyncio.create_task(
            self._ws_to_tcp(websocket, writer, stop)
        )
        # TCP -> WebSocket  (ADB server replies)
        tcp_to_ws = asyncio.create_task(
            self._pump(reader, _WsWriter(websocket), "tcp->ws", stop)
        )
        try:
            await asyncio.gather(ws_to_tcp, tcp_to_ws, return_exceptions=True)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _ws_to_tcp(self, websocket, writer, stop: asyncio.Event) -> None:
        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    writer.write(message)
                else:
                    writer.write(message.encode())
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError, OSError) as exc:
            log.debug("ws->tcp ended: %s", exc)
        finally:
            stop.set()


class _WsWriter:
    """Minimal writable object so the TCP pump can send to the websocket."""

    def __init__(self, websocket):
        self._ws = websocket

    async def write(self, data: bytes) -> None:
        await self._ws.send(data)

    async def drain(self) -> None:
        return None
