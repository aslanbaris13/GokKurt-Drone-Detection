"""
GökKurt — Drone Algılama ve Takip Sistemi
DetectorService birim testleri.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Proje kökünü sys.path'e ekle
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.config as config

# ── Test başlamadan önce SIMULATION_MODE=True zorla ─────────────────────────
config.SIMULATION_MODE = True


# ── ultralytics stub ─────────────────────────────────────────────────────────
def _make_ultralytics_stub(model_names: dict[int, str], detections: list[dict]):
    """Gerçek model olmadan DetectorService'i test edebilmek için sahte YOLO."""

    class _FakeBox:
        def __init__(self, d: dict):
            self.conf = [d["confidence"]]
            self.cls = [d["class_id"]]
            xyxy_tensor = MagicMock()
            xyxy_tensor.tolist.return_value = list(d["xyxy"])
            self.xyxy = [xyxy_tensor]

    class _FakeResult:
        def __init__(self):
            self.boxes = [_FakeBox(d) for d in detections]

    class _FakeYOLO:
        def __init__(self, *a, **kw):
            self.names = model_names

        def __call__(self, frame, verbose=False):
            return [_FakeResult()]

    ultralytics_stub = types.ModuleType("ultralytics")
    ultralytics_stub.YOLO = _FakeYOLO
    return ultralytics_stub


# ─────────────────────────────────────────────────────────────────────────────


class TestDetectorService:
    """DetectorService birim testleri."""

    def _make_detector(self, model_names: dict, detections: list) -> "DetectorService":
        stub = _make_ultralytics_stub(model_names, detections)
        with patch.dict("sys.modules", {"ultralytics": stub}):
            from src.detector_service import DetectorService
            detector = DetectorService()
        # Modeli sahteyle değiştir (yeniden import gerekmeden)
        new_stub = _make_ultralytics_stub(model_names, detections)
        detector.model = new_stub.YOLO("dummy")
        detector._class_names = model_names
        return detector

    # ── Test 1: Servis doğru yükleniyor mu? ──────────────────────────────────

    def test_service_loads(self):
        """DetectorService nesnesinin başarıyla oluşturulduğunu doğrular."""
        stub = _make_ultralytics_stub({0: "drone"}, [])
        with patch.dict("sys.modules", {"ultralytics": stub}):
            from importlib import reload
            import src.detector_service as dm
            reload(dm)
            detector = dm.DetectorService()
        assert detector is not None
        assert hasattr(detector, "model")

    # ── Test 2: Boş frame hata vermemeli ────────────────────────────────────

    def test_empty_frame_returns_empty_list(self):
        """Sıfır boyutlu frame'de detect() boş liste döndürmeli."""
        detector = self._make_detector({0: "drone"}, [])
        empty = np.zeros((0, 0, 3), dtype=np.uint8)
        result = detector.detect(empty)
        assert result == []

    def test_none_frame_returns_empty_list(self):
        """None frame'de detect() boş liste döndürmeli."""
        detector = self._make_detector({0: "drone"}, [])
        result = detector.detect(None)  # type: ignore[arg-type]
        assert result == []

    # ── Test 3: Dönüş formatı doğru mu? ─────────────────────────────────────

    def test_return_format(self):
        """detect() çıktısının beklenen sözlük formatında olduğunu doğrular."""
        model_names = {0: "drone"}
        raw_detections = [
            {"class_id": 0, "confidence": 0.9, "xyxy": (10, 20, 100, 150)},
        ]
        detector = self._make_detector(model_names, raw_detections)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = detector.detect(frame)

        assert len(results) == 1
        det = results[0]
        assert "bbox" in det
        assert "confidence" in det
        assert "class" in det
        assert isinstance(det["bbox"], tuple)
        assert len(det["bbox"]) == 4
        assert isinstance(det["confidence"], float)
        assert isinstance(det["class"], str)

    # ── Test 4: Güven eşiği filtresi çalışıyor mu? ──────────────────────────

    def test_confidence_filter(self):
        """Güven eşiğinin altındaki tespitler filtrelenmelidir."""
        original_conf = config.YOLO_CONFIDENCE
        config.YOLO_CONFIDENCE = 0.8
        try:
            model_names = {0: "drone"}
            raw_detections = [
                {"class_id": 0, "confidence": 0.5, "xyxy": (0, 0, 50, 50)},  # eşiğin altı
                {"class_id": 0, "confidence": 0.9, "xyxy": (10, 10, 60, 60)},  # eşiğin üstü
            ]
            detector = self._make_detector(model_names, raw_detections)
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            results = detector.detect(frame)
            assert len(results) == 1
            assert results[0]["confidence"] == 0.9
        finally:
            config.YOLO_CONFIDENCE = original_conf

    # ── Test 5: Sonuçlar güvene göre sıralı mı? ─────────────────────────────

    def test_results_sorted_by_confidence(self):
        """detect() sonuçları güvene göre azalan sırada olmalıdır."""
        model_names = {0: "drone"}
        raw_detections = [
            {"class_id": 0, "confidence": 0.6, "xyxy": (0, 0, 10, 10)},
            {"class_id": 0, "confidence": 0.95, "xyxy": (20, 20, 80, 80)},
            {"class_id": 0, "confidence": 0.75, "xyxy": (5, 5, 50, 50)},
        ]
        detector = self._make_detector(model_names, raw_detections)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = detector.detect(frame)
        confidences = [r["confidence"] for r in results]
        assert confidences == sorted(confidences, reverse=True)
