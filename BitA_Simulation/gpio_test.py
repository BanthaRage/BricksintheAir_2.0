#!/usr/bin/env python3
"""
GPIO diagnostic tool.

Usage:
    sudo python3 BitA_Simulation/gpio_test.py           # pulse all 5 pins individually
    sudo python3 BitA_Simulation/gpio_test.py --smoke   # run full fog cycle

Pin map:
    GPIO12  Board 32  Propeller
    GPIO13  Board 33  AFSS pump
    GPIO16  Board 36  Gear UP
    GPIO20  Board 38  Gear DOWN
    GPIO21  Board 40  AFSS coil
"""

import time
import sys

try:
    import lgpio
except ImportError:
    print("FAIL: lgpio not importable -- run: sudo apt install python3-lgpio")
    sys.exit(1)

GPIO_CHIP     = 0
GPIO_PROP     = 12
GPIO_PUMP     = 13
GPIO_GEAR_UP  = 16
GPIO_GEAR_DN  = 20
GPIO_COIL     = 21

PINS = [
    (GPIO_PROP,    "Propeller    (Board 32)"),
    (GPIO_PUMP,    "AFSS pump    (Board 33)"),
    (GPIO_GEAR_UP, "Gear UP      (Board 36)"),
    (GPIO_GEAR_DN, "Gear DOWN    (Board 38)"),
    (GPIO_COIL,    "AFSS coil    (Board 40)"),
]

# Fog sequence parameters
COIL_PRESOAK_DUTY = 10
COIL_PRESOAK_S    = 3.0
COIL_PREHEAT_DUTY = 45
COIL_PREHEAT_S    = 5.0
PUMP_DUTY         = 100
FOG_HOLD_S        = 10.0
FOG_PURGE_S       = 0.4


def open_chip():
    print(f"Opening gpiochip{GPIO_CHIP}...")
    h = lgpio.gpiochip_open(GPIO_CHIP)
    if h < 0:
        print(f"FAIL: gpiochip_open returned {h} -- try running with sudo")
        sys.exit(1)
    print(f"  OK (handle={h})\n")
    for gpio, _ in PINS:
        rc = lgpio.gpio_claim_output(h, gpio, 0)
        if rc < 0:
            print(f"FAIL: gpio_claim_output GPIO{gpio} returned {rc}")
            lgpio.gpiochip_close(h)
            sys.exit(1)
    return h


def pwm(h, gpio, duty):
    lgpio.tx_pwm(h, gpio, 1000, duty)


def stop(h, gpio):
    lgpio.gpio_write(h, gpio, 0)


def test_all_pins(h):
    """Pulse each pin at 50% for 3 seconds."""
    for gpio, label in PINS:
        print(f"Testing GPIO{gpio}  {label} -- 50% for 3s ...")
        pwm(h, gpio, 50.0)
        time.sleep(3)
        stop(h, gpio)
        print(f"  Done")
    print("\nAll pins tested.")


def test_smoke(h):
    """Run the full fog sequence: presoak -> preheat -> coil+pump -> purge."""
    try:
        print("Smoke cycle starting -- Ctrl+C to abort at any time\n")

        print(f"[1/4] Presoak  -- coil at {COIL_PRESOAK_DUTY}% for {COIL_PRESOAK_S}s ...")
        pwm(h, GPIO_COIL, COIL_PRESOAK_DUTY)
        time.sleep(COIL_PRESOAK_S)

        print(f"[2/4] Preheat  -- coil at {COIL_PREHEAT_DUTY}% for {COIL_PREHEAT_S}s ...")
        pwm(h, GPIO_COIL, COIL_PREHEAT_DUTY)
        time.sleep(COIL_PREHEAT_S)

        print(f"[3/4] Fog active -- coil {COIL_PREHEAT_DUTY}% + pump {PUMP_DUTY}% for {FOG_HOLD_S}s ...")
        pwm(h, GPIO_PUMP, PUMP_DUTY)
        time.sleep(FOG_HOLD_S)

        print(f"[4/4] Purge    -- coil off, pump running for {FOG_PURGE_S}s ...")
        stop(h, GPIO_COIL)
        time.sleep(FOG_PURGE_S)

    except KeyboardInterrupt:
        print("\nAborted.")
    finally:
        print("Stopping coil and pump.")
        stop(h, GPIO_COIL)
        stop(h, GPIO_PUMP)

    print("\nSmoke cycle complete.")


if __name__ == "__main__":
    smoke_mode = "--smoke" in sys.argv
    h = open_chip()
    try:
        if smoke_mode:
            test_smoke(h)
        else:
            test_all_pins(h)
    finally:
        lgpio.gpiochip_close(h)
