"""
GökKurt — Drone Algılama ve Takip Sistemi
Kamera servisi: SIMULATION_MODE'a göre webcam veya Pi Camera kullanır.
Thread-safe frame yakalama sağlar.
"""

import threading
import logging
from typing import Optional

import cv2
import numpy as np

from src import config

logger = logging.getLogger(__name__)


class CameraService:
    """Kamera kaynağını yöneten servis.

    SIMULATION_MODE True iken OpenCV VideoCapture (webcam/video),
    False iken picamera2 kullanır.
    """

    def __init__(self, source: int | str = 0) -> None:
        """
        Args:
            source: Webcam indeksi (int) ya da video dosyası yolu (str).
                    Yalnızca SIMULATION_MODE=True durumunda geçerlidir.
        """
        self._source = source
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Kamera nesnesi — mode'a göre atanır
        self._cap = None        # OpenCV capture (simülasyon)
        self._picam = None      # picamera2 örneği (Pi)

    # ── Başlatma / Durdurma ──────────────────────────────────────────────────

    def start(self) -> None:
        """Kamera kaynağını açar ve arka plan thread'ini başlatır."""
        if config.SIMULATION_MODE:
            self._cap = cv2.VideoCapture(self._source)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
            self._cap.set(cv2.CAP_PROP_FPS, config.CAMERA_FPS)
            if not self._cap.isOpened():
                # Kamera yok — sahte kare üretme moduna geç
                logger.warning("Kamera açılamadı (%s) — sahte kare (synthetic) moduna geçildi.", self._source)
                self._cap = None   # _read_frame synthetic yola düşer
            else:
                logger.info("Simülasyon kamerası açıldı: %s", self._source)
        else:
            # Gerçek Pi kamerası
            from picamera2 import Picamera2  # type: ignore[import]
            self._picam = Picamera2()
            camera_config = self._picam.create_preview_configuration(
                main={
                    "size": (config.CAMERA_WIDTH, config.CAMERA_HEIGHT),
                    "format": "RGB888",
                }
            )
            self._picam.configure(camera_config)
            self._picam.start()
            logger.info("Pi Camera başlatıldı (%dx%d)", config.CAMERA_WIDTH, config.CAMERA_HEIGHT)

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="CameraThread")
        self._thread.start()
        logger.info("Kamera thread'i başlatıldı.")

    def stop(self) -> None:
        """Kamera kaynağını ve thread'i temizler."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)

        if self._cap is not None:
            self._cap.release()
            self._cap = None

        if self._picam is not None:
            self._picam.stop()
            self._picam = None

        logger.info("Kamera servisi durduruldu.")

    # ── Frame Alma ───────────────────────────────────────────────────────────

    def get_frame(self) -> Optional[np.ndarray]:
        """En son yakalanan kareyi döndürür (thread-safe).

        Returns:
            BGR formatında numpy dizisi, henüz kare yoksa None.
        """
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    # ── İç Döngü ─────────────────────────────────────────────────────────────

    def _capture_loop(self) -> None:
        """Arka planda sürekli kare yakalar ve _frame'i günceller."""
        while self._running:
            frame = self._read_frame()
            if frame is not None:
                with self._lock:
                    self._frame = frame

    def _read_frame(self) -> Optional[np.ndarray]:
        """Kaynaktan tek bir kare okur."""
        if config.SIMULATION_MODE:
            if self._cap is None:
                # Gerçek kamera yok — gri test karesi üret
                import time
                time.sleep(1.0 / config.CAMERA_FPS)
                frame = np.zeros((config.CAMERA_HEIGHT, config.CAMERA_WIDTH, 3), dtype=np.uint8)
                frame[:] = (20, 20, 30)   # koyu lacivert
                t = cv2.getTickCount() / cv2.getTickFrequency()
                cv2.putText(frame, "SYNTHETIC FRAME", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 180, 255), 2)
                cv2.putText(frame, f"t={t:.2f}s", (10, 55),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 140), 1)
                return frame
            ret, frame = self._cap.read()
            if not ret:
                # Video dosyası bitince başa sar
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._cap.read()
            return frame if ret else None
        else:
            # picamera2 RGB döndürür; OpenCV BGR bekler
            if self._picam is None:
                return None
            rgb = self._picam.capture_array()
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
