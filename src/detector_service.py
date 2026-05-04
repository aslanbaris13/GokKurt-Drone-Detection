"""
GökKurt — Drone Algılama ve Takip Sistemi
Detector servisi: YOLOv26 Nano modeli ile kare üzerinde drone tespiti yapar.
"""

import logging
from typing import Any

import numpy as np

from src import config

logger = logging.getLogger(__name__)

# Algılama sonucunu temsil eden tip takma adı
Detection = dict[str, Any]  # {"bbox": (x1,y1,x2,y2), "confidence": float, "class": str}


class DetectorService:
    """YOLOv26 Nano modelini kullanarak drone tespiti yapan servis."""

    # COCO sınıf adlarından fallback listesi (drone sınıfı yoksa bunlar da kabul edilir)
    _FALLBACK_CLASSES: tuple[str, ...] = ("drone", "airplane", "bird", "kite")

    def __init__(self) -> None:
        """Modeli diskten yükler."""
        from ultralytics import YOLO  # type: ignore[import]

        logger.info("YOLO modeli yükleniyor: %s", config.YOLO_MODEL_PATH)
        self.model = YOLO(config.YOLO_MODEL_PATH)
        logger.info("Model başarıyla yüklendi.")

        # Modelin desteklediği sınıf adlarını al
        self._class_names: dict[int, str] = self.model.names  # {id: "name"}
        logger.debug("Model sınıfları: %s", self._class_names)

    # ── Ana Algılama Metodu ───────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Verilen karede drone tespiti yapar.

        Args:
            frame: BGR formatında numpy kare dizisi.

        Returns:
            Tespit edilen nesnelerin listesi. Her eleman::

                {
                    "bbox": (x1, y1, x2, y2),   # piksel koordinatları
                    "confidence": float,          # 0.0 – 1.0
                    "class": str,                 # sınıf adı
                }

            Güven eşiğinin altındaki veya hedef dışı tespitler filtrelenir.
            Liste güvene göre azalan sırada sıralanır.
        """
        if frame is None or frame.size == 0:
            return []

        # YOLO çıkarımı yap — imgsz=320 Pi CPU için yeterli, 2x hız kazanımı
        results = self.model(frame, verbose=False, imgsz=320)

        detections: list[Detection] = []

        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                class_name = self._class_names.get(class_id, "unknown")

                # Güven ve sınıf filtresi
                if confidence < config.YOLO_CONFIDENCE:
                    continue
                if not self._is_target_class(class_name):
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                detection: Detection = {
                    "bbox": (x1, y1, x2, y2),
                    "confidence": confidence,
                    "class": class_name,
                }
                detections.append(detection)
                logger.debug(
                    "Tespit: sınıf=%s güven=%.2f bbox=(%d,%d,%d,%d)",
                    class_name, confidence, x1, y1, x2, y2,
                )

        # Güvene göre azalan sırada sırala
        detections.sort(key=lambda d: d["confidence"], reverse=True)

        if detections:
            best = detections[0]
            logger.info(
                "En iyi tespit: %s %.2f @ bbox%s",
                best["class"], best["confidence"], best["bbox"],
            )

        return detections

    # ── Yardımcı Metodlar ────────────────────────────────────────────────────

    def _is_target_class(self, class_name: str) -> bool:
        """Sınıf adının hedef listesinde olup olmadığını kontrol eder."""
        name_lower = class_name.lower()
        # Önce config'deki birincil hedefi dene
        if name_lower == config.YOLO_TARGET_CLASS.lower():
            return True
        # Fallback: modelde "drone" yoksa diğer havacı sınıfları kabul et
        return name_lower in self._FALLBACK_CLASSES
