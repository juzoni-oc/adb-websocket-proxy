# adb-websocket-proxy

> **ADB over WebSocket** — expose the Android Debug Bridge through a single,
> firewall-friendly WebSocket port so remote clients can drive devices as if
> they were connected locally.

`adb-websocket-proxy` bridges a WebSocket connection to the local ADB server
(`localhost:5037`). Any ADB client that speaks the ADB protocol can use the
WebSocket tunnel transparently — authentication, device selection and the ADB
handshake all happen over the socket exactly as they would on a normal TCP
connection, only the transport changes.

## Why

- 🌐 Reach devices behind NAT / inside a container from anywhere.
- 🔒 One TLS-terminated port instead of exposing the ADB TCP port.
- 🔑 Optional static-token or HMAC-signed request auth.
- 🧩 A tiny HTTP API to list / connect devices and a `/healthz` probe.

## Architecture

```
  adb client  <--WebSocket-->  adb-websocket-proxy  <--TCP 5037-->  adb server
   (remote)                       (this service)                      (devices)
```

## Quick start

```bash
pip install -r requirements.txt

# open mode (no auth) for a trusted LAN
python -m src.ws_adb_server

# or with auth
export ADB_PROXY_SECRET="$(openssl rand -hex 16)"
python -m src.ws_adb_server
```

With Docker Compose (point it at your host ADB server):

```bash
ADB_HOST=host.docker.internal docker compose up --build
```

## HTTP API

| Method & path                | Description                                   |
|------------------------------|-----------------------------------------------|
| `GET /healthz`               | liveness probe                                |
| `GET /api/devices`           | JSON list of registered/online devices       |
| `GET /api/connect?serial=x`  | `adb connect x` via the proxy                 |

## WebSocket

Connect to `ws://host:8765/ws` (add `?token=...` or `?sig=...` if auth is on)
and speak the ADB protocol directly. Example client snippet:

```python
import asyncio, websockets

async def main():
    async with websockets.connect("ws://localhost:8765/ws") as ws:
        # ADB "host:devices" request (length-prefixed protocol)
        req = b"host:devices"
        await ws.send(len(req).__format__(">04x").encode() + req)
        print(await ws.recv())

asyncio.run(main())
```

## Configuration (environment variables)

| Variable            | Default             | Purpose                          |
|---------------------|---------------------|----------------------------------|
| `WS_PORT`           | `8765`              | Listen port                      |
| `ADB_HOST`          | `127.0.0.1`         | ADB server host                  |
| `ADB_PORT`          | `5037`              | ADB server port                  |
| `ADB_PROXY_SECRET`  | _(empty = open)_    | HMAC signing secret              |
| `ADB_PROXY_TOKENS`  | _(empty = open)_    | Comma-separated static tokens    |

## Project layout

```
adb-websocket-proxy/
├── src/
│   ├── ws_adb_server.py   # WebSocket ADB server
│   ├── device_registry.py # device registration (JSON backed)
│   ├── tunnel.py          # connection tunnel management
│   └── auth.py            # authentication (token + HMAC)
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Contact

Maintained by **juzoni-oc**. Need hosted remote-device access, a managed
device farm, or custom ADB gateway work? Contact **[qtphone.com](https://qtphone.com)**.

## License

MIT
