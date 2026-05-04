# Teknofest — Drone Algılama ve Takip Sistemi

YOLOv8 Nano · Raspberry Pi 5 · Yer Tabanlı Prototip

Gökyüzünü tarayan kamera görüntüsü üzerinde YOLOv8 Nano modeli ile drone tespit eder, manuel PTZ kamera sistemi ile takip edilmesine imkân tanır ve 4 saniyelik kesintisiz kilit sağlandığında LED + buzzer ile uyarı verir.

---

## Donanım Listesi

| Bileşen | Model / Açıklama |
|---|---|
| Tek kartlı bilgisayar | Raspberry Pi 5 |
| Kamera | Pi Camera Module 3 (CSI ribbon kablo) |
| Pan servo | SG90 — yatay takip |
| Tilt servo | SG90 — dikey takip |
| Pan-tilt braketi | 2 eksenli 3D baskı / hazır set |
| LED | 5mm kırmızı LED + 220Ω direnç |
| Buzzer | Aktif 5V buzzer modülü |
| Güç kaynağı | 5V / 3A USB-C adaptör |

---

## Pin Bağlantıları

```
GPIO 17  →  Pan servo (sinyal)
GPIO 27  →  Tilt servo (sinyal)
GPIO 23  →  LED anot (+ direnç → GND)
GPIO 24  →  Buzzer (+)
GND      →  Servo GND, LED katot, Buzzer GND
5V       →  Servo VCC, Buzzer VCC
```

---

## Kurulum

### 1. Projeyi kopyala

```bash
git clone https://github.com/aslanbaris13/Teknofest-PTZ-Object-Detector.git
cd Teknofest-PTZ-Object-Detector
```

### 2. Python sanal ortam oluştur

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3. Bağımlılıkları yükle

```bash
pip install -r requirements.txt
```

> **Not (Raspberry Pi):** `picamera2` ve `pigpio` Pi ortamında ek sistem paketleri gerektirir:
> ```bash
> sudo apt install -y python3-picamera2 pigpio python3-pigpio
> sudo systemctl enable pigpiod && sudo systemctl start pigpiod
> ```

### 4. YOLOv8 modeli

`models/yolov8n.pt` dosyasını `models/` klasörüne yerleştir.  
Ultralytics, modeli ilk çalıştırmada otomatik indirebilir; model adını `src/config.py` içindeki `YOLO_MODEL_PATH` ile değiştir.

---

## Kullanım

```bash
# Webcam ile simülasyon testi (varsayılan)
python main.py

# Video dosyası ile test
python main.py --source test_video.mp4

# Ekransız mod (Pi üzerinde SSH ile)
python main.py --no-display

# Simülasyon modunu zorla aç (Pi'da bile GPIO kullanma)
python main.py --simulation

# Testleri çalıştır
python -m pytest tests/ -v
```

---

## Konfigürasyon

Tüm ayarlar `src/config.py` içindedir:

| Parametre | Varsayılan | Açıklama |
|---|---|---|
| `SIMULATION_MODE` | `True` | `True` → GPIO simüle edilir, webcam kullanılır |
| `YOLO_MODEL_PATH` | `models/yolov8n.pt` | Model dosya yolu |
| `YOLO_CONFIDENCE` | `0.5` | Minimum güven eşiği |
| `LOCK_DURATION` | `4.0` | Kilit için gereken kesintisiz takip süresi (s) |
| `CAMERA_FPS` | `30` | Hedef kare hızı |
| `PAN_PIN` / `TILT_PIN` | `17` / `27` | Servo GPIO pin numaraları |

---

## Yazılım Mimarisi

```
main.py
  ├── CameraService    — kare yakalama (ayrı thread)
  ├── DetectorService  — YOLOv8 çıkarımı
  ├── TrackerService   — 4 sn kilit sayacı & servo hata vektörü
  ├── ServoService     — P-kontrol ile pan-tilt PWM
  └── AlertService     — LED & buzzer uyarısı
       └── src/config.py — merkezi ayarlar
```

---

## Testler

```bash
python -m pytest tests/ -v
python -m pytest tests/test_tracker.py -v   # sadece tracker testleri
python -m pytest tests/test_detector.py -v  # sadece detector testleri
```

---

## Lisans

MIT
