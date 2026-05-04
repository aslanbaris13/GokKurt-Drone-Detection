"""
GökKurt — QR Kod Tespit Servisi
KTR §4.2.2'de tanımlanan 3 aşamalı pipeline'ı uygular:

  1. Adaptive threshold + morfolojik filtreleme
  2. cv2.findContours ile aday QR çerçevesi + cv2.warpPerspective ile düzleştirme
  3. PyZbar ile decode

Kamikaze dalışında kamera açısı 0–30° değişebildiği için ham görüntü üzerinde
doğrudan PyZbar çağrısı çoğu zaman başarısız olur; perspektif telafisi kritiktir.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from src import config

logger = logging.getLogger(__name__)

try:
    from pyzbar.pyzbar import decode as _pyzbar_decode  # type: ignore[import]
    _HAS_PYZBAR = True
except Exception as e:  # pyzbar libsystem bağımlılığı eksikse fallback
    logger.warning("pyzbar yüklenemedi (%s) — OpenCV QRCodeDetector fallback kullanılacak.", e)
    _pyzbar_decode = None
    _HAS_PYZBAR = False


@dataclass
class QRResult:
    """Çözülen QR kodunun sonucu."""
    data: str                              # Çözülen metin
    polygon: list[tuple[int, int]]         # 4 köşe noktası (kamera çerçevesi piksel)
    bbox: tuple[int, int, int, int]        # x1,y1,x2,y2
    confidence: float                      # 0..1 — perspective + decode kalitesi
    decoded_at: float                      # time.monotonic() timestamp


class QRService:
    """3 aşamalı QR pipeline'ını koşturur."""

    def __init__(self) -> None:
        self._last_decode_time: float = 0.0
        self._last_result: Optional[QRResult] = None
        self._opencv_detector = cv2.QRCodeDetector()

    # ── Public ────────────────────────────────────────────────────────────────

    def process(self, frame: np.ndarray) -> Optional[QRResult]:
        """Tek bir kareyi işler ve QR sonucu döndürür (yoksa None).

        Args:
            frame: BGR kare.
        Returns:
            QRResult ya da None.
        """
        if frame is None or frame.size == 0:
            return None

        now = time.monotonic()
        # CPU tasarrufu — decode çok sık çağrılmasın
        if now - self._last_decode_time < config.QR_DECODE_INTERVAL:
            return self._last_result
        self._last_decode_time = now

        # 1) Adaptive threshold + morfoloji
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        block = config.QR_ADAPTIVE_BLOCK
        if block % 2 == 0:
            block += 1
        thresh = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block,
            config.QR_ADAPTIVE_C,
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)

        # 2) Aday QR çerçevelerini çıkar + perspektif düzleştirme
        candidates = self._extract_candidates(morph, frame)

        # 3) Her aday için decode dene
        for warped, polygon in candidates:
            data = self._decode(warped)
            if data:
                xs = [p[0] for p in polygon]
                ys = [p[1] for p in polygon]
                bbox = (min(xs), min(ys), max(xs), max(ys))
                result = QRResult(
                    data=data,
                    polygon=polygon,
                    bbox=bbox,
                    confidence=0.95,
                    decoded_at=now,
                )
                self._last_result = result
                logger.info("QR çözüldü: %s @ bbox=%s", data[:60], bbox)
                return result

        # Aday yoksa veya hiçbiri çözülemediyse — son çare olarak ham kare üzerinde dene
        data = self._decode(frame)
        if data:
            h, w = frame.shape[:2]
            result = QRResult(
                data=data,
                polygon=[(0, 0), (w, 0), (w, h), (0, h)],
                bbox=(0, 0, w, h),
                confidence=0.5,
                decoded_at=now,
            )
            self._last_result = result
            logger.info("QR çözüldü (raw frame fallback): %s", data[:60])
            return result

        # Sonuç yok — son sonucun yaşı 1.5s'den fazlaysa temizle
        if self._last_result and (now - self._last_result.decoded_at) > 1.5:
            self._last_result = None
        return self._last_result

    # ── Aşama 2: Aday çıkarımı + perspektif telafisi ─────────────────────────

    def _extract_candidates(
        self,
        binary: np.ndarray,
        original: np.ndarray,
    ) -> list[tuple[np.ndarray, list[tuple[int, int]]]]:
        """findContours + approxPolyDP ile dörtgen adayları çıkarır
        ve her birini 200x200 kareye warp eder."""
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        h, w = binary.shape
        max_area = h * w * 0.6
        results: list[tuple[np.ndarray, list[tuple[int, int]]]] = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < config.QR_MIN_AREA or area > max_area:
                continue

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
            if len(approx) != 4:
                continue

            pts = approx.reshape(4, 2).astype(np.float32)
            ordered = self._order_points(pts)

            side = 200
            dst = np.array([[0, 0], [side - 1, 0], [side - 1, side - 1], [0, side - 1]],
                           dtype=np.float32)
            M = cv2.getPerspectiveTransform(ordered, dst)
            warped = cv2.warpPerspective(original, M, (side, side))

            polygon = [(int(p[0]), int(p[1])) for p in ordered]
            results.append((warped, polygon))

        # Adayları alana göre büyükten küçüğe sırala (hedef daha büyük)
        results.sort(key=lambda r: -cv2.contourArea(np.array(r[1])))
        return results[:5]

    @staticmethod
    def _order_points(pts: np.ndarray) -> np.ndarray:
        """4 noktayı top-left, top-right, bottom-right, bottom-left sırasına dizer."""
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # tl
        rect[2] = pts[np.argmax(s)]   # br
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # tr
        rect[3] = pts[np.argmax(diff)]  # bl
        return rect

    # ── Aşama 3: Decode ──────────────────────────────────────────────────────

    def _decode(self, image: np.ndarray) -> Optional[str]:
        """PyZbar varsa onu, yoksa OpenCV detector'ı kullanır."""
        if _HAS_PYZBAR and _pyzbar_decode is not None:
            try:
                results = _pyzbar_decode(image)
                for r in results:
                    raw = r.data
                    if isinstance(raw, bytes):
                        return raw.decode("utf-8", errors="replace")
                    return str(raw)
            except Exception as e:
                logger.debug("pyzbar decode hatası: %s", e)

        # Fallback: OpenCV
        try:
            data, points, _ = self._opencv_detector.detectAndDecode(image)
            if data:
                return data
        except Exception as e:
            logger.debug("OpenCV QR decode hatası: %s", e)

        return None
