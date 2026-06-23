"""
BricksInTheAir — GPIO Bridge

Watches I2CBus device state and translates changes into GPIODriver calls.
Call update() after each bus transaction and on the GUI poll tick.

Engine speed → propeller duty:
  Level 0 →  0%   Level 1 → 35%
  Level 2 → 50%   Level 3 → 65%   Level 4 → 80%   Level 5 → 100%
"""

import logging
import threading
import time

from devices import (
    GEAR_EXTENDED, GEAR_RETRACTED, GEAR_IN_TRANSIT,
    SEC_OPERATION_MODE,
)
from gpio_driver import FOG_PREHEAT_S

log = logging.getLogger(__name__)

# Engine level → propeller PWM duty (%)
SPEED_DUTY = {0: 0, 1: 35, 2: 50, 3: 65, 4: 80, 5: 100}

# Seconds the propeller runs at full throttle after ECU overspeed before cutting
OVERSPEED_RUNON_S = 6.0

# Gear motor duty — full power; timed stop is handled by GearDevice
GEAR_DUTY = 100.0


class GPIOBridge:
    """
    Diff-based bridge between simulated device state and physical GPIO.

    Usage:
        driver = GPIODriver()
        driver.setup()
        bridge = GPIOBridge(bus, driver)

        # after each bus transaction or on timer tick:
        bridge.update()

        # on shutdown:
        driver.cleanup()
    """

    def __init__(self, bus, driver):
        self._bus    = bus
        self._driver = driver

        # Shadow state — initialised to sentinel values to force a
        # full output sync on the first update() call.
        self._last_speed        = -1
        self._last_gear         = -1
        self._last_smoke_active = False
        self._last_smoke_popped = False
        self._last_emergency    = False
        self._last_ecu_smoke    = False
        self._overspeed_cutoff  = None   # time.time() + OVERSPEED_RUNON_S on ECU overflow

        # Background tick: expires smoke timers even with no I2C traffic
        threading.Thread(target=self._ticker, daemon=True, name="bridge-tick").start()

    def _ticker(self):
        while True:
            time.sleep(1.0)
            self._bus.fcc._check_smoke()
            self.update()

    def update(self):
        """Compare current device state against shadows and drive GPIO."""
        self._sync_emergency()
        self._sync_propeller()
        self._sync_gear()
        self._sync_fog()

    # ------------------------------------------------------------------
    # Emergency stop
    # ------------------------------------------------------------------

    def _sync_emergency(self):
        emergency = self._bus.fcc.emergency_stop
        if emergency and not self._last_emergency:
            self._driver.emergency_stop()
        if not emergency and self._last_emergency:
            # Coming out of emergency — force full re-sync on next tick
            self._last_speed        = -1
            self._last_gear         = -1
            self._last_smoke_active = False
            self._overspeed_cutoff  = None
        self._last_emergency = emergency

    # ------------------------------------------------------------------
    # Propeller
    # ------------------------------------------------------------------

    def _sync_propeller(self):
        if self._bus.fcc.emergency_stop:
            return
        ecu   = self._bus.ecu
        speed = ecu.engine_speed

        if ecu.smoke_active:
            # Start runon timer on first overflow detection
            if self._overspeed_cutoff is None:
                self._overspeed_cutoff = time.time() + OVERSPEED_RUNON_S
            # Full throttle during runon window, then cut
            speed = 5 if time.time() < self._overspeed_cutoff else 0
        else:
            self._overspeed_cutoff = None

        if speed == self._last_speed:
            return

        duty = SPEED_DUTY.get(speed, 0)
        self._driver.set_propeller(duty)
        self._last_speed = speed

    # ------------------------------------------------------------------
    # Landing gear
    # ------------------------------------------------------------------

    def _sync_gear(self):
        if self._bus.fcc.emergency_stop:
            return
        pos = self._bus.gear.gear_position

        if pos == self._last_gear:
            return

        if pos == GEAR_IN_TRANSIT:
            # GearDevice sets target via _transit_target — drive toward it
            target = getattr(self._bus.gear, '_transit_target', None)
            if target == GEAR_EXTENDED:
                self._driver.gear_down(GEAR_DUTY)
            elif target == GEAR_RETRACTED:
                self._driver.gear_up(GEAR_DUTY)
            else:
                log.warning("GEAR IN_TRANSIT but _transit_target unknown")
        elif pos == GEAR_EXTENDED:
            self._driver.gear_stop()
        elif pos == GEAR_RETRACTED:
            self._driver.gear_stop()

        self._last_gear = pos

    # ------------------------------------------------------------------
    # AFSS fog
    # ------------------------------------------------------------------

    def _sync_fog(self):
        if self._bus.fcc.emergency_stop:
            return
        fcc = self._bus.fcc
        ecu = self._bus.ecu

        # ECU overflow → activate FCC AFSS timer (one-shot, routes through
        # FCC so the 8s duration and stop signal are managed centrally)
        if ecu.smoke_active and not self._last_ecu_smoke:
            if not fcc.smoke_active:
                fcc.smoke_active      = True
                fcc.smoke_popped      = True
                # Offset start time by preheat so the FCC timer gives
                # SMOKE_DURATION_S of actual vapor, not preheat + vapor.
                fcc._smoke_start_time = time.time() + FOG_PREHEAT_S
        self._last_ecu_smoke = ecu.smoke_active

        # All fog is now FCC-managed; ecu.smoke_active only triggers the timer above
        smoke_active = fcc.smoke_active
        smoke_popped = fcc.smoke_popped

        # Fog just started
        if smoke_active and not self._last_smoke_active:
            presoak = (
                fcc._last_smoke_time is None or
                time.time() - fcc._last_smoke_time > fcc.SMOKE_IDLE_PRESOAK_S
            )
            self._driver.trigger_fog(presoak=presoak)

        # Fog just ended (FCC timer expired)
        if not smoke_active and self._last_smoke_active:
            self._driver.stop_fog()

        self._last_smoke_active = smoke_active
        self._last_smoke_popped = smoke_popped
