"""
GökKurt — Mock Yarışma Sunucusu
KTR §6'da bahsedilen "yarışma sunucusu" davranışını taklit eder.

Endpoint'ler:
  POST /api/kilit_bilgisi      — kilit bildirimi
  POST /api/kamikaze_bilgisi   — kamikaze paketi (QR ile)
  GET  /api/rakip_iha          — rakip İHA listesi (10 Hz polling için)
  GET  /api/hss_verisi         — HSS yasaklı silindirler
  GET  /api/ucus_sinirlari     — geofence

Kullanım:
    python mock_server.py --port 9000

Ana server.py bu adrese istek atar (config.COMP_SERVER_URL).
"""

from __future__ import annotations

import argparse
import logging
import math
import random
import time
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [MOCK] %(message)s")
logger = logging.getLogger("mock")

app = FastAPI(title="GökKurt Mock Yarışma Sunucusu")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

# ── Düzce kampüs merkezli rakip İHA simülasyonu ───────────────────────────────
CENTER_LAT, CENTER_LON = 40.9050, 31.1820
_T0 = time.monotonic()


def _simulate_enemies() -> list[dict]:
    """3 rakip İHA — dairesel patern, 12/16/20 m/s (KTR §8.3.1)."""
    t = time.monotonic() - _T0
    enemies = []
    for i, speed in enumerate([12.0, 16.0, 20.0]):
        radius = 80 + i * 30
        omega = speed / radius   # rad/s
        angle = omega * t + i * 2.0
        # Yaklaşık metre→derece dönüşümü
        dlat = (radius * math.cos(angle)) / 111000
        dlon = (radius * math.sin(angle)) / (111000 * math.cos(math.radians(CENTER_LAT)))
        enemies.append({
            "id":         f"ENEMY-{i+1:02d}",
            "lat":        round(CENTER_LAT + dlat, 6),
            "lon":        round(CENTER_LON + dlon, 6),
            "irtifa":     round(80 + i * 15, 1),
            "hiz":        speed,
            "heading":    round((math.degrees(angle + math.pi/2)) % 360, 1),
            "timestamp":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    return enemies


# Statik HSS silindirleri (KTR §5)
HSS_ZONES = [
    {"id": "HSS-1", "lat": 40.9072, "lon": 31.1858, "radius": 150,
     "h_min": 0, "h_max": 200},
    {"id": "HSS-2", "lat": 40.9008, "lon": 31.1810, "radius": 120,
     "h_min": 0, "h_max": 180},
]

# Uçuş sınırları
GEOFENCE = [
    [40.8975, 31.1735],
    [40.8975, 31.1910],
    [40.9115, 31.1910],
    [40.9115, 31.1735],
]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/rakip_iha")
def rakip_iha():
    return {"enemies": _simulate_enemies()}


@app.get("/api/hss_verisi")
def hss():
    return {"zones": HSS_ZONES, "timestamp": time.time()}


@app.get("/api/ucus_sinirlari")
def geofence():
    return {"polygon": GEOFENCE}


@app.post("/api/kilit_bilgisi")
def kilit_bilgisi(payload: dict[str, Any]):
    logger.info("KILIT bilgisi alındı: %s", payload)
    # %95 ihtimal ACK, %5 başarısız (gerçekçi network)
    if random.random() < 0.95:
        return {"status": "ok", "ack": True, "received_at": time.time()}
    return {"status": "error", "ack": False}, 503


@app.post("/api/kamikaze_bilgisi")
def kamikaze_bilgisi(payload: dict[str, Any]):
    logger.info("KAMIKAZE paketi alındı: takim=%s qr=%s",
                payload.get("takim_id"), str(payload.get("qr_veri"))[:40])
    # %90 başarı
    if random.random() < 0.90:
        return {"status": "ok", "ack": True, "qr_veri": payload.get("qr_veri"),
                "received_at": time.time()}
    return {"status": "error", "ack": False}, 503


@app.get("/")
def root():
    return {
        "name": "GökKurt Mock Yarışma Sunucusu",
        "endpoints": [
            "GET  /api/rakip_iha",
            "GET  /api/hss_verisi",
            "GET  /api/ucus_sinirlari",
            "POST /api/kilit_bilgisi",
            "POST /api/kamikaze_bilgisi",
        ],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=9000)
    a = p.parse_args()
    logger.info("Mock yarışma sunucusu başlatılıyor: http://%s:%d", a.host, a.port)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
