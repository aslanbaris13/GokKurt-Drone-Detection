"""
GökKurt — Drone Algılama ve Takip Sistemi
Merkezi konfigürasyon modülü. Tüm sistem ayarları buradan yönetilir.

Şartname referansı: Savaşan İHA 2026 KTR §4 (Otonom Görevler) ve §6 (YKİ).
"""

# ─── Model Ayarları ───────────────────────────────────────────────────────────
YOLO_MODEL_PATH: str = "models/drone_v26_best.pt"   # YOLOv26n fine-tune — 18 epoch, mAP50=98% (epoch 15 best)
YOLO_CONFIDENCE: float = 0.5                  # Minimum güven eşiği (0.0 – 1.0)
YOLO_TARGET_CLASS: str = "drone"              # Hedef sınıf adı

# ─── Kamera Ayarları ─────────────────────────────────────────────────────────
CAMERA_WIDTH: int = 640
CAMERA_HEIGHT: int = 480
CAMERA_FPS: int = 30

# ─── Servo GPIO Pin Ayarları ─────────────────────────────────────────────────
PAN_PIN: int = 19     # Yatay servo BCM pin numarası  (fiziksel: GPIO19)
TILT_PIN: int = 18    # Dikey servo BCM pin numarası  (fiziksel: GPIO18)

PAN_CENTER: int = 90
TILT_CENTER: int = 90
PAN_MIN: int = 0
PAN_MAX: int = 180
TILT_MIN: int = 30
TILT_MAX: int = 150

# Servo yön düzeltmesi — fiziksel montaja göre ayarla
# True → o eksen tersine döner (hedef sağda → servo sola döner gibi davranıyorsa True yap)
PAN_INVERT:  bool = True   # Pan ters bağlı görünüyor (log: 90→180 runaway)
TILT_INVERT: bool = True   # Tilt ters bağlı görünüyor (log: 90→30 runaway)

# ─── Uyarı Donanımı GPIO Pinleri ─────────────────────────────────────────────
LED_PIN: int = 23
BUZZER_PIN: int = 24

# ─── Kilit Kriteri (KTR §4.1.3) ──────────────────────────────────────────────
# "hedefin bounding box alanının görüntü alanının yüzde 6-7'sini
#  4 saniye boyunca kesintisiz kaplaması"
LOCK_DURATION: float = 4.0           # Saniye (kesintisiz)
LOCK_BBOX_RATIO_MIN: float = 0.06    # %6 — şartname alt sınırı
LOCK_LOST_TIMEOUT: float = 0.5       # Hedef kaybı tolerans süresi (s)
LOCK_EKF_EXTRAPOLATION: float = 0.35 # EKF tahmin penceresi (s) — kısa kayıplarda bbox tahmin

# ─── QR Kod Ayarları (KTR §4.2.2) ────────────────────────────────────────────
QR_MIN_AREA: int = 800               # Aday QR çerçevesi minimum piksel alanı
QR_ADAPTIVE_BLOCK: int = 31          # Adaptive threshold blok boyutu (tek sayı)
QR_ADAPTIVE_C: int = 7               # Adaptive threshold C sabiti
QR_DECODE_INTERVAL: float = 0.1      # QR decode çağrı periyodu (s) — CPU tasarrufu

# ─── FSM Ayarları (KTR §4.2.1) ───────────────────────────────────────────────
FSM_DIVE_ALTITUDE: float = 100.0     # İNTİKAL → DALIŞ irtifa eşiği (m)
FSM_DIVE_RANGE: float = 150.0        # İNTİKAL → DALIŞ yatay mesafe (m)
FSM_LOCK_TIMEOUT: float = 8.0        # KİLİT fazı zaman aşımı (s)
FSM_PASS_DURATION: float = 2.0       # PAS_GEÇ tırmanış süresi (s)

# ─── Yarışma Sunucusu (KTR §6) ───────────────────────────────────────────────
COMP_SERVER_URL: str = "http://localhost:9000"   # Mock server URL
COMP_TEAM_ID: str = "GOKKURT"
COMP_RETRY_TIMEOUT: float = 3.0                  # ACK bekleme süresi (s)
COMP_MAX_RETRIES: int = 2                        # Toplam deneme = 1 + retry

# ─── Takip / Kilit Ayarları (Eski uyumluluk) ─────────────────────────────────
LOCK_DURATION_LEGACY: float = LOCK_DURATION

# ─── Loglama Ayarları ────────────────────────────────────────────────────────
LOG_DIR: str = "logs/"
LOG_FILE: str = "logs/detections.log"
EVENT_LOG_FILE: str = "logs/events.jsonl"

# ─── Simülasyon Modu ─────────────────────────────────────────────────────────
SIMULATION_MODE: bool = False  # True → --simulation flag ile override edilir
