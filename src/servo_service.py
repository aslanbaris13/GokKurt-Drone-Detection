"""
GökKurt — Drone Algılama ve Takip Sistemi
Servo servisi: Pan-tilt servo motorlarını P-kontrol ile yönlendirir.
Pi 5 uyumlu: /sys/class/pwm/ sysfs hardware PWM kullanır.
  - GPIO18 = TILT (pwm ch0)
  - GPIO19 = PAN  (pwm ch1)
Gereksinim: /boot/firmware/config.txt → dtoverlay=pwm-2chan
SIMULATION_MODE=True iken GPIO yerine log/print kullanır.
"""

import logging
import os
import time

from src import config

logger = logging.getLogger(__name__)

# P-kontrolör kazancı — hata (−1..+1) × KP → açı değişimi (derece)
KP: float = 0.08

# Servo PWM periyodu: 20ms = 50Hz
_PERIOD_NS: int = 20_000_000

# GPIO → hardware PWM kanal eşleşmesi (dtoverlay=pwm-2chan varsayılanı)
# GPIO18 → ch0,  GPIO19 → ch1
_GPIO_TO_CH: dict[int, int] = {18: 0, 19: 1}


class ServoService:
    """Pan-tilt servo motorlarını sysfs hardware PWM ile kontrol eden servis.

    Pi 5'te lgpio.tx_servo software PWM RP1 çipinde çalışmaz.
    Bu sınıf /sys/class/pwm/ arayüzünü kullanır.
    Servo açı → PWM: mikrosaniye = 500 + (açı / 180) × 2000
    """

    def __init__(self) -> None:
        self._pan_angle: float = float(config.PAN_CENTER)
        self._tilt_angle: float = float(config.TILT_CENTER)

        self._pan_path: str | None = None
        self._tilt_path: str | None = None

        if not config.SIMULATION_MODE:
            self._init_hardware_pwm()
        else:
            logger.info("[SIM] Servo servisi simülasyon modunda başlatıldı.")

        self.center()

    # ── Başlatma / Temizleme ─────────────────────────────────────────────────

    def _init_hardware_pwm(self) -> None:
        """sysfs hardware PWM kanallarını başlatır."""
        chip = self._find_pwm_chip()

        pan_ch  = _GPIO_TO_CH.get(config.PAN_PIN,  1)
        tilt_ch = _GPIO_TO_CH.get(config.TILT_PIN, 0)

        self._pan_path  = self._setup_channel(chip, pan_ch)
        self._tilt_path = self._setup_channel(chip, tilt_ch)

        logger.info(
            "Hardware PWM başlatıldı (pwmchip%d | PAN=ch%d GPIO%d | TILT=ch%d GPIO%d).",
            chip, pan_ch, config.PAN_PIN, tilt_ch, config.TILT_PIN,
        )

    def _find_pwm_chip(self) -> int:
        """En az 2 kanalı olan ilk pwmchip'i döner."""
        for num in range(8):
            base = f"/sys/class/pwm/pwmchip{num}"
            if not os.path.exists(base):
                continue
            try:
                with open(f"{base}/npwm") as f:
                    if int(f.read().strip()) >= 2:
                        logger.info("pwmchip%d bulundu.", num)
                        return num
            except Exception:
                pass
        raise RuntimeError(
            "Hiçbir hardware PWM chip bulunamadı.\n"
            "  /boot/firmware/config.txt içine şunu ekleyin:\n"
            "    dtoverlay=pwm-2chan\n"
            "  Sonra 'sudo reboot' yapın."
        )

    def _setup_channel(self, chip: int, channel: int) -> str:
        """PWM kanalını export edip 20ms periyot ayarlar. Kanal yolunu döner."""
        base = f"/sys/class/pwm/pwmchip{chip}"
        path = f"{base}/pwm{channel}"

        if not os.path.exists(path):
            with open(f"{base}/export", "w") as f:
                f.write(str(channel))
            time.sleep(0.15)

        # Periyot yazılabilmesi için önce devre dışı bırak
        try:
            with open(f"{path}/enable", "w") as f:
                f.write("0")
        except Exception:
            pass

        with open(f"{path}/period", "w") as f:
            f.write(str(_PERIOD_NS))

        logger.debug("PWM ch%d hazır: %s", channel, path)
        return path

    def cleanup(self) -> None:
        """PWM sinyalini durdurur."""
        for path in (self._pan_path, self._tilt_path):
            if path and os.path.exists(path):
                try:
                    with open(f"{path}/enable", "w") as f:
                        f.write("0")
                except Exception as exc:
                    logger.warning("PWM cleanup hatası (%s): %s", path, exc)
        logger.info("Servo PWM durduruldu.")

    # ── Servo Kontrolü ───────────────────────────────────────────────────────

    def update(self, pan_error: float, tilt_error: float) -> None:
        """P-kontrolör ile servo açılarını hata değerine göre günceller.

        Args:
            pan_error:  Normalize yatay hata (−1 … +1). Pozitif → sağ.
            tilt_error: Normalize dikey hata (−1 … +1). Pozitif → aşağı.
        """
        if config.PAN_INVERT:
            pan_error = -pan_error
        if config.TILT_INVERT:
            tilt_error = -tilt_error

        self._pan_angle  += KP * pan_error  * (config.PAN_MAX  - config.PAN_MIN)  / 2
        self._tilt_angle += KP * tilt_error * (config.TILT_MAX - config.TILT_MIN) / 2

        self._pan_angle  = max(config.PAN_MIN,  min(config.PAN_MAX,  self._pan_angle))
        self._tilt_angle = max(config.TILT_MIN, min(config.TILT_MAX, self._tilt_angle))

        self._apply_angles()

    def center(self) -> None:
        """Her iki servoyu merkez açısına getirir."""
        self._pan_angle  = float(config.PAN_CENTER)
        self._tilt_angle = float(config.TILT_CENTER)
        self._apply_angles()
        logger.debug("Servolar merkeze alındı (pan=%d, tilt=%d).",
                     config.PAN_CENTER, config.TILT_CENTER)

    # ── İç Yardımcılar ───────────────────────────────────────────────────────

    def _apply_angles(self) -> None:
        """Hesaplanan açıları donanıma veya simülasyon çıktısına yazar."""
        if config.SIMULATION_MODE:
            logger.debug("[SIM] Pan=%.1f°  Tilt=%.1f°", self._pan_angle, self._tilt_angle)
            return

        pan_us  = self._angle_to_us(self._pan_angle)
        tilt_us = self._angle_to_us(self._tilt_angle)

        if self._pan_path:
            self._write_pwm(self._pan_path, pan_us * 1000)
        if self._tilt_path:
            self._write_pwm(self._tilt_path, tilt_us * 1000)

        logger.info("PAN PWM: %d µs | TILT PWM: %d µs", pan_us, tilt_us)

    def _write_pwm(self, path: str, duty_ns: int) -> None:
        """duty_cycle ve enable yazar."""
        try:
            with open(f"{path}/duty_cycle", "w") as f:
                f.write(str(duty_ns))
            with open(f"{path}/enable", "w") as f:
                f.write("1")
        except Exception as exc:
            logger.warning("PWM yazma hatası (%s): %s", path, exc)

    @staticmethod
    def _angle_to_us(angle: float) -> int:
        """Derece → mikrosaniye.  0°=500µs  90°=1500µs  180°=2500µs"""
        return int(500 + (angle / 180.0) * 2000)

    # ── Salt Okunur Özellikler ────────────────────────────────────────────────

    @property
    def pan_angle(self) -> float:
        return self._pan_angle

    @property
    def tilt_angle(self) -> float:
        return self._tilt_angle
