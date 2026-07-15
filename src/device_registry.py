"""Device registry for adb-websocket-proxy.

Tracks which Android devices are reachable and (optionally) online. Keeps a
hand-authored allow-list in JSON and can merge in the live output of
``adb devices -l``.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class DeviceInfo:
    serial: str
    model: str = ""
    status: str = "offline"      # offline | device | unauthorized
    owner: str = ""
    last_seen: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "DeviceInfo":
        return cls(**data)


class DeviceRegistry:
    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.expanduser("~/.adb-proxy/devices.json")
        self._devices: Dict[str, DeviceInfo] = {}
        self.load()

    def load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                self._devices = {
                    d["serial"]: DeviceInfo.from_dict(d) for d in raw.get("devices", [])
                }
            except (json.JSONDecodeError, KeyError):
                self._devices = {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(
                {"devices": [d.to_dict() for d in self._devices.values()]},
                fh,
                indent=2,
            )

    def register(self, serial: str, **meta) -> DeviceInfo:
        existing = self._devices.get(serial)
        if existing:
            for k, v in meta.items():
                setattr(existing, k, v)
            info = existing
        else:
            info = DeviceInfo(serial=serial, **meta)
            self._devices[serial] = info
        self.save()
        return info

    def unregister(self, serial: str) -> None:
        self._devices.pop(serial, None)
        self.save()

    def get(self, serial: str) -> Optional[DeviceInfo]:
        return self._devices.get(serial)

    def all(self) -> List[DeviceInfo]:
        return list(self._devices.values())

    def refresh_from_adb(self, adb_bin: str = "adb") -> List[DeviceInfo]:
        """Merge live `adb devices -l` output into the registry."""
        try:
            out = subprocess.run(
                [adb_bin, "devices", "-l"], capture_output=True, text=True, check=False
            ).stdout
        except FileNotFoundError:
            return self.all()
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            serial = parts[0]
            status = parts[1] if len(parts) > 1 else "offline"
            meta = {}
            for p in parts[2:]:
                if ":" in p:
                    k, _, v = p.partition(":")
                    meta[k] = v
            self.register(serial, status=status, model=meta.get("model", ""))
        return self.all()
