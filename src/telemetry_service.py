"""
GökKurt — Sistem Telemetri Servisi
Şartname §6: "batarya yüzdesi, link kalitesi (RSSI), CPU/GPU sıcaklığı, GPU
kullanım oranı" gibi metrikler UI sağ alt köşede gösterilir.

Bu prototipte Jetson yerine Pi 5 üzerinde çalışılıyor:
  - CPU sıcaklık → /sys/class/thermal/thermal_zone0/temp
  - CPU yük     → psutil
  - RAM         → psutil
  - Disk        → psutil
  - Uptime      → time.monotonic()
  - Net (RSSI)  → iwconfig parse (varsa)
  - Batarya     → mock (Pi'de batarya sensörü yok)
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import psutil  # type: ignore[import]
    _HAS_PSUTIL = True
except Exception:
    psutil = None
    _HAS_PSUTIL = False
    logger.warning("psutil yüklü değil — sistem telemetri sınırlı çalışacak.")


_BOOT = time.monotonic()


def _read_cpu_temp_c() -> Optional[float]:
    """Pi/Linux thermal zone'undan CPU sıcaklığı."""
    paths = [
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/devices/virtual/thermal/thermal_zone0/temp",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    return int(f.read().strip()) / 1000.0
            except Exception:
                continue
    # macOS fallback
    try:
        out = subprocess.run(["powermetrics", "-n", "1"], timeout=1.5,
                             capture_output=True, text=True)
        m = re.search(r"CPU die temperature:\s+([\d.]+)", out.stdout)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None


def _read_wifi_rssi() -> Optional[int]:
    """iwconfig çıktısından dBm değerini parse eder (Linux)."""
    if not shutil.which("iwconfig"):
        return None
    try:
        out = subprocess.run(["iwconfig"], capture_output=True, text=True, timeout=1.0)
        m = re.search(r"Signal level=(-?\d+)\s*dBm", out.stdout)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def _read_throttling() -> Optional[dict]:
    """vcgencmd get_throttled — Pi'de termal/voltaj uyarısı."""
    if not shutil.which("vcgencmd"):
        return None
    try:
        out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True,
                             text=True, timeout=1.0)
        m = re.search(r"throttled=0x([0-9a-fA-F]+)", out.stdout)
        if not m:
            return None
        v = int(m.group(1), 16)
        return {
            "raw": f"0x{v:x}",
            "under_voltage_now":   bool(v & 0x1),
            "freq_capped_now":     bool(v & 0x2),
            "throttled_now":       bool(v & 0x4),
            "soft_temp_limit_now": bool(v & 0x8),
            "any_event":           bool(v & 0xFFFF0000),
        }
    except Exception:
        return None


class TelemetryService:
    """Anlık sistem telemetrisini toplar."""

    def __init__(self) -> None:
        self._mock_battery = 100.0
        self._mock_battery_drain_per_sec = 0.05  # ~33dk

    def snapshot(self) -> dict:
        now = time.monotonic()
        uptime_s = now - _BOOT

        cpu_pct = psutil.cpu_percent(interval=None) if _HAS_PSUTIL else None
        ram = psutil.virtual_memory() if _HAS_PSUTIL else None
        disk = psutil.disk_usage("/") if _HAS_PSUTIL else None
        load = os.getloadavg() if hasattr(os, "getloadavg") else (None, None, None)

        cpu_temp = _read_cpu_temp_c()
        rssi = _read_wifi_rssi()
        throttling = _read_throttling()

        # Mock batarya — yavaşça düşer
        self._mock_battery = max(0.0, self._mock_battery - self._mock_battery_drain_per_sec * 0.1)

        return {
            "uptime_s":     round(uptime_s, 1),
            "cpu_pct":      round(cpu_pct, 1) if cpu_pct is not None else None,
            "cpu_temp_c":   round(cpu_temp, 1) if cpu_temp is not None else None,
            "load_1":       round(load[0], 2) if load[0] is not None else None,
            "load_5":       round(load[1], 2) if load[1] is not None else None,
            "ram_used_mb":  round(ram.used / 1024 / 1024) if ram else None,
            "ram_total_mb": round(ram.total / 1024 / 1024) if ram else None,
            "ram_pct":      round(ram.percent, 1) if ram else None,
            "disk_pct":     round(disk.percent, 1) if disk else None,
            "wifi_rssi":    rssi,
            "throttling":   throttling,
            "battery_pct":  round(self._mock_battery, 1),  # mock
            "platform":     "Raspberry Pi 5" if os.path.exists("/sys/firmware/devicetree/base/model") else "Mac/Dev",
        }
