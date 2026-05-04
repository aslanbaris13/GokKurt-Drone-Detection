"""
GökKurt — Drone Algılama ve Takip Sistemi
Ana koordinasyon döngüsü. Tüm servisleri başlatır ve birbirine bağlar.

Kullanım:
    python main.py                           # webcam ile simülasyon
    python main.py --source test_video.mp4   # video dosyası ile test
    python main.py --no-display              # ekransız mod (Pi SSH)
    python main.py --simulation              # simülasyon modunu zorla aç
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# ── Argüman ayrıştırma (config'ten önce; simülasyon flag'ini override edebilir)
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GökKurt — Drone Algılama ve Takip Sistemi")
    parser.add_argument(
        "--source",
        default=0,
        help="Video kaynağı: webcam indeksi (0) veya video dosya yolu",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Görüntü penceresini açma (başsız mod / SSH)",
    )
    parser.add_argument(
        "--simulation",
        action="store_true",
        help="GPIO'yu simüle et, webcam kullan (masaüstü testi)",
    )
    return parser.parse_args()


args = _parse_args()

# Simülasyon flag'ini config'e yazmadan önce import et
import src.config as config  # noqa: E402

if args.simulation:
    config.SIMULATION_MODE = True

# --source sayısal ise int'e dönüştür (webcam indeksi)
try:
    source: int | str = int(args.source)
except (ValueError, TypeError):
    source = args.source

# ── Loglama yapılandırması ───────────────────────────────────────────────────
Path(config.LOG_DIR).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

# ── Servis importları ────────────────────────────────────────────────────────
from src.camera_service import CameraService      # noqa: E402
from src.detector_service import DetectorService  # noqa: E402
from src.tracker_service import TrackerService    # noqa: E402
from src.servo_service import ServoService        # noqa: E402
from src.alert_service import AlertService        # noqa: E402


def draw_overlay(
    frame: np.ndarray,
    detections: list,
    tracker,
    fps: float,
) -> np.ndarray:
    """Görüntü üzerine tespit kutusu, kilit bilgisi ve FPS çizer.

    Args:
        frame:      BGR kare.
        detections: DetectorService çıktısı.
        tracker:    TrackerService örneği (progress ve locked okunur).
        fps:        Anlık kare hızı.

    Returns:
        Üzerine çizim yapılmış kare.
    """
    h, w = frame.shape[:2]

    # ── Bounding box ────────────────────────────────────────────────────────
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = f"{det['class']} {det['confidence']:.0%}"

        if tracker.is_locked:
            color = (0, 0, 255)    # Kırmızı — kilitli
            thickness = 3
        else:
            color = (0, 255, 0)    # Yeşil — takip ediliyor
            thickness = 2

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
        cv2.putText(frame, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # ── Kilit durumu ─────────────────────────────────────────────────────────
    if tracker.is_locked:
        cv2.putText(frame, "** LOCKED **", (w // 2 - 90, 40),
                    cv2.FONT_HERSHEY_DUPLEX, 1.1, (0, 0, 255), 3)
    elif tracker.is_tracking:
        pct = int(tracker.lock_progress * 100)
        cv2.putText(frame, f"Kilit: %{pct}", (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        # İlerleme çubuğu
        bar_w = int((w - 20) * tracker.lock_progress)
        cv2.rectangle(frame, (10, 50), (w - 10, 65), (50, 50, 50), -1)
        cv2.rectangle(frame, (10, 50), (10 + bar_w, 65), (0, 200, 255), -1)

    # ── FPS ──────────────────────────────────────────────────────────────────
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

    return frame


def main() -> None:
    logger.info("GökKurt başlatılıyor — simülasyon=%s", config.SIMULATION_MODE)

    # ── Servisleri oluştur ───────────────────────────────────────────────────
    camera = CameraService(source=source)
    detector = DetectorService()
    tracker = TrackerService()
    servo = ServoService()
    alert = AlertService()

    camera.start()
    logger.info("Tüm servisler başlatıldı.")

    # FPS hesabı için değişkenler
    prev_time = time.monotonic()
    fps = 0.0

    try:
        while True:
            # ── a) Kare al ───────────────────────────────────────────────────
            frame = camera.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue

            h, w = frame.shape[:2]

            # ── b) Drone tespiti ─────────────────────────────────────────────
            detections = detector.detect(frame)

            # ── c) Tracker güncelle ──────────────────────────────────────────
            just_locked = tracker.update(
                detections,
                frame_center=(w // 2, h // 2),
                frame_size=(w, h),
            )

            # ── d) Servo yönlendir ───────────────────────────────────────────
            if detections:
                pan_err, tilt_err = tracker.get_pan_tilt_error(
                    detections[0]["bbox"], w, h
                )
                servo.update(pan_err, tilt_err)
            else:
                servo.center()

            # ── e) Uyarı ─────────────────────────────────────────────────────
            if just_locked:
                alert.lock_achieved()
                logger.info("HEDEF KİLİTLENDİ! Uyarı verildi.")
            elif tracker.is_tracking:
                alert.tracking_indicator(tracker.lock_progress)
            else:
                alert.lock_lost()

            # ── f) FPS ───────────────────────────────────────────────────────
            now = time.monotonic()
            fps = 1.0 / max(now - prev_time, 1e-6)
            prev_time = now

            # ── g) Görüntü göster ────────────────────────────────────────────
            if not args.no_display:
                vis = draw_overlay(frame.copy(), detections, tracker, fps)
                cv2.imshow("GökKurt — Drone Takip", vis)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    logger.info("Kullanıcı 'q' tuşuna bastı, çıkılıyor.")
                    break

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — temiz çıkış yapılıyor.")
    finally:
        # ── Cleanup ──────────────────────────────────────────────────────────
        camera.stop()
        servo.center()
        servo.cleanup()
        alert.cleanup()
        cv2.destroyAllWindows()
        logger.info("GökKurt durduruldu.")


if __name__ == "__main__":
    main()
