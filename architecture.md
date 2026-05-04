# GökKurt — Sistem Mimarisi ve Donanım Bağlantı Kılavuzu

---

## İçindekiler

1. [Genel Bakış](#1-genel-bakış)
2. [Donanım Listesi](#2-donanım-listesi)
3. [Raspberry Pi 5 GPIO Haritası](#3-raspberry-pi-4-gpio-haritası)
4. [Devre Bağlantıları](#4-devre-bağlantıları)
   - 4.1 Pan-Tilt Servo Bağlantısı
   - 4.2 LED Uyarı Devresi
   - 4.3 Buzzer Bağlantısı
   - 4.4 Pi Camera Module 3
5. [Güç Dağıtımı](#5-güç-dağıtımı)
6. [Yazılım Mimarisi](#6-yazılım-mimarisi)
   - 6.1 Katmanlar ve Sorumluluklar
   - 6.2 Veri Akışı
   - 6.3 Servisler Arası Arayüzler
7. [Durum Makinesi — Kilit Döngüsü](#7-durum-makinesi--kilit-döngüsü)
8. [Servo P-Kontrolör](#8-servo-p-kontrolör)
9. [Thread Modeli](#9-thread-modeli)
10. [Simülasyon Modu](#10-simülasyon-modu)

---

## 1. Genel Bakış

```
              ┌─────────────────────────────────┐
              │        Hedef Drone               │
              │       (Gökyüzünde)               │
              └────────────┬────────────────────┘
                           │ görüntü
                    ┌──────▼──────┐
                    │ Pi Camera Module 3 │  ← CSI ribbon kablo
                    │  (pan-tilt  │
                    │  brakette)  │
                    └──────┬──────┘
                           │ ham kare (RGB888)
          ┌────────────────▼────────────────────────┐
          │           Raspberry Pi 5          │
          │                                          │
          │  ┌──────────────────────────────────┐    │
          │  │  main.py — Ana Koordinasyon       │    │
          │  │  ┌──────────┐  ┌──────────────┐  │    │
          │  │  │ Camera   │  │  Detector    │  │    │
          │  │  │ Service  ├─►│  Service     │  │    │
          │  │  │ (thread) │  │  (YOLOv8n)   │  │    │
          │  │  └──────────┘  └──────┬───────┘  │    │
          │  │                       │ bbox      │    │
          │  │              ┌────────▼────────┐  │    │
          │  │              │ Tracker Service  │  │    │
          │  │              │ (4sn kilit sayaç)│  │    │
          │  │              └──┬──────────┬───┘  │    │
          │  │           hata  │          │kilit  │    │
          │  │        ┌────────▼──┐  ┌────▼────┐ │    │
          │  │        │  Servo    │  │  Alert  │ │    │
          │  │        │  Service  │  │  Service│ │    │
          │  │        └─────┬─────┘  └────┬────┘ │    │
          │  └────────────── │ ─────────── │ ─────┘    │
          │  GPIO 17,27      │             │ GPIO 23,24│
          └──────────────────┼─────────────┼───────────┘
                             │             │
                  ┌──────────▼───┐   ┌─────▼───────┐
                  │  Pan + Tilt  │   │ LED + Buzzer │
                  │  SG90 Servo  │   │  Uyarı Dev. │
                  └──────────────┘   └─────────────┘
```

---

## 2. Donanım Listesi

| # | Bileşen | Model | Adet | Notlar |
|---|---|---|---|---|
| 1 | Tek kartlı bilgisayar | Raspberry Pi 5 Model B | 1 | 64-bit ARM Cortex-A76 |
| 2 | Kamera | Raspberry Pi Camera Module 3 | 1 | 12 MP Sony IMX708, CSI |
| 3 | Pan servo | Tower Pro SG90 | 1 | 4.8V, 180° dönüş |
| 4 | Tilt servo | Tower Pro SG90 | 1 | 4.8V, 180° dönüş |
| 5 | Pan-tilt braketi | 2 eksenli alüminyum/plastik set | 1 | Kamera montajı dahil |
| 6 | LED | 5mm kırmızı difüz LED | 1 | 2V / 20mA |
| 7 | Direnç | 220 Ω ¼W | 1 | LED akım sınırlayıcı |
| 8 | Buzzer | Aktif 5V buzzer modülü | 1 | Dahili osilatör |
| 9 | Breadboard | Mini (170 nokta) veya tam boy | 1 | LED + buzzer devresi için |
| 10 | Jumper kablo | Dişi-erkek, erkek-erkek | ~15 | Renk kodlu kullanın |
| 11 | Güç kaynağı | 5V / 3A USB-C adaptör | 1 | Pi + servolara yetecek |
| 12 | MicroSD | 16 GB+ Class 10 / A1 | 1 | Raspberry Pi OS 64-bit |

---

## 3. Raspberry Pi 5 GPIO Haritası

Aşağıdaki tablo sistemin kullandığı pinleri gösterir. BCM numaralandırması kullanılmaktadır.

```
                          Raspberry Pi 5
                     ┌─────────────────────┐
               3.3V  │  1 ●   ● 2  │  5V
          SDA (GPIO2)│  3 ●   ● 4  │  5V
          SCL (GPIO3)│  5 ●   ● 6  │  GND  ──────── Ortak GND
                     │  7 ●   ● 8  │
               GND   │  9 ●   ● 10 │
                     │ 11 ●   ● 12 │
                     │ 13 ●   ● 14 │  GND
                     │ 15 ●   ● 16 │
               3.3V  │ 17 ●   ● 18 │
                     │ 19 ●   ● 20 │  GND
                     │ 21 ●   ● 22 │
                     │ 23 ●   ● 24 │
               GND   │ 25 ●   ● 26 │
                     │ 27 ●   ● 28 │
                     │ 29 ●   ● 30 │  GND
                     │ 31 ●   ● 32 │
  PAN SERVO ← GPIO17 │ 33 ●   ● 34 │  GND
                     │ 35 ●   ● 36 │
 TILT SERVO ← GPIO27 │ 37 ●   ● 38 │
               GND   │ 39 ●   ● 40 │
                     └─────────────────────┘

       Fiziksel  BCM    Fonksiyon
       ────────  ───    ─────────────────────
          11     17    Pan Servo PWM sinyali
          13     27    Tilt Servo PWM sinyali
          16     23    LED (anot, 220Ω ile)
          18     24    Buzzer (+)
           6      —    GND (servo ortak)
          25      —    GND (LED/buzzer ortak)
           4      —    5V  (servo VCC)
```

---

## 4. Devre Bağlantıları

### 4.1 Pan-Tilt Servo Bağlantısı

SG90 servo kablosu 3 telli gelir: **kahverengi = GND**, **kırmızı = VCC (+5V)**, **turuncu/sarı = sinyal**.

```
Pan Servo (SG90)                  Raspberry Pi 5
─────────────────                 ───────────────
Kahverengi (GND)  ──────────────► Pin 6   (GND)
Kırmızı    (VCC)  ──────────────► Pin 4   (5V)
Turuncu  (Sinyal) ──────────────► Pin 11  (GPIO 17)

Tilt Servo (SG90)                 Raspberry Pi 5
─────────────────                 ───────────────
Kahverengi (GND)  ──────────────► Pin 6   (GND)   [aynı ray]
Kırmızı    (VCC)  ──────────────► Pin 4   (5V)    [aynı ray]
Turuncu  (Sinyal) ──────────────► Pin 13  (GPIO 27)
```

> **Uyarı:** İki servo aynı 5V ve GND rayına bağlanabilir. Ancak yük altında toplam akım ~900mA'ya ulaşabilir. Pi'nın 5V pinleri USB-C güç kaynağından beslendiğinden **en az 3A adaptör** kullanın; yoksa Pi resetlenir.

**PWM parametreleri (pigpio):**

| Parametre | Değer |
|---|---|
| Frekans | 50 Hz (20 ms periyot) |
| Min darbe genişliği | 500 µs → 0° |
| Merkez darbe genişliği | 1500 µs → 90° |
| Max darbe genişliği | 2500 µs → 180° |
| Formül | `500 + (açı / 180) × 2000` µs |

---

### 4.2 LED Uyarı Devresi

```
Raspberry Pi 5                 Breadboard
──────────────                 ──────────
Pin 16 (GPIO 23) ──┬── 220Ω ──► LED Anot (+)
                   │
                   └────────────── (direnç sonrası)
Pin 25 (GND)     ──────────────► LED Katot (−) (kısa bacak)

Şematik:
GPIO23 ──[220Ω]──┤►├── GND
                 LED
```

> 3.3V GPIO çıkışı için akım: `(3.3V − 2.0V) / 220Ω ≈ 5.9mA` — LED için güvenli aralık.

---

### 4.3 Buzzer Bağlantısı

Aktif buzzer modülü (dahili osilatör) kullanılır; frekans üretmek gerekmez, sadece DC gerilim yeterlidir.

```
Raspberry Pi 5                 Buzzer Modülü
──────────────                 ─────────────
Pin 18 (GPIO 24) ──────────►  S / + (sinyal/VCC)
Pin 25 (GND)     ──────────►  − / GND
```

> Modülsüz çıplak buzzer kullanılıyorsa aynı bağlantı geçerlidir; transistör (2N2222/BC547) ile sürülmesi tavsiye edilir çünkü GPIO akımı (16mA maks) yetmeyebilir.

**Transistörlü güvenli sürücü devresi (isteğe bağlı):**

```
GPIO24 ──[1kΩ]──► BC547 Base
                  BC547 Collector ──► Buzzer (+) ──► 5V
                  BC547 Emitter   ──► GND
```

---

### 4.4 Pi Camera Module 3

```
Pi Camera Module 3                   Raspberry Pi 5
────────────                   ─────────────────────────────
CSI ribbon kablo ──────────►  CSI-2 kamera konektörü (CAMERA)
                               (DISPLAY konektörünün yanında,
                                15-pin FFC, metal yüzey Pi'ya bakmalı)
```

**Kablo takma adımları:**
1. Siyah plastik mandalı yukarı kaldırarak konektörü aç.
2. Mavi plastik yüz **HDMI portuna bakacak** şekilde kabloyu yerleştir.
3. Mandalı aşağı bastırarak kilitle.
4. Kameranın lens kapağını çıkar.

**Yazılımda etkinleştirme:**
```bash
sudo raspi-config
# → Interface Options → Camera → Enable
sudo reboot
```

---

## 5. Güç Dağıtımı

```
USB-C Adaptör (5V / 3A)
         │
         ▼
  Raspberry Pi 5
  ├── Pi Board        ~500mA
  ├── Pin 4 (5V) ──► Pan Servo   ~450mA (yük altında)
  ├── Pin 4 (5V) ──► Tilt Servo  ~450mA (yük altında)
  ├── GPIO 24    ──► Buzzer       ~30mA
  └── GPIO 23    ──► LED          ~6mA  (220Ω ile sınırlı)

Toplam (en kötü durum): ~1.4A
Tavsiye edilen adaptör : 3A (güvenlik payı ile)
```

> Servo sayısı arttırılacaksa veya daha büyük servo kullanılacaksa (MG90S, MG995 vb.) harici 5V BEC/regülatör önerilir; servo GND'sini Pi GND'ye bağlamayı unutmayın.

---

## 6. Yazılım Mimarisi

### 6.1 Katmanlar ve Sorumluluklar

```
┌─────────────────────────────────────────────────────┐
│                    main.py                           │
│         (Koordinasyon + Görselleştirme)              │
└────┬──────────┬──────────┬──────────┬───────────────┘
     │          │          │          │
     ▼          ▼          ▼          ▼
┌─────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐
│ Camera  │ │ Detector │ │Tracker │ │  Servo   │
│ Service │ │ Service  │ │Service │ │  Service │
│         │ │          │ │        │ │          │
│ Kare    │ │ YOLOv8n  │ │4sn kilit│ │P-kontrol │
│ yakalama│ │ çıkarımı │ │sayacı  │ │PWM       │
└─────────┘ └──────────┘ └───┬────┘ └──────────┘
                              │
                         ┌────▼─────┐
                         │  Alert   │
                         │  Service │
                         │ LED+buzz │
                         └──────────┘
                              │
                    ┌─────────▼──────────┐
                    │    src/config.py   │
                    │  (merkezi ayarlar) │
                    └────────────────────┘
```

### 6.2 Veri Akışı

```
Kamera
  │
  │  np.ndarray  (BGR, 640×480)
  ▼
DetectorService.detect(frame)
  │
  │  list[Detection]
  │  [{"bbox":(x1,y1,x2,y2), "confidence":0.9, "class":"drone"}, ...]
  ▼
TrackerService.update(detections, frame_center)
  │
  ├──► (pan_error, tilt_error)  float  −1.0 … +1.0
  │         │
  │         ▼
  │    ServoService.update(pan_err, tilt_err)
  │         │
  │         └──► GPIO PWM sinyali (pigpio)
  │
  └──► just_locked: bool
            │
            ▼
       AlertService.lock_achieved()  /  tracking_indicator(progress)
            │
            └──► GPIO LED + Buzzer
```

### 6.3 Servisler Arası Arayüzler

| Çağıran | Çağrılan | Metod | Girdi | Çıktı |
|---|---|---|---|---|
| main | CameraService | `get_frame()` | — | `np.ndarray \| None` |
| main | DetectorService | `detect(frame)` | BGR kare | `list[Detection]` |
| main | TrackerService | `update(dets, center)` | tespitler, (cx,cy) | `bool` (just_locked) |
| main | TrackerService | `get_pan_tilt_error(bbox,w,h)` | bbox, boyutlar | `(float, float)` |
| main | ServoService | `update(pan_err, tilt_err)` | −1…+1 hatalar | — |
| main | AlertService | `lock_achieved()` | — | — |
| main | AlertService | `tracking_indicator(progress)` | 0.0…1.0 | — |

---

## 7. Durum Makinesi — Kilit Döngüsü

```
           ┌─────────────┐
           │    IDLE     │◄──────────────────────────┐
           │ (Bekleniyor)│                            │
           └──────┬──────┘                            │
                  │ detection geldi                    │ timeout > 0.5s
                  ▼                                    │
           ┌─────────────┐                            │
           │  TRACKING   │◄──── detection devam ──────┤
           │ (Sayaç var) │                            │
           └──────┬──────┘                            │
                  │ elapsed >= 4.0s                    │
                  ▼                                    │
           ┌─────────────┐       detection kayboldu   │
           │   LOCKED    │───────────────────────────►┘
           │  (Uyarı!)   │       (tolerans > 0.5s)
           └─────────────┘

  Durum Değişkenleri:
  ┌─────────────────┬──────┬──────────┬────────┐
  │ Durum           │ is_  │ is_      │ lock_  │
  │                 │track │ locked   │progress│
  ├─────────────────┼──────┼──────────┼────────┤
  │ IDLE            │False │ False    │ 0.0    │
  │ TRACKING        │True  │ False    │ 0–1.0  │
  │ LOCKED          │True  │ True     │ 1.0    │
  └─────────────────┴──────┴──────────┴────────┘
```

---

## 8. Servo P-Kontrolör

```
Hedef bbox                Çerçeve merkezi
(cx_target, cy_target)    (cx_frame, cy_frame)
          │                       │
          └────────── Δ ──────────┘
                      │
             ┌────────▼────────┐
             │  Normalize hata  │
             │  e = Δ / (W/2)   │   −1.0 … +1.0
             └────────┬────────┘
                      │
             ┌────────▼────────┐
             │  P-Kontrolör     │
             │  Δθ = Kp × e     │   Kp = 0.3
             │     × (MAX−MIN)  │
             │     / 2          │
             └────────┬────────┘
                      │
             ┌────────▼────────┐
             │  Yeni açı        │
             │  θ = θ + Δθ      │
             │  clamp(min,max)  │
             └────────┬────────┘
                      │
             ┌────────▼────────┐
             │  PWM dönüşümü    │
             │  µs = 500 +      │
             │  (θ/180)×2000    │
             └────────┬────────┘
                      │
                    SG90 Servo
```

**Kp = 0.3** seçiminin gerekçesi: Küçük değer → aşım (overshoot) yok, salınım yok; daha hızlı tepki istiyorsanız 0.5'e kadar artırabilirsiniz.

---

## 9. Thread Modeli

```
Ana Thread (main.py döngüsü)
   │
   ├── YOLO çıkarımı  (~50-150ms / kare)
   ├── Tracker güncelle
   ├── Servo güncelle
   ├── Alert güncelle
   └── cv2.imshow / waitKey

CameraThread (daemon=True)
   └── _capture_loop(): sürekli kare yakalar
          │ threading.Lock ile korunur
          └── self._frame güncellenir

AlertThread (daemon=True, geçici)
   └── _buzz_and_light(1.0): kilit olayında 1sn yanar
```

Tüm thread'ler `daemon=True` olarak işaretlenmiştir; ana process sonlandığında otomatik ölürler. Kamera frame'i `threading.Lock` ile korunur, diğer servisler tek thread'den çalışır.

---

## 10. Simülasyon Modu

`SIMULATION_MODE = True` (varsayılan) ayarlandığında:

| Gerçek Donanım | Simülasyon Karşılığı |
|---|---|
| Pi Camera Module 3 (CSI) | `cv2.VideoCapture(0)` — webcam veya `--source` video |
| pigpio servo PWM | `logger.debug("[SIM] Pan=X° Tilt=Y°")` |
| RPi.GPIO LED | `print("[LED ON]")` / `print("[LED OFF]")` |
| RPi.GPIO Buzzer | `print("[BUZZER ON]")` / `print("[BUZZER OFF]")` |

**Masaüstünde test → Pi'ya geçiş adımları:**

```bash
# 1. config.py içinde değiştir:
SIMULATION_MODE = False

# 2. Pi ortamında ek paketleri kur:
sudo apt install -y python3-picamera2 pigpio python3-pigpio
pip install pigpio

# 3. pigpio daemon'u başlat:
sudo systemctl enable pigpiod && sudo systemctl start pigpiod

# 4. Çalıştır:
python main.py --no-display   # SSH ile ekransız
```
