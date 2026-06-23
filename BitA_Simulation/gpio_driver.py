"""
BricksInTheAir — Raspberry Pi 5 GPIO Driver

Abstracts lgpio hardware calls behind a simple duty-cycle API.
Runs in mock mode (logging only) when lgpio is not available,
so the simulation can import this safely on any machine.

Pin map (BCM / GPIO numbering) — software PWM via lgpio, 1000 Hz:
  GPIO12  Board 32  Propeller speed   MOSFET 1
  GPIO13  Board 33  AFSS pump         MOSFET 3
  GPIO16  Board 36  Gear UP           DRV8833 IN1
  GPIO20  Board 38  Gear DOWN         DRV8833 IN2
  GPIO21  Board 40  AFSS coil         MOSFET 2

RPi 5 confirmed as gpiochip0 on this unit. Verify with `gpioinfo` and
adjust GPIO_CHIP below if yours differs.
"""

import threading
import time
import logging

log = logging.getLogger(__name__)

try:
    import lgpio
    _HW = True
except ImportError:
    _HW = False
    log.warning("lgpio not found — GPIO driver running in mock mode")

# ---------------------------------------------------------------------------
# Pin assignments (BCM / GPIO numbering)
# ---------------------------------------------------------------------------

GPIO_CHIP     = 0      # Verify with `gpioinfo` — RPi 5 is typically gpiochip0

GPIO_PROP      = 12    # Board 32  Propeller
GPIO_PUMP      = 13    # Board 33  AFSS pump
GPIO_GEAR_UP   = 16    # Board 36  Gear UP   (DRV8833 IN1)
GPIO_GEAR_DOWN = 20    # Board 38  Gear DOWN (DRV8833 IN2)
GPIO_COIL      = 21    # Board 40  AFSS coil

_ALL_GPIO = (GPIO_PROP, GPIO_PUMP, GPIO_GEAR_UP, GPIO_GEAR_DOWN, GPIO_COIL)

PWM_FREQ_HZ = 1000     # software PWM frequency for all outputs

# ---------------------------------------------------------------------------
# Fog sequence parameters
# ---------------------------------------------------------------------------

# Coil is on 9V rail.  P = 81 × duty / 1.5 Ω = 54 × duty.
# Rated coil power 8.6 W → 16% duty.  20% = 10.8 W, 25% = 13.5 W.
COIL_START_DUTY        = 20   # 10.8 W on 9V — slightly above rated for reliable vaporization
COIL_MAX_DUTY          = 25   # 13.5 W hard ceiling
# Pump is on 5V rail; 75% ≈ 3.75 V average — good airflow without over-driving.
PUMP_START_DUTY        = 100
FOG_PREHEAT_S          = 3.0  # longer preheat needed at lower coil duty
FOG_PURGE_S            = 3.0
COIL_IDLE_PRESOAK_DUTY = 10
COIL_IDLE_PRESOAK_S    = 2.0


# ---------------------------------------------------------------------------
# GPIODriver
# ---------------------------------------------------------------------------

class GPIODriver:
    """
    Low-level GPIO interface.  All duty-cycle arguments are 0–100 %.
    Call setup() before use and cleanup() on shutdown.
    """

    def __init__(self):
        self._h: int | None  = None
        self._fog_thread: threading.Thread | None = None
        self._fog_stop   = threading.Event()
        self._ready      = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self):
        if not _HW:
            log.info("[MOCK] GPIO setup — 5× software PWM via lgpio (mock)")
            self._ready = True
            return

        h = lgpio.gpiochip_open(GPIO_CHIP)
        if h < 0:
            log.error("gpiochip_open(%d) failed: error %d — check permissions "
                      "(run with sudo, or add user to gpio group and re-login)",
                      GPIO_CHIP, h)
            return

        self._h = h

        for gpio in _ALL_GPIO:
            rc = lgpio.gpio_claim_output(self._h, gpio, 0)
            if rc < 0:
                log.error("gpio_claim_output GPIO%d failed: error %d", gpio, rc)

        for gpio in _ALL_GPIO:
            lgpio.gpio_write(self._h, gpio, 0)

        self._ready = True
        log.info("GPIO setup complete — 5× PWM @ %d Hz on gpiochip%d",
                 PWM_FREQ_HZ, GPIO_CHIP)

    def cleanup(self):
        self._fog_stop.set()
        if self._fog_thread and self._fog_thread.is_alive():
            self._fog_thread.join(timeout=2.0)

        if _HW and self._ready and self._h is not None:
            for gpio in _ALL_GPIO:
                self._write(gpio, 0)   # cancel any active tx_pwm before closing
            lgpio.gpiochip_close(self._h)
            self._h = None

        self._ready = False
        log.info("GPIO cleanup complete")

    # ------------------------------------------------------------------
    # Internal write helper
    # ------------------------------------------------------------------

    def _write(self, gpio: int, pct: float):
        pct = max(0.0, min(100.0, pct))
        if _HW and self._h is not None:
            if pct == 0.0:
                # Replace the running infinite wave with a single finite cycle,
                # then drive the pin LOW.  After 1 cycle (1 ms at 1 kHz) the
                # wave engine stops and gpio_write has nothing overriding it.
                try:
                    lgpio.tx_pwm(self._h, gpio, PWM_FREQ_HZ, 1.0, 0, 1)
                except Exception as e:
                    log.warning("tx_pwm stop GPIO%d: %s", gpio, e)
                lgpio.gpio_write(self._h, gpio, 0)
            elif pct == 100.0:
                # tx_pwm rejects 100% (0 µs OFF time = "bad PWM micros").
                # Hold the pin statically HIGH instead — identical electrically.
                lgpio.gpio_write(self._h, gpio, 1)
            else:
                rc = lgpio.tx_pwm(self._h, gpio, PWM_FREQ_HZ, pct)
                if rc < 0:
                    log.error("tx_pwm GPIO%d -> %.1f%% failed: error %d", gpio, pct, rc)
        else:
            log.debug("[MOCK] PWM GPIO%d -> %.1f%%", gpio, pct)

    # ------------------------------------------------------------------
    # Propeller
    # ------------------------------------------------------------------

    def set_propeller(self, duty_pct: float):
        """Set propeller MOSFET duty cycle (0–100 %)."""
        self._write(GPIO_PROP, duty_pct)
        log.info("Propeller → %.1f%%", duty_pct)

    # ------------------------------------------------------------------
    # Landing gear  (DRV8833 IN1 / IN2)
    # ------------------------------------------------------------------

    def gear_up(self, duty_pct: float = 100.0):
        """Drive DRV8833 IN1 high, IN2 low — motor extends gear."""
        self._write(GPIO_GEAR_DOWN, 0)
        self._write(GPIO_GEAR_UP,   duty_pct)
        log.info("Gear UP  → %.1f%%", duty_pct)

    def gear_down(self, duty_pct: float = 100.0):
        """Drive DRV8833 IN2 high, IN1 low — motor retracts gear."""
        self._write(GPIO_GEAR_UP,   0)
        self._write(GPIO_GEAR_DOWN, duty_pct)
        log.info("Gear DOWN → %.1f%%", duty_pct)

    def gear_stop(self):
        """Both IN1 and IN2 low — coast stop."""
        self._write(GPIO_GEAR_UP,   0)
        self._write(GPIO_GEAR_DOWN, 0)
        log.info("Gear STOP")

    # ------------------------------------------------------------------
    # AFSS fog sequence
    # ------------------------------------------------------------------

    def emergency_stop(self):
        """Cut all outputs immediately — no purge, no delay."""
        self._fog_stop.set()
        if self._fog_thread and self._fog_thread.is_alive():
            self._fog_thread.join(timeout=1.0)
        for gpio in _ALL_GPIO:
            try:
                self._write(gpio, 0)
            except Exception as e:
                log.error("emergency_stop GPIO%d write failed: %s", gpio, e)
        log.warning("EMERGENCY STOP — all GPIO outputs cut")

    def trigger_fog(self, presoak: bool = False):
        """
        Start the fog sequence in a background thread.
          pump on immediately (runs whenever coil is on)
          [optional] coil at 10% for 2s  (idle presoak)
          coil at 20% for 3s             (preheat)
          hold until stop_fog() is called
        """
        if self._fog_thread and self._fog_thread.is_alive():
            log.warning("trigger_fog called while fog already active — ignored")
            return

        self._fog_stop.clear()
        self._fog_thread = threading.Thread(
            target=self._fog_sequence,
            args=(presoak,),
            daemon=True,
            name="fog-sequence",
        )
        self._fog_thread.start()
        log.info("Fog sequence started (presoak=%s)", presoak)

    def stop_fog(self):
        """
        Signal the fog thread to stop, then purge:
          coil off → wait 0.4s → pump off
        """
        self._fog_stop.set()
        if self._fog_thread and self._fog_thread.is_alive():
            self._fog_thread.join(timeout=FOG_PREHEAT_S + FOG_PURGE_S + 0.5)

        self._write(GPIO_COIL, 0)
        time.sleep(FOG_PURGE_S)
        self._write(GPIO_PUMP, 0)
        log.info("Fog stopped and purged")

    def _fog_sequence(self, presoak: bool):
        try:
            self._write(GPIO_PUMP, PUMP_START_DUTY)
            log.info("Fog pump on: %d%%", PUMP_START_DUTY)

            if presoak:
                log.info("Fog pre-soak: coil at %d%% for %.1fs",
                         COIL_IDLE_PRESOAK_DUTY, COIL_IDLE_PRESOAK_S)
                self._write(GPIO_COIL, COIL_IDLE_PRESOAK_DUTY)
                if self._fog_stop.wait(timeout=COIL_IDLE_PRESOAK_S):
                    return

            self._write(GPIO_COIL, COIL_START_DUTY)
            log.info("Fog preheat: coil at %d%% for %.1fs", COIL_START_DUTY, FOG_PREHEAT_S)
            if self._fog_stop.wait(timeout=FOG_PREHEAT_S):
                return

            log.info("Fog active: coil %d%% + pump %d%%", COIL_START_DUTY, PUMP_START_DUTY)
            self._fog_stop.wait()

        finally:
            self._write(GPIO_COIL, 0)
            self._write(GPIO_PUMP, 0)
