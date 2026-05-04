"""
GökKurt — Drone Algılama ve Takip Sistemi
Tracker servisi: KTR §4.1.3 kilit kriterini uygular.

Şartname: "hedefin bounding box alanının görüntü alanının yüzde 6-7'sini
4 saniye boyunca kesintisiz kaplaması" gerekir.

Tier 3 eklenti: Kısa süreli tespit kaybında lineer EKF ile tahmin.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Optional

from src import config
from src.detector_service import Detection

logger = logging.getLogger(__name__)

# EKF tolerans: config üzerinden runtime değiştirilebilir
EKF_HISTORY_LEN: int = 6  # bbox geçmişi uzunluğu


class _LinearPredictor:
    """Sabit-hız lineer EKF (2B merkez + sabit boyut)."""

    def __init__(self) -> None:
        self._history: deque[tuple[float, float, float, float, float]] = deque(maxlen=EKF_HISTORY_LEN)
        # (time, cx, cy, w, h)

    def update(self, bbox: tuple[int, int, int, int], now: float) -> None:
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        w  = float(x2 - x1)
        h  = float(y2 - y1)
        self._history.append((now, cx, cy, w, h))

    def predict(self, now: float) -> Optional[tuple[int, int, int, int]]:
        """Mevcut veri noktalarına bakarak bbox tahmin eder.

        Returns:
            (x1, y1, x2, y2) ya da tahmin yoksa None.
        """
        if len(self._history) < 2:
            return None

        # En az 2 nokta olan son iki örneği kullan → hız çıkar
        t0, cx0, cy0, w0, h0 = self._history[-2]
        t1, cx1, cy1, w1, h1 = self._history[-1]
        dt = max(t1 - t0, 1e-6)
        elapsed = now - t1

        if elapsed > config.LOCK_EKF_EXTRAPOLATION:
            return None  # Çok uzun süre geçti — güvenilmez

        vx = (cx1 - cx0) / dt
        vy = (cy1 - cy0) / dt

        new_cx = cx1 + vx * elapsed
        new_cy = cy1 + vy * elapsed
        new_w  = (w0 + w1) / 2.0     # boyutu yavaş ortala
        new_h  = (h0 + h1) / 2.0

        x1p = int(new_cx - new_w / 2)
        y1p = int(new_cy - new_h / 2)
        x2p = int(new_cx + new_w / 2)
        y2p = int(new_cy + new_h / 2)
        return (x1p, y1p, x2p, y2p)

    def reset(self) -> None:
        self._history.clear()


class TrackerService:
    """Kilit ve servo hata vektörünü yöneten servis.

    Attributes:
        is_tracking (bool): Tespit var mı?
        is_locked (bool): KTR kilit kriteri sağlandı mı?
        lock_progress (float): 4s sayacın yüzdesi (0.0–1.0).
        bbox_ratio (float): Anlık bbox alan oranı (0.0–1.0).
        criterion_met (bool): Anlık olarak %6 eşiği aşılıyor mu?
        predicted (bool): Aktif tahmin modunda mı?
    """

    def __init__(self) -> None:
        self.is_tracking: bool = False
        self.is_locked:   bool = False
        self.lock_progress: float = 0.0
        self.bbox_ratio:    float = 0.0
        self.criterion_met: bool = False
        self.predicted:     bool = False   # EKF tahmin modu aktif mi?

        self._criterion_start: Optional[float] = None
        self._last_seen:       Optional[float] = None
        self._last_frame_size: Optional[tuple[int, int]] = None

        self._predictor = _LinearPredictor()

    # ── Ana güncelleme ────────────────────────────────────────────────────────

    def update(
        self,
        detections: list[Detection],
        frame_center: tuple[int, int],
        frame_size: Optional[tuple[int, int]] = None,
    ) -> bool:
        """Tracker'ı tespit listesiyle günceller.

        Args:
            detections: DetectorService çıktısı.
            frame_center: (cx, cy) — eski API uyumu için.
            frame_size: (w, h) — bbox alan oranı hesabı için zorunlu.
        Returns:
            True → bu çağrıda kilit yeni tamamlandı.
        """
        now = time.monotonic()

        # Frame size'ı tahmin et — geriye uyum için
        if frame_size is None and frame_center is not None:
            cx, cy = frame_center
            frame_size = (cx * 2, cy * 2)
        if frame_size:
            self._last_frame_size = frame_size

        if not detections:
            return self._on_no_detection(now)

        # ── Gerçek tespit geldi ─────────────────────────────────────────────
        self.predicted = False
        self._last_seen = now
        self.is_tracking = True

        det = detections[0]
        bbox = det["bbox"]
        self._predictor.update(bbox, now)
        return self._compute_lock(bbox, frame_size, now)

    def _compute_lock(
        self,
        bbox: tuple[int, int, int, int],
        frame_size: Optional[tuple[int, int]],
        now: float,
    ) -> bool:
        """Bbox'tan kilit kriterini hesaplar ve sayacı yönetir."""
        just_locked = False

        x1, y1, x2, y2 = bbox
        bbox_area = max(0, (x2 - x1)) * max(0, (y2 - y1))

        if frame_size:
            fw, fh = frame_size
            frame_area = max(1, fw * fh)
            self.bbox_ratio = bbox_area / frame_area
        else:
            self.bbox_ratio = 0.0

        self.criterion_met = self.bbox_ratio >= config.LOCK_BBOX_RATIO_MIN

        if self.criterion_met:
            if self._criterion_start is None:
                self._criterion_start = now
                logger.info(
                    "Kilit kriteri sağlandı (bbox=%.2f%% >= %.0f%%) — sayaç başladı.%s",
                    self.bbox_ratio * 100,
                    config.LOCK_BBOX_RATIO_MIN * 100,
                    " [EKF]" if self.predicted else "",
                )

            elapsed = now - self._criterion_start
            self.lock_progress = min(elapsed / config.LOCK_DURATION, 1.0)

            if elapsed >= config.LOCK_DURATION and not self.is_locked:
                self.is_locked = True
                just_locked = True
                logger.info(
                    "◆ KİLİT TAMAMLANDI — %.1fs kesintisiz, bbox=%.2f%%",
                    elapsed, self.bbox_ratio * 100,
                )
        else:
            if self._criterion_start is not None:
                logger.debug(
                    "Bbox oranı %.2f%% < %.0f%% — kilit sayacı sıfırlandı.",
                    self.bbox_ratio * 100, config.LOCK_BBOX_RATIO_MIN * 100,
                )
            self._criterion_start = None
            self.lock_progress = 0.0
            self.is_locked = False

        return just_locked

    def _on_no_detection(self, now: float) -> bool:
        """Tespit yokken EKF ile tahmin yap, tolerans bitince sıfırla."""
        if self._last_seen is None:
            return False

        time_since_seen = now - self._last_seen

        # EKF penceresi içinde: tahmin et
        if time_since_seen < config.LOCK_EKF_EXTRAPOLATION:
            predicted_bbox = self._predictor.predict(now)
            if predicted_bbox is not None:
                self.predicted = True
                self.is_tracking = True
                return self._compute_lock(predicted_bbox, self._last_frame_size, now)

        # Tolerans süresi içinde: tracking durumu koru, ama criterion resetle
        if time_since_seen <= config.LOCK_LOST_TIMEOUT:
            self.predicted = False
            self.criterion_met = False
            self.bbox_ratio = 0.0
            self._criterion_start = None
            self.lock_progress = 0.0
            self.is_locked = False
            return False

        # Tolerans süresi bitti: tam reset
        if self.is_tracking:
            logger.info("Hedef kayboldu (%.2fs). Kilit sıfırlandı.", time_since_seen)
        self.reset()
        return False

    # ── Servo hatası ──────────────────────────────────────────────────────────

    def get_pan_tilt_error(
        self,
        bbox: tuple[int, int, int, int],
        frame_w: int,
        frame_h: int,
    ) -> tuple[float, float]:
        """Hedef merkezine göre normalize -1..+1 hata vektörü."""
        x1, y1, x2, y2 = bbox
        target_cx = (x1 + x2) / 2.0
        target_cy = (y1 + y2) / 2.0
        pan_error  = (target_cx - frame_w / 2.0) / (frame_w / 2.0)
        tilt_error = (target_cy - frame_h / 2.0) / (frame_h / 2.0)
        return pan_error, tilt_error

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        self.is_tracking   = False
        self.is_locked     = False
        self.lock_progress = 0.0
        self.bbox_ratio    = 0.0
        self.criterion_met = False
        self.predicted     = False
        self._criterion_start = None
        self._last_seen    = None
        self._predictor.reset()
