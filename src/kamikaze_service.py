"""
GökKurt — Kamikaze Paket İletim Servisi
KTR §4.2.2: QR kodu çözüldükten sonra ``kamikaze_bilgisi`` JSON paketi
yarışma sunucusuna REST over TLS (HTTPS) ile gönderilir.

Paket şeması:
    {timestamp, takim_id, qr_veri, lat, lon, irtifa, hiz}

ACK alınmazsa 3s timeout ile yeniden denenir (toplam 2 deneme); 2. deneme de
başarısız olursa FSM ABORT'a düşer.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from src import config

logger = logging.getLogger(__name__)


@dataclass
class KamikazePacket:
    timestamp: str
    takim_id: str
    qr_veri: str
    lat: float
    lon: float
    irtifa: float
    hiz: float

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "takim_id":  self.takim_id,
            "qr_veri":   self.qr_veri,
            "lat":       self.lat,
            "lon":       self.lon,
            "irtifa":    self.irtifa,
            "hiz":       self.hiz,
        }


@dataclass
class TransmissionStatus:
    """UI'ya açılan paket durumu."""
    state: str = "idle"          # idle | sending | ack | failed
    attempts: int = 0
    max_attempts: int = config.COMP_MAX_RETRIES + 1
    last_packet: Optional[dict] = None
    last_error: Optional[str] = None
    last_response: Optional[str] = None
    history: list[dict] = field(default_factory=list)   # son gönderiler

    def to_dict(self) -> dict:
        return {
            "state":         self.state,
            "attempts":      self.attempts,
            "max_attempts":  self.max_attempts,
            "last_packet":   self.last_packet,
            "last_error":    self.last_error,
            "last_response": self.last_response,
            "history":       self.history[-10:],
        }


class KamikazeService:
    """QR sonucu + telemetry alır, sunucuya gönderir, ACK bekler."""

    def __init__(self) -> None:
        self.status = TransmissionStatus()
        self._lock = threading.Lock()
        self._inflight = False

    # ── Public ────────────────────────────────────────────────────────────────

    def send_async(
        self,
        qr_data: str,
        lat: float = 0.0,
        lon: float = 0.0,
        irtifa: float = 0.0,
        hiz: float = 0.0,
    ) -> None:
        """Arka plan thread'inde paket gönderir; ana döngüyü bloklamaz."""
        if self._inflight:
            logger.debug("Önceki kamikaze paketi hâlâ uçuşta, atlanıyor.")
            return

        packet = KamikazePacket(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            takim_id=config.COMP_TEAM_ID,
            qr_veri=qr_data,
            lat=lat, lon=lon, irtifa=irtifa, hiz=hiz,
        )
        self._inflight = True
        threading.Thread(target=self._send_with_retries, args=(packet,), daemon=True).start()

    def reset(self) -> None:
        with self._lock:
            self.status = TransmissionStatus()

    # ── İç ────────────────────────────────────────────────────────────────────

    def _send_with_retries(self, packet: KamikazePacket) -> None:
        try:
            url = f"{config.COMP_SERVER_URL}/api/kamikaze_bilgisi"
            payload = packet.to_dict()

            with self._lock:
                self.status.state = "sending"
                self.status.attempts = 0
                self.status.last_packet = payload
                self.status.last_error = None
                self.status.last_response = None

            for attempt in range(1, config.COMP_MAX_RETRIES + 2):
                with self._lock:
                    self.status.attempts = attempt
                logger.info("Kamikaze paketi gönderiliyor (deneme %d/%d) → %s",
                            attempt, config.COMP_MAX_RETRIES + 1, url)
                try:
                    with httpx.Client(timeout=config.COMP_RETRY_TIMEOUT, verify=False) as client:
                        r = client.post(url, json=payload)
                        ok = r.status_code == 200
                        body = r.text[:200]
                        if ok:
                            with self._lock:
                                self.status.state = "ack"
                                self.status.last_response = body
                                self.status.history.append({
                                    "ts": time.time(),
                                    "result": "ack",
                                    "attempts": attempt,
                                    "qr": packet.qr_veri[:40],
                                })
                            logger.info("Kamikaze paketi ACK alındı (HTTP 200).")
                            return
                        else:
                            err = f"HTTP {r.status_code}: {body}"
                            logger.warning("Kamikaze paketi başarısız: %s", err)
                            with self._lock:
                                self.status.last_error = err
                except Exception as e:
                    logger.warning("Kamikaze gönderim hatası (deneme %d): %s", attempt, e)
                    with self._lock:
                        self.status.last_error = str(e)

            # Tüm denemeler başarısız
            with self._lock:
                self.status.state = "failed"
                self.status.history.append({
                    "ts": time.time(),
                    "result": "failed",
                    "attempts": self.status.attempts,
                    "qr": packet.qr_veri[:40],
                    "error": self.status.last_error,
                })
            logger.error("Kamikaze paketi tüm denemelerde başarısız.")
        finally:
            self._inflight = False

    @property
    def acked(self) -> bool:
        return self.status.state == "ack"
