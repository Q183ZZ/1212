"""Bluetooth speaker control for Yaobao.

Uses Linux BlueZ via bluetoothctl. No phone app is required.
The exact adapter is intentionally discovered by BlueZ so this works with
board-integrated Bluetooth or a USB Bluetooth adapter.
"""
from __future__ import annotations

import subprocess
from typing import Optional


class BluetoothSpeaker:
    def __init__(self, device_name: str = "耀宝"):
        self.device_name = device_name

    def _run(self, *args: str, timeout: float = 8.0) -> tuple[bool, str]:
        try:
            p = subprocess.run(
                ["bluetoothctl", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            out = (p.stdout or "") + (p.stderr or "")
            return p.returncode == 0, out.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)

    def power_on(self) -> bool:
        ok, _ = self._run("power", "on")
        return ok

    def make_discoverable(self, seconds: int = 120) -> bool:
        ok1, _ = self._run("pairable", "on")
        ok2, _ = self._run("discoverable", "on")
        # bluetoothctl's discoverable timeout handling varies by distro;
        # the caller can turn discoverability off after the desired window.
        return ok1 and ok2

    def discoverable_off(self) -> bool:
        ok, _ = self._run("discoverable", "off")
        return ok

    def list_devices(self) -> str:
        _, out = self._run("devices")
        return out

    def pair(self, mac: str) -> tuple[bool, str]:
        return self._run("pair", mac, timeout=30)

    def trust(self, mac: str) -> tuple[bool, str]:
        return self._run("trust", mac)

    def connect(self, mac: str) -> tuple[bool, str]:
        return self._run("connect", mac, timeout=30)

    def disconnect(self, mac: str) -> tuple[bool, str]:
        return self._run("disconnect", mac)

    def status(self) -> dict:
        ok, out = self._run("show")
        powered = "Powered: yes" in out
        discoverable = "Discoverable: yes" in out
        return {
            "available": ok,
            "powered": powered,
            "discoverable": discoverable,
            "name": self.device_name,
        }
