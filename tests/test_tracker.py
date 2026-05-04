"""
GökKurt — Drone Algılama ve Takip Sistemi
TrackerService birim testleri.
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.config as config

config.SIMULATION_MODE = True

from src.tracker_service import TrackerService

# Sahte tespit yardımcısı
def _det(x1=10, y1=10, x2=100, y2=100, conf=0.9) -> dict:
    return {"bbox": (x1, y1, x2, y2), "confidence": conf, "class": "drone"}


FRAME_CENTER = (320, 240)


class TestTrackerService:
    """TrackerService birim testleri."""

    # ── Test 1: 4 saniye kilit mantığı ───────────────────────────────────────

    def test_lock_achieved_after_4_seconds(self):
        """4 saniyelik kesintisiz tespitte is_locked=True olmalı."""
        tracker = TrackerService()

        # Zamanı taklit et: 4.1 saniye ileri sar
        start = time.monotonic()
        with patch("src.tracker_service.time") as mock_time:
            mock_time.monotonic.return_value = start
            tracker.update([_det()], FRAME_CENTER)  # takip başlasın

            # Kilit süresi dolmadan önce
            mock_time.monotonic.return_value = start + 3.9
            just_locked = tracker.update([_det()], FRAME_CENTER)
            assert not just_locked
            assert not tracker.is_locked

            # Kilit süresi dolduktan sonra
            mock_time.monotonic.return_value = start + 4.1
            just_locked = tracker.update([_det()], FRAME_CENTER)

        assert just_locked, "4 saniye dolduğunda just_locked=True bekleniyor"
        assert tracker.is_locked

    # ── Test 2: Kilit kaybedilince sıfırlanmalı ──────────────────────────────

    def test_lock_resets_when_target_lost(self):
        """Hedef LOCK_LOST_TIMEOUT'u aşarsa kilit sıfırlanmalı."""
        tracker = TrackerService()
        start = time.monotonic()

        with patch("src.tracker_service.time") as mock_time:
            # Takibi başlat
            mock_time.monotonic.return_value = start
            tracker.update([_det()], FRAME_CENTER)

            # Tolerans süresini aş
            mock_time.monotonic.return_value = start + config.LOCK_LOST_TIMEOUT + 0.1
            tracker.update([], FRAME_CENTER)  # tespit yok

        assert not tracker.is_tracking
        assert not tracker.is_locked
        assert tracker.lock_progress == 0.0

    # ── Test 3: Lock progress hesabı doğru mu? ───────────────────────────────

    def test_lock_progress_calculation(self):
        """lock_progress değeri zamanla doğru artmalıdır."""
        tracker = TrackerService()
        start = time.monotonic()

        with patch("src.tracker_service.time") as mock_time:
            mock_time.monotonic.return_value = start
            tracker.update([_det()], FRAME_CENTER)

            half = config.LOCK_DURATION / 2
            mock_time.monotonic.return_value = start + half
            tracker.update([_det()], FRAME_CENTER)

        expected = 0.5
        assert abs(tracker.lock_progress - expected) < 0.05, (
            f"lock_progress {tracker.lock_progress:.3f} beklenen ~{expected}"
        )

    # ── Test 4: lock_progress 1.0'ı aşmamalı ────────────────────────────────

    def test_lock_progress_capped_at_1(self):
        """lock_progress hiçbir zaman 1.0'ı geçmemeli."""
        tracker = TrackerService()
        start = time.monotonic()

        with patch("src.tracker_service.time") as mock_time:
            mock_time.monotonic.return_value = start
            tracker.update([_det()], FRAME_CENTER)

            mock_time.monotonic.return_value = start + config.LOCK_DURATION * 3
            tracker.update([_det()], FRAME_CENTER)

        assert tracker.lock_progress <= 1.0

    # ── Test 5: reset() her şeyi sıfırlamalı ─────────────────────────────────

    def test_reset_clears_all_state(self):
        """reset() çağrısı tüm durumu başlangıç değerlerine döndürmeli."""
        tracker = TrackerService()
        start = time.monotonic()

        with patch("src.tracker_service.time") as mock_time:
            mock_time.monotonic.return_value = start
            tracker.update([_det()], FRAME_CENTER)
            mock_time.monotonic.return_value = start + 1.0
            tracker.update([_det()], FRAME_CENTER)

        tracker.reset()

        assert not tracker.is_tracking
        assert not tracker.is_locked
        assert tracker.lock_progress == 0.0

    # ── Test 6: pan/tilt hata hesabı ─────────────────────────────────────────

    def test_pan_tilt_error_center_target(self):
        """Merkezdeki hedef için hata vektörü sıfır olmalı."""
        tracker = TrackerService()
        # Çerçeve 640x480, merkez (320,240)
        # bbox merkezi de (320,240) olsun: (160,120,480,360)
        pan_err, tilt_err = tracker.get_pan_tilt_error((160, 120, 480, 360), 640, 480)
        assert abs(pan_err) < 1e-9
        assert abs(tilt_err) < 1e-9

    def test_pan_tilt_error_right_target(self):
        """Sağdaki hedef pozitif pan hatası vermeli."""
        tracker = TrackerService()
        # bbox merkezi (480, 240): sağda
        pan_err, tilt_err = tracker.get_pan_tilt_error((380, 120, 580, 360), 640, 480)
        assert pan_err > 0, "Sağdaki hedef pozitif pan hatası vermeli"

    # ── Test 7: Tolerans süresi içinde kilit korunmalı ───────────────────────

    def test_lock_preserved_within_tolerance(self):
        """LOCK_LOST_TIMEOUT dolmadan hedef kaybolursa kilit korunmalı."""
        tracker = TrackerService()
        start = time.monotonic()

        with patch("src.tracker_service.time") as mock_time:
            # Kilidi tamamla
            mock_time.monotonic.return_value = start
            tracker.update([_det()], FRAME_CENTER)
            mock_time.monotonic.return_value = start + config.LOCK_DURATION + 0.1
            tracker.update([_det()], FRAME_CENTER)
            assert tracker.is_locked

            # Tolerans içinde kaybol
            mock_time.monotonic.return_value = (
                start + config.LOCK_DURATION + 0.1 + config.LOCK_LOST_TIMEOUT / 2
            )
            tracker.update([], FRAME_CENTER)

        # Kilit hâlâ korunmalı (tolerans dolmadı)
        assert tracker.is_tracking, "Tolerans süresi içinde takip korunmalı"
