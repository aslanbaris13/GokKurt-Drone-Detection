"""
GökKurt — Drone Algılama ve Takip Sistemi
Alert servisi: Kilit durumuna göre LED ve buzzer uyarısı verir.
SIMULATION_MODE=True iken GPIO yerine terminal çıktısı kullanır.
"""

import logging
import threading
import time

from src import config

logger = logging.getLogger(__name__)


class AlertService:
    """LED ve buzzer ile kilit uyarısı veren servis.

    Simülasyon modunda terminale '[LED ON]', '[BUZZER BEEP]' vb. yazar.
    """

    def __init__(self) -> None:
        self._gpio = None   # RPi.GPIO modülü (gerçek mod)
        self._alert_thread: threading.Thread | None = None
        self._last_lock_state: bool | None = None   # spam önleme

        if not config.SIMULATION_MODE:
            self._init_gpio()
        else:
            logger.info("[SIM] Alert servisi simülasyon modunda başlatıldı.")

    # ── Başlatma / Temizleme ─────────────────────────────────────────────────

    def _init_gpio(self) -> None:
        """GPIO pinlerini çıkış olarak yapılandırır."""
        import RPi.GPIO as GPIO  # type: ignore[import]

        self._gpio = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.LED_PIN, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(config.BUZZER_PIN, GPIO.OUT, initial=GPIO.LOW)
        logger.info("Alert GPIO pinleri yapılandırıldı (LED=%d, BUZZER=%d).",
                    config.LED_PIN, config.BUZZER_PIN)

    def cleanup(self) -> None:
        """GPIO pinlerini sıfırlar ve kaynakları serbest bırakır."""
        if self._gpio is not None:
            self._gpio.output(config.LED_PIN, self._gpio.LOW)
            self._gpio.output(config.BUZZER_PIN, self._gpio.LOW)
            self._gpio.cleanup()
            logger.info("Alert GPIO temizlendi.")
        else:
            logger.info("[SIM] Alert servisi temizlendi.")

    # ── Uyarı Metodları ──────────────────────────────────────────────────────

    def lock_achieved(self) -> None:
        """4 saniyelik kilit tamamlandığında çağrılır.

        LED yakar + buzzer çalar (1 saniye, ayrı thread'de).
        """
        if self._last_lock_state is not True:
            logger.info("◆ Kilit uyarısı tetiklendi!")
            self._last_lock_state = True
        # Önceki uyarı thread'i bitmemişse yenisini başlatma
        if self._alert_thread and self._alert_thread.is_alive():
            return
        self._alert_thread = threading.Thread(
            target=self._buzz_and_light, args=(1.0,), daemon=True, name="AlertThread"
        )
        self._alert_thread.start()

    def lock_lost(self) -> None:
        """Kilit kaybedildiğinde LED ve buzzeri kapatır."""
        self._set_led(False)
        self._set_buzzer(False)
        if self._last_lock_state is not False:
            logger.info("Kilit kaybedildi — LED ve buzzer kapatıldı.")
            self._last_lock_state = False

    def tracking_indicator(self, progress: float) -> None:
        """Takip ilerleme durumuna göre LED'i yanıp söndürür.

        Args:
            progress: 0.0 (takip yok) – 1.0 (kilit tamamlandı).
        """
        if progress <= 0.0:
            self._set_led(False)
            return

        # İlerlemeye göre LED'i aç / kapat (yüksek ilerlemede sürekli açık)
        if progress >= 1.0:
            self._set_led(True)
        else:
            # Kaba yanıp sönme: progress < 0.5 → kapalı, >= 0.5 → açık
            blink_state = (int(time.monotonic() * (2 + progress * 4)) % 2) == 0
            self._set_led(blink_state)

    # ── İç Yardımcılar ───────────────────────────────────────────────────────

    def _buzz_and_light(self, duration: float) -> None:
        """LED yakar ve buzzer çalar, ardından söndürür."""
        self._set_led(True)
        self._set_buzzer(True)
        time.sleep(duration)
        self._set_led(False)
        self._set_buzzer(False)

    def _set_led(self, state: bool) -> None:
        if config.SIMULATION_MODE:
            label = "[LED ON] " if state else "[LED OFF]"
            # Sık çıktıyı azalt: sadece değişimde logla
            if getattr(self, "_last_led", None) != state:
                print(label, flush=True)
                self._last_led = state
        else:
            self._gpio.output(config.LED_PIN, self._gpio.HIGH if state else self._gpio.LOW)  # type: ignore[union-attr]

    def _set_buzzer(self, state: bool) -> None:
        if config.SIMULATION_MODE:
            label = "[BUZZER ON] " if state else "[BUZZER OFF]"
            if getattr(self, "_last_buzzer", None) != state:
                print(label, flush=True)
                self._last_buzzer = state
        else:
            self._gpio.output(config.BUZZER_PIN, self._gpio.HIGH if state else self._gpio.LOW)  # type: ignore[union-attr]
