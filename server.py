"""
GökKurt — FastAPI Sunucu (KTR §6 uyumlu)

Görevler:
  • Pi kamerasından yakalanan kareyi MJPEG ile yayınlar (/stream)
  • Detector → Tracker → QR → Kamikaze → FSM zincirini koşturur
  • WebSocket üzerinden tam telemetri akışı (10 Hz)
  • REST endpoint'leri: /api/system, /api/params, /api/qr/test, /api/mission
  • Mock yarışma sunucusu için dış HTTP çağrısı

Kullanım:
    python server.py                  # Pi kamerası
    python server.py --simulation     # webcam (Mac)
    python server.py --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn

# ── Argümanlar ────────────────────────────────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GökKurt FastAPI Sunucu")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--source", default=0)
    p.add_argument("--simulation", action="store_true")
    return p.parse_args()

args = _parse_args()

import src.config as config

try:
    source: int | str = int(args.source)
except (ValueError, TypeError):
    source = args.source

# --simulation veya video dosyası → simülasyon modu (gerçek donanım yok)
if args.simulation or isinstance(source, str):
    config.SIMULATION_MODE = True

# ── Loglama ───────────────────────────────────────────────────────────────────
Path(config.LOG_DIR).mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("server")

# ── Servisler ─────────────────────────────────────────────────────────────────
from src.camera_service    import CameraService
from src.detector_service  import DetectorService
from src.tracker_service   import TrackerService
from src.servo_service     import ServoService
from src.alert_service     import AlertService
from src.qr_service        import QRService
from src.fsm_service       import FSMService, FSMState
from src.kamikaze_service  import KamikazeService
from src.telemetry_service import TelemetryService

camera    = CameraService(source=source)
detector  = DetectorService()
tracker   = TrackerService()

# Servo: Pi 5'te lgpio gerekli. Başlatılamazsa NullServo ile devam et.
class _NullServo:
    pan_angle = 90.0; tilt_angle = 90.0
    def update(self, *a, **kw): pass
    def center(self): pass
    def cleanup(self): pass

try:
    servo = ServoService()
except Exception as _e:
    logger.warning("Servo başlatılamadı (%s) — GPIO devre dışı.", _e)
    servo = _NullServo()

alert     = AlertService()
qr        = QRService()
fsm       = FSMService()
kamikaze  = KamikazeService()
telemetry = TelemetryService()

# ── Paylaşılan durum ──────────────────────────────────────────────────────────
_lock = threading.Lock()
_latest_frame: bytes | None = None
_latest_data: dict = {
    "detections":    [],
    "fps":           0.0,
    "tracker":       {},
    "qr":            None,
    "fsm":           {},
    "kamikaze":      {},
    "telemetry":     {},
}
_event_log: list[dict] = []   # Son N event
_MAX_EVENTS = 200


def _emit_event(level: str, source: str, message: str, **extra: Any) -> None:
    evt = {
        "ts":      time.time(),
        "level":   level,
        "source":  source,
        "message": message,
        **extra,
    }
    with _lock:
        _event_log.append(evt)
        if len(_event_log) > _MAX_EVENTS:
            del _event_log[: len(_event_log) - _MAX_EVENTS]


# ── Tespit döngüsü (arka plan thread) ─────────────────────────────────────────
def detection_loop() -> None:
    camera.start()
    logger.info("Kamera başlatıldı.")
    _emit_event("info", "system", "Kamera başlatıldı")

    prev_time = time.monotonic()
    last_qr_attempt = 0.0
    last_kamikaze_qr = ""
    _frame_counter = 0
    _last_detections: list = []
    DETECT_EVERY = 2   # Her N karede bir inference — Pi CPU tasarrufu

    while True:
        frame = camera.get_frame()
        if frame is None:
            time.sleep(0.01)
            continue

        h, w = frame.shape[:2]

        # Yüksek çözünürlüklü video için inference öncesi küçült
        if w > 640 or h > 480:
            infer_frame = cv2.resize(frame, (640, 480))
            ih, iw = 480, 640
        else:
            infer_frame = frame
            ih, iw = h, w

        # ── Tespit (her DETECT_EVERY karede bir) ───────────────────────────────
        _frame_counter += 1
        if _frame_counter % DETECT_EVERY == 0:
            detections = detector.detect(infer_frame)
            # bbox koordinatlarını orijinal boyuta ölçekle
            if (iw, ih) != (w, h):
                sx, sy = w / iw, h / ih
                for d in detections:
                    x1, y1, x2, y2 = d["bbox"]
                    d["bbox"] = (int(x1*sx), int(y1*sy), int(x2*sx), int(y2*sy))
            _last_detections = detections
        else:
            detections = _last_detections
        just_locked = tracker.update(
            detections,
            frame_center=(w // 2, h // 2),
            frame_size=(w, h),
        )

        # ── QR (sadece KILIT veya DALIS fazında çalışsın — CPU tasarrufu) ──────
        qr_result = None
        if fsm.state in (FSMState.DALIS, FSMState.KILIT) or fsm.state == FSMState.IDLE:
            now = time.monotonic()
            if now - last_qr_attempt >= 0.05:
                qr_result = qr.process(frame)
                last_qr_attempt = now

        # ── FSM güncelle ───────────────────────────────────────────────────────
        qr_decoded = qr_result is not None
        fsm.update(
            tracking      = tracker.is_tracking,
            criterion_met = tracker.criterion_met,
            is_locked     = tracker.is_locked,
            qr_decoded    = qr_decoded,
            kamikaze_ack  = kamikaze.acked,
        )

        # ── Servo takip mantığı ────────────────────────────────────────────────
        # KİLİT sağlandıysa servo pozisyonu koru (takibi bırak)
        # Tespit varsa ve henüz kilitlenmediyse takip et
        # Tespit yoksa merkeze dön
        try:
            if tracker.is_locked:
                pass  # Kilit aktif — mevcut açıyı koru, hareket etme
            elif detections:
                pan_err, tilt_err = tracker.get_pan_tilt_error(detections[0]["bbox"], w, h)
                servo.update(pan_err, tilt_err)
            else:
                servo.center()
        except Exception:
            pass

        if just_locked:
            alert.lock_achieved()
            _emit_event("success", "tracker",
                        f"◆ KİLİT TAMAMLANDI (bbox=%{tracker.bbox_ratio*100:.1f})",
                        bbox_ratio=tracker.bbox_ratio)
        elif tracker.is_tracking:
            alert.tracking_indicator(tracker.lock_progress)
        else:
            alert.lock_lost()

        # ── KILIT fazında QR varsa kamikaze paketi gönder ─────────────────────
        if (fsm.state == FSMState.KILIT
                and qr_result is not None
                and qr_result.data != last_kamikaze_qr):
            last_kamikaze_qr = qr_result.data
            kamikaze.send_async(
                qr_data=qr_result.data,
                lat=40.9018, lon=31.1795,        # Düzce kampüs örnek koordinat
                irtifa=30.0, hiz=18.0,
            )
            _emit_event("warning", "kamikaze",
                        f"Kamikaze paketi gönderiliyor: {qr_result.data[:40]}")

        # ── FPS + JPEG encode ──────────────────────────────────────────────────
        now = time.monotonic()
        fps = 1.0 / max(now - prev_time, 1e-6)
        prev_time = now

        # Stream için kare boyutunu sınırla
        stream_frame = cv2.resize(frame, (640, 480)) if (w > 640 or h > 480) else frame
        vis = _draw_overlay(stream_frame.copy(), detections, qr_result, fps)
        _, jpeg = cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 65])

        det_list = [
            {
                "bbox":       d["bbox"],
                "confidence": round(float(d["confidence"]), 3),
                "class":      d["class"],
                "score":      round(_target_score(d, w, h), 1),
            }
            for d in detections
        ]

        # Bileşik hedef seçim skoru (0-100) — en yüksek tespite göre
        best_score = det_list[0]["score"] if det_list else 0.0

        with _lock:
            global _latest_frame, _latest_data
            _latest_frame = jpeg.tobytes()
            _latest_data = {
                "detections":  det_list,
                "target_score": best_score,
                "fps":          round(fps, 1),
                "tracker": {
                    "tracking":      tracker.is_tracking,
                    "locked":        tracker.is_locked,
                    "lock_progress": round(tracker.lock_progress, 3),
                    "bbox_ratio":    round(tracker.bbox_ratio, 4),
                    "criterion_met": tracker.criterion_met,
                    "predicted":     tracker.predicted,
                    "lock_threshold": config.LOCK_BBOX_RATIO_MIN,
                    "lock_duration":  config.LOCK_DURATION,
                },
                "qr": ({
                    "data":       qr_result.data,
                    "polygon":    qr_result.polygon,
                    "bbox":       qr_result.bbox,
                    "confidence": qr_result.confidence,
                } if qr_result else None),
                "fsm":      fsm.to_dict(),
                "kamikaze": kamikaze.status.to_dict(),
                "frame": {"w": w, "h": h},
            }


def _target_score(det: dict, frame_w: int, frame_h: int) -> float:
    """Hedef seçim skoru (0–100).

    Bileşenler:
      • Güven skoru   (0–40 p) — model confidence
      • Bbox oran    (0–30 p) — %6 eşiğine yakınlık
      • Merkez yakınlığı (0–20 p) — frame merkezine uzaklık
      • Boyut skoru   (0–10 p) — tespit en az %4 alan kaplıyor mu
    """
    x1, y1, x2, y2 = det["bbox"]
    frame_area = max(1, frame_w * frame_h)
    bbox_area  = max(0, (x2 - x1)) * max(0, (y2 - y1))
    ratio      = bbox_area / frame_area

    # — Güven (0–40) ───────────────────────────────────────────────────────────
    conf_score = float(det["confidence"]) * 40.0

    # — Bbox oranı (0–30): %6'ya ne kadar yakın? ───────────────────────────────
    target_ratio = config.LOCK_BBOX_RATIO_MIN   # 0.06
    diff = abs(ratio - target_ratio)
    ratio_score = max(0.0, 30.0 - diff * 600.0)

    # — Merkez yakınlığı (0–20) ────────────────────────────────────────────────
    cx_det = (x1 + x2) / 2.0
    cy_det = (y1 + y2) / 2.0
    # normalize [0, 1] — 0 = mükemmel merkez, 1 = köşe
    dcx = abs(cx_det - frame_w / 2.0) / max(1, frame_w / 2.0)
    dcy = abs(cy_det - frame_h / 2.0) / max(1, frame_h / 2.0)
    center_score = max(0.0, 20.0 * (1.0 - (dcx + dcy) / 2.0))

    # — Boyut skoru (0–10) ─────────────────────────────────────────────────────
    size_score = 10.0 if ratio >= 0.04 else ratio / 0.04 * 10.0

    return min(100.0, conf_score + ratio_score + center_score + size_score)


def _draw_overlay(frame: np.ndarray, detections: list, qr_result, fps: float) -> np.ndarray:
    h, w = frame.shape[:2]

    # Kilitlenme dörtgeni (KTR §6: "kilitlenme dörtgeni ortada çizilir")
    # Görüntü merkezinde %6 alan = kenar = sqrt(0.06)*min(w,h) civarı
    side = int((config.LOCK_BBOX_RATIO_MIN ** 0.5) * min(w, h))
    cx, cy = w // 2, h // 2
    cv2.rectangle(frame, (cx - side, cy - side), (cx + side, cy + side),
                  (80, 180, 255), 1, cv2.LINE_AA)

    # Bounding box
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = f"{det['class']} {det['confidence']:.0%}"
        color  = (0, 0, 255) if tracker.is_locked else (0, 255, 0)
        thick  = 3 if tracker.is_locked else 2
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thick)
        cv2.putText(frame, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # QR polygon
    if qr_result is not None:
        pts = np.array(qr_result.polygon, dtype=np.int32)
        cv2.polylines(frame, [pts], True, (0, 230, 118), 2)
        cv2.putText(frame, f"QR: {qr_result.data[:30]}",
                    (pts[0][0], pts[0][1] - 6), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 230, 118), 2)

    # Lock HUD
    if tracker.is_locked:
        cv2.putText(frame, "◆ KILIT AKTIF", (w // 2 - 95, 30),
                    cv2.FONT_HERSHEY_DUPLEX, 0.9, (0, 0, 255), 2)
    elif tracker.criterion_met:
        pct = int(tracker.lock_progress * 100)
        cv2.putText(frame, f"Kilit: %{pct}", (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
        bar_w = int((w - 20) * tracker.lock_progress)
        cv2.rectangle(frame, (10, 50), (w - 10, 65), (50, 50, 50), -1)
        cv2.rectangle(frame, (10, 50), (10 + bar_w, 65), (0, 200, 255), -1)

    # EKF tahmin göstergesi
    if tracker.predicted:
        cv2.putText(frame, "EKF TAHMIN", (cx - 50, cy - side - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 60), 1, cv2.LINE_AA)

    # Hedef seçim skoru — en iyi tespite göre
    if detections:
        score = _target_score(detections[0], w, h)
        score_color = (0, 230, 118) if score >= 70 else (0, 200, 255) if score >= 40 else (100, 100, 255)
        cv2.putText(frame, f"SKOR: {score:.0f}/100", (10, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, score_color, 2, cv2.LINE_AA)
        # Mini skor çubuğu
        bar_total = w - 20
        bar_filled = int(bar_total * score / 100.0)
        cv2.rectangle(frame, (10, 72), (w - 10, 82), (40, 40, 40), -1)
        cv2.rectangle(frame, (10, 72), (10 + bar_filled, 82), score_color, -1)

    # FSM state
    cv2.putText(frame, f"FSM: {fsm.state.value}", (10, h - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    cv2.putText(frame, f"FPS: {fps:.1f} | bbox: %{tracker.bbox_ratio*100:.1f}",
                (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    return frame


# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(title="GökKurt API", version="2026.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _mjpeg_generator():
    while True:
        with _lock:
            frame = _latest_frame
        if frame is None:
            time.sleep(0.03); continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
        time.sleep(0.033)


@app.get("/stream")
def stream():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/status")
def get_status():
    with _lock:
        return _latest_data


@app.get("/api/system")
def get_system():
    return telemetry.snapshot()


@app.get("/api/events")
def get_events(limit: int = 50):
    with _lock:
        return list(_event_log[-limit:])


@app.get("/api/params")
def get_params():
    """Tüm config parametrelerini döndürür (Mission Planner tarzı)."""
    out = {}
    for key in dir(config):
        if key.startswith("_") or key.isupper() is False:
            continue
        val = getattr(config, key)
        if isinstance(val, (int, float, str, bool)) and not callable(val):
            out[key] = val
    return out


@app.patch("/api/params/{key}")
def update_param(key: str, body: dict):
    """Runtime'da parametre günceller. Diske YAZMAZ."""
    if not hasattr(config, key) or key.startswith("_"):
        raise HTTPException(404, f"Parameter '{key}' not found")
    new_val = body.get("value")
    current = getattr(config, key)
    try:
        # Tip dönüşümü
        if isinstance(current, bool):
            new_val = str(new_val).lower() in ("true", "1", "yes")
        elif isinstance(current, int):
            new_val = int(new_val)
        elif isinstance(current, float):
            new_val = float(new_val)
        elif isinstance(current, str):
            new_val = str(new_val)
    except Exception as e:
        raise HTTPException(400, f"Tip dönüşüm hatası: {e}")
    setattr(config, key, new_val)
    _emit_event("info", "params", f"Param güncellendi: {key} = {new_val}",
                key=key, value=new_val)
    return {"ok": True, "key": key, "value": new_val}


@app.post("/api/mission/start")
def mission_start():
    fsm.start_mission()
    _emit_event("info", "fsm", "Görev manuel başlatıldı (IDLE → INTIKAL)")
    return {"ok": True, "state": fsm.state.value}


@app.post("/api/mission/abort")
def mission_abort(body: dict | None = None):
    reason = (body or {}).get("reason", "Operatör manuel ABORT")
    fsm.abort(reason)
    _emit_event("error", "fsm", f"ABORT: {reason}")
    return {"ok": True, "state": fsm.state.value}


@app.post("/api/mission/reset")
def mission_reset():
    fsm.reset()
    tracker.reset()
    kamikaze.reset()
    _emit_event("info", "fsm", "Sistem reset edildi")
    return {"ok": True, "state": fsm.state.value}


# ── WebSocket ─────────────────────────────────────────────────────────────────
_ws_clients: list[WebSocket] = []
_ws_lock = asyncio.Lock()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    async with _ws_lock:
        _ws_clients.append(ws)
    logger.info("WebSocket bağlandı. Toplam: %d", len(_ws_clients))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with _ws_lock:
            if ws in _ws_clients:
                _ws_clients.remove(ws)
        logger.info("WebSocket ayrıldı. Toplam: %d", len(_ws_clients))


async def _broadcast_loop():
    """10 Hz ile tam telemetri akışı."""
    while True:
        await asyncio.sleep(0.1)
        if not _ws_clients:
            continue
        with _lock:
            payload = dict(_latest_data)
        payload["telemetry"] = telemetry.snapshot()
        with _lock:
            payload["events"] = list(_event_log[-15:])
        msg = json.dumps(payload, default=str)
        dead = []
        for ws in list(_ws_clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        if dead:
            async with _ws_lock:
                for ws in dead:
                    if ws in _ws_clients:
                        _ws_clients.remove(ws)


@app.on_event("startup")
async def startup():
    threading.Thread(target=detection_loop, daemon=True).start()
    asyncio.create_task(_broadcast_loop())
    logger.info("GökKurt sunucu başlatıldı (KTR 2026 v3 uyumlu).")
    _emit_event("info", "system", "Sunucu başlatıldı")


if __name__ == "__main__":
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
