"""
GökKurt — Sonlu Durum Makinesi (FSM) Servisi
KTR §4.2.1'de tanımlanan kamikaze görev fazlarını yönetir.

Durumlar:
    IDLE       → bekleme
    INTIKAL    → hedefe yaklaşma (≥100m irtifa, 16-18 m/s)
    DALIS      → kontrollü alçalma (25-30°, max 28 m/s)
    KILIT      → bbox %6+ 4s + QR tespit
    PAS_GEC    → tırmanış (+15° pitch, 120m'ye kadar)
    DONUS      → loiter / RTL
    ABORT      → failsafe — tüm fazlardan tetiklenebilir

Geçişler şartnameye uygun olarak modellenmiştir; demo amaçlı bazı kısıtlar
(irtifa, hız) telemetri yokken otomatik sağlanır kabul edilir.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

from src import config

logger = logging.getLogger(__name__)


class FSMState(str, Enum):
    IDLE = "IDLE"
    INTIKAL = "INTIKAL"
    DALIS = "DALIS"
    KILIT = "KILIT"
    PAS_GEC = "PAS_GEC"
    DONUS = "DONUS"
    ABORT = "ABORT"


# Şartnameye uygun resmi sıra (UI ile uyumlu)
STATE_ORDER = [
    FSMState.IDLE,
    FSMState.INTIKAL,
    FSMState.DALIS,
    FSMState.KILIT,
    FSMState.PAS_GEC,
    FSMState.DONUS,
]


class FSMService:
    """Görev durumlarını yönetir.

    Servis dışından çağrılan tek metot ``update(...)``: tracker, qr ve telemetry
    durumlarına bakarak bir sonraki state'e geçer.
    """

    def __init__(self) -> None:
        self.state: FSMState = FSMState.IDLE
        self.previous: Optional[FSMState] = None
        self.entered_at: float = time.monotonic()
        self.abort_reason: Optional[str] = None
        self.transitions: list[dict] = []           # {ts, from, to, reason}

    # ── Public API ───────────────────────────────────────────────────────────

    @property
    def time_in_state(self) -> float:
        return time.monotonic() - self.entered_at

    @property
    def state_index(self) -> int:
        try:
            return STATE_ORDER.index(self.state)
        except ValueError:
            return -1  # ABORT

    def start_mission(self) -> None:
        """Manuel olarak IDLE → INTIKAL'e geçer."""
        if self.state == FSMState.IDLE:
            self._transition(FSMState.INTIKAL, "Manuel görev başlatma")

    def abort(self, reason: str) -> None:
        """Acil durum — herhangi bir state'ten ABORT'a."""
        if self.state != FSMState.ABORT:
            self.abort_reason = reason
            self._transition(FSMState.ABORT, reason)

    def reset(self) -> None:
        """IDLE'a geri döner."""
        self.abort_reason = None
        self._transition(FSMState.IDLE, "Reset")

    def update(
        self,
        tracking: bool,
        criterion_met: bool,
        is_locked: bool,
        qr_decoded: bool,
        kamikaze_ack: bool,
    ) -> None:
        """Her döngüde çağrılır — koşullara göre state ilerletir.

        Args:
            tracking:       herhangi bir drone tespit edildi mi?
            criterion_met:  bbox %6+ koşulu sağlanıyor mu (anlık)?
            is_locked:      4s kilit tamamlandı mı?
            qr_decoded:     QR kod son 2sn'de okundu mu?
            kamikaze_ack:   Kamikaze paketi sunucuya iletildi ve ACK alındı mı?
        """
        s = self.state
        t = self.time_in_state

        # Failsafe state'inden manuel reset gerekir
        if s == FSMState.ABORT:
            return

        # ── IDLE → INTIKAL: tracking başladığında otomatik başlat
        if s == FSMState.IDLE:
            if tracking:
                self._transition(FSMState.INTIKAL, "Hedef tespit edildi")

        # ── INTIKAL → DALIS: bbox %6 sağlandığında (mesafe yakın anlamına gelir)
        elif s == FSMState.INTIKAL:
            if criterion_met:
                self._transition(FSMState.DALIS, "Yaklaşma tamamlandı (bbox≥%6)")
            elif not tracking and t > 5.0:
                self._transition(FSMState.IDLE, "INTIKAL'da hedef kayboldu")

        # ── DALIS → KILIT: 4s kesintisiz kilit
        elif s == FSMState.DALIS:
            if is_locked:
                self._transition(FSMState.KILIT, "Kilit tamamlandı (4s)")
            elif not tracking and t > 3.0:
                self.abort("DALIS sırasında hedef kayboldu")
            elif t > config.FSM_LOCK_TIMEOUT:
                self.abort("DALIS zaman aşımı")

        # ── KILIT → PAS_GEC: kamikaze paketi ACK aldı (QR okundu)
        elif s == FSMState.KILIT:
            if qr_decoded and kamikaze_ack:
                self._transition(FSMState.PAS_GEC, "Kamikaze paketi gönderildi (ACK)")
            elif t > config.FSM_LOCK_TIMEOUT:
                # 2 deneme başarısız sayılır
                self.abort("KILIT sırasında ACK alınamadı")

        # ── PAS_GEC → DONUS: 2s sonra tırmanış tamamlandı varsayımı
        elif s == FSMState.PAS_GEC:
            if t >= config.FSM_PASS_DURATION:
                self._transition(FSMState.DONUS, "Pas geçme tamamlandı")

        # ── DONUS → IDLE: 3s loiter sonrası hazır
        elif s == FSMState.DONUS:
            if t >= 3.0:
                self._transition(FSMState.IDLE, "Görev tamamlandı")

    # ── Geçiş yardımcısı ─────────────────────────────────────────────────────

    def _transition(self, new_state: FSMState, reason: str) -> None:
        if new_state == self.state:
            return
        ts = time.monotonic()
        self.previous = self.state
        logger.info("FSM: %s → %s (%s)", self.state.value, new_state.value, reason)
        self.transitions.append({
            "ts": ts,
            "from": self.state.value,
            "to": new_state.value,
            "reason": reason,
        })
        # Son 50 geçişi tut
        if len(self.transitions) > 50:
            self.transitions = self.transitions[-50:]
        self.state = new_state
        self.entered_at = ts

    # ── Serileştirme ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "state_index": self.state_index,
            "previous": self.previous.value if self.previous else None,
            "time_in_state": round(self.time_in_state, 2),
            "abort_reason": self.abort_reason,
            "recent_transitions": self.transitions[-10:],
        }
