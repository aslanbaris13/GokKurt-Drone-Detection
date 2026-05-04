#!/usr/bin/env python3
"""
Servo Fiziksel Bağlantı Test Scripti
=====================================
pwmchip0 / pwm2 (GPIO18, fiziksel pin 12) → TILT servo
pwmchip0 / pwm3 (GPIO19, fiziksel pin 35) → PAN  servo

Çalıştır:  sudo python3 servo_test.py
Durdur:    Ctrl+C
"""

import time
import os
import sys

# ── Ayarlar ───────────────────────────────────────────────────────────────────

CHIP      = 0          # pwmchip0
TILT_CH   = 2          # GPIO18 → pwm2
PAN_CH    = 3          # GPIO19 → pwm3
PERIOD_NS = 20_000_000 # 20ms = 50Hz

# Servo pozisyonları (mikrosaniye)
MIN_US  =  500   # 0°
MID_US  = 1500   # 90° (merkez)
MAX_US  = 2500   # 180°

# ── Yardımcı Fonksiyonlar ─────────────────────────────────────────────────────

def pwm_path(chip, ch):
    return f"/sys/class/pwm/pwmchip{chip}/pwm{ch}"

def export_channel(chip, ch):
    path = pwm_path(chip, ch)
    if not os.path.exists(path):
        try:
            with open(f"/sys/class/pwm/pwmchip{chip}/export", "w") as f:
                f.write(str(ch))
            time.sleep(0.15)
        except PermissionError:
            print(f"HATA: İzin reddedildi. 'sudo python3 servo_test.py' ile çalıştır.")
            sys.exit(1)

def write_pwm(chip, ch, duty_ns):
    path = pwm_path(chip, ch)
    try:
        with open(f"{path}/duty_cycle", "w") as f:
            f.write("0")  # önce sıfırla (period'dan büyük olamaz)
        with open(f"{path}/period", "w") as f:
            f.write(str(PERIOD_NS))
        with open(f"{path}/duty_cycle", "w") as f:
            f.write(str(duty_ns))
        with open(f"{path}/enable", "w") as f:
            f.write("1")
    except Exception as e:
        print(f"  HATA ({path}): {e}")

def disable_channel(chip, ch):
    path = pwm_path(chip, ch)
    try:
        with open(f"{path}/enable", "w") as f:
            f.write("0")
    except Exception:
        pass

def us_to_ns(us):
    return us * 1000

def move_both(pan_us, tilt_us, label):
    print(f"  → {label:12s}  PAN={pan_us}µs  TILT={tilt_us}µs")
    write_pwm(CHIP, PAN_CH,  us_to_ns(pan_us))
    write_pwm(CHIP, TILT_CH, us_to_ns(tilt_us))

# ── Ana Döngü ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 52)
    print("  GökKurt — Servo Fiziksel Bağlantı Testi")
    print("=" * 52)
    print(f"  PAN  → pwmchip{CHIP}/pwm{PAN_CH}  (GPIO19, pin 35)")
    print(f"  TILT → pwmchip{CHIP}/pwm{TILT_CH}  (GPIO18, pin 12)")
    print("  Durdurmak için: Ctrl+C")
    print()

    # Kanalları hazırla
    export_channel(CHIP, PAN_CH)
    export_channel(CHIP, TILT_CH)

    # Başlangıç: merkeze al
    print("[BAŞLANGIÇ] Merkeze alınıyor...")
    move_both(MID_US, MID_US, "MERKEZ")
    time.sleep(3)

    positions = [
        (MIN_US,  MIN_US,  "MİNİMUM (0°)"),
        (MID_US,  MID_US,  "MERKEZ  (90°)"),
        (MAX_US,  MAX_US,  "MAKSİMUM (180°)"),
        (MID_US,  MID_US,  "MERKEZ  (90°)"),
        (MAX_US,  MIN_US,  "PAN MAX / TILT MIN"),
        (MIN_US,  MAX_US,  "PAN MIN / TILT MAX"),
        (MID_US,  MID_US,  "MERKEZ  (90°)"),
    ]

    round_num = 1
    try:
        while True:
            print(f"\n--- Tur {round_num} ---")
            for pan_us, tilt_us, label in positions:
                move_both(pan_us, tilt_us, label)
                time.sleep(5)
            round_num += 1

    except KeyboardInterrupt:
        print("\n\n[DURDURULDU] Servolar merkeze alınıyor...")
        move_both(MID_US, MID_US, "MERKEZ")
        time.sleep(1)
        disable_channel(CHIP, PAN_CH)
        disable_channel(CHIP, TILT_CH)
        print("PWM durduruldu. Çıkılıyor.")

if __name__ == "__main__":
    main()
