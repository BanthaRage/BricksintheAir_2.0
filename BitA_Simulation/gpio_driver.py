"""
BricksInTheAir — Orange Pi 4 Pro GPIO Driver

Abstracts wiringOP hardware calls behind a simple duty-cycle API.
Runs in mock mode (logging only) when wiringOP is not available,
so the simulation can import this safely on any machine.

Pin map (BOARD / physical numbering) — all hardware PWM, PD bank:
  Pin 29  PD0  PWM0_0  Propeller speed   MOSFET 1
  Pin 30  PD5  PWM0_5  AFSS pump         MOSFET 3
  Pin 33  PD2  PWM0_2  Gear UP           DRV8833 IN1
  Pin 35  PD3  PWM0_3  Gear DOWN         DRV8833 IN2
  Pin 37  PD4  PWM0_4  AFSS coil         MOSFET 2

All five outputs share the same PWM controller — one clock/range
configuration applies to all.

HW PWM clock: RK3399 PWM base clock is 24 MHz.
  For 1000 Hz with range=1024: clock_div = 24_000_000 / (1000 * 1024) ≈ 23
  Verify with: gpio readall  (wiringOP)
"""

import threading
import time
import logging

log = logging.getLogger(__name__)

try:
    import wiringpi
    _HW = True
except ImportError:
    _HW = False
    log.warning("wiringOP not found — GPIO driver running in mock mode")

# ---------------------------------------------------------------------------
# Pin assignments (BOARD / physical numbering)
# ---------------------------------------------------------------------------

PIN_PROP      = 29   # PD0  PWM0_0  Propeller
PIN_PUMP      = 30   # PD5  PWM0_5  AFSS pump
PIN_GEAR_UP   = 33   # PD2  PWM0_2  Gear UP   (DRV8833 IN1)
PIN_GEAR_DOWN = 35   # PD3  PWM0_3  Gear DOWN (DRV8833 IN2)
PIN_COIL      = 37   # PD4  PWM0_4  AFSS coil

_ALL_PWM_PINS = (PIN_PROP, PIN_PUMP, PIN_GEAR_UP, PIN_GEAR_DOWN, PIN_COIL)

# HW PWM: range=1024, clock_div=23 → ~1000 Hz on RK3399 24 MHz base clock
HW_PWM_RANGE = 1024
HW_PWM_CLOCK = 23

# ---------------------------------------------------------------------------
# Fog sequence parameters
# ---------------------------------------------------------------------------

COIL_START_DUTY        = 35
COIL_MAX_DUTY          = 50
PUMP_START_DUTY        = 45
FOG_PREHEAT_S          = 1.5
FOG_PURGE_S            = 0.4
COIL_IDLE_PRESOAK_DUTY = 10
COIL_IDLE_PRESOAK_S    = 2.0


# ---------------------------------------------------------------------------
# Duty-cycle helper
# ---------------------------------------------------------------------------

def _hw_value(pct: float) -> int:
    """Convert 0–100 % to 0–HW_PWM_RANGE integer."""
    return int(max(0.0, min(100.0, pct)) / 100.0 * HW_PWM_RANGE)


# ---------------------------------------------------------------------------
# GPIODriver
# ---------------------------------------------------------------------------

class GPIODriver:
    """
    Low-level GPIO interface.  All duty-cycle arguments are 0–100 %.
    Call setup() before use and cleanup() on shutdown.
    """

    def __init__(self):
        self._fog_thread: threading.Thread | None = None
        self._fog_stop   = threading.Event()
        self._ready      = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self):
        if not _HW:
            log.info("[MOCK] GPIO setup — all five pins are HW PWM (PD bank)")
            self._ready = True
            return

        wiringpi.wiringPiSetupPhys()

        for pin in _ALL_PWM_PINS:
            wiringpi.pinMode(pin, wiringpi.PWM_OUTPUT)

        wiringpi.pwmSetMode(wiringpi.PWM_MODE_MS)
        wiringpi.pwmSetClock(HW_PWM_CLOCK)
        wiringpi.pwmSetRange(HW_PWM_RANGE)

        for pin in _ALL_PWM_PINS:
            wiringpi.pwmWrite(pin, 0)

        self._ready = True
        log.info("GPIO setup complete — 5× HW PWM on PD bank")

    def cleanup(self):
        self._fog_stop.set()
        if self._fog_thread and self._fog_thread.is_alive():
            self._fog_thread.join(timeout=2.0)

        if _HW and self._ready:
            for pin in _ALL_PWM_PINS:
                wiringpi.pwmWrite(pin, 0)
            if hasattr(wiringpi, 'wiringPiCleanup'):
                wiringpi.wiringPiCleanup()

        self._ready = False
        log.info("GPIO cleanup complete")

    # ------------------------------------------------------------------
    # Internal write helper
    # ------------------------------------------------------------------

    def _write(self, pin: int, pct: float):
        val = _hw_value(pct)
        if _HW:
            wiringpi.pwmWrite(pin, val)
        else:
            log.debug("[MOCK] PWM pin %d → %.1f%% (%d/%d)", pin, pct, val, HW_PWM_RANGE)

    # ------------------------------------------------------------------
    # Propeller
    # ------------------------------------------------------------------

    def set_propeller(self, duty_pct: float):
        """Set propeller MOSFET duty cycle (0–100 %)."""
        self._write(PIN_PROP, duty_pct)
        log.info("Propeller → %.1f%%", duty_pct)

    # ------------------------------------------------------------------
    # Landing gear  (DRV8833 IN1 / IN2)
    # ------------------------------------------------------------------

    def gear_up(self, duty_pct: float = 100.0):
        """Drive DRV8833 IN1 high, IN2 low — motor extends gear."""
        self._write(PIN_GEAR_DOWN, 0)
        self._write(PIN_GEAR_UP,   duty_pct)
        log.info("Gear UP  → %.1f%%", duty_pct)

    def gear_down(self, duty_pct: float = 100.0):
        """Drive DRV8833 IN2 high, IN1 low — motor retracts gear."""
        self._write(PIN_GEAR_UP,   0)
        self._write(PIN_GEAR_DOWN, duty_pct)
        log.info("Gear DOWN → %.1f%%", duty_pct)

    def gear_stop(self):
        """Both IN1 and IN2 low — coast stop."""
        self._write(PIN_GEAR_UP,   0)
        self._write(PIN_GEAR_DOWN, 0)
        log.info("Gear STOP")

    # ------------------------------------------------------------------
    # AFSS fog sequence
    # ------------------------------------------------------------------

    def trigger_fog(self, presoak: bool = False):
        """
        Start the fog sequence in a background thread.
          [optional] coil at 10% for 2s  (idle presoak)
          coil at 35%
          wait 1.5s  (preheat)
          pump at 45%
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

        self._write(PIN_COIL, 0)
        time.sleep(FOG_PURGE_S)
        self._write(PIN_PUMP, 0)
        log.info("Fog stopped and purged")

    def _fog_sequence(self, presoak: bool):
        try:
            if presoak:
                log.info("Fog pre-soak: coil at %d%% for %.1fs",
                         COIL_IDLE_PRESOAK_DUTY, COIL_IDLE_PRESOAK_S)
                self._write(PIN_COIL, COIL_IDLE_PRESOAK_DUTY)
                if self._fog_stop.wait(timeout=COIL_IDLE_PRESOAK_S):
                    self._write(PIN_COIL, 0)
                    return

            self._write(PIN_COIL, COIL_START_DUTY)
            log.info("Fog preheat: coil at %d%%", COIL_START_DUTY)
            if self._fog_stop.wait(timeout=FOG_PREHEAT_S):
                self._write(PIN_COIL, 0)
                return

            self._write(PIN_PUMP, PUMP_START_DUTY)
            log.info("Fog active: coil %d%% + pump %d%%", COIL_START_DUTY, PUMP_START_DUTY)
            self._fog_stop.wait()

        finally:
            self._write(PIN_COIL, 0)
            self._write(PIN_PUMP, 0)
