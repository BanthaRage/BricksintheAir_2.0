#!/usr/bin/env python3
"""
GPIO diagnostic — pulses each output pin at 50% for 3 seconds.
Watch each connected module/load for activity as each pin fires.

    sudo python3 BitA_Simulation/gpio_test.py

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
    print("FAIL: lgpio not importable — run: sudo apt install python3-lgpio")
    sys.exit(1)

GPIO_CHIP = 0

PINS = [
    (12, "Propeller    (Board 32)"),
    (13, "AFSS pump    (Board 33)"),
    (16, "Gear UP      (Board 36)"),
    (20, "Gear DOWN    (Board 38)"),
    (21, "AFSS coil    (Board 40)"),
]

print(f"Opening gpiochip{GPIO_CHIP}...")
h = lgpio.gpiochip_open(GPIO_CHIP)
if h < 0:
    print(f"FAIL: gpiochip_open returned {h}")
    print("  -> Try running with sudo")
    sys.exit(1)
print(f"  OK (handle={h})\n")

for gpio, label in PINS:
    rc = lgpio.gpio_claim_output(h, gpio, 0)
    if rc < 0:
        print(f"FAIL: gpio_claim_output GPIO{gpio} returned {rc}")
        lgpio.gpiochip_close(h)
        sys.exit(1)

for gpio, label in PINS:
    print(f"Testing GPIO{gpio}  {label} -- 50% PWM for 3s ...")
    rc = lgpio.tx_pwm(h, gpio, 1000, 50.0)
    if rc < 0:
        print(f"  FAIL: tx_pwm returned {rc}")
    else:
        time.sleep(3)
        lgpio.tx_pwm(h, gpio, 0, 0)
        lgpio.gpio_write(h, gpio, 0)
        print(f"  Done")

lgpio.gpiochip_close(h)
print("\nAll pins tested.")
