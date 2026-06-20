#!/usr/bin/env python3
"""
Quick GPIO diagnostic — run this first if motors don't respond.
Pulses GPIO12 at 50% duty for 5 seconds then stops.

    sudo python3 BitA_Simulation/gpio_test.py
"""

import time
import sys

try:
    import lgpio
except ImportError:
    print("FAIL: lgpio not importable — run: sudo apt install python3-lgpio")
    sys.exit(1)

GPIO_CHIP = 0
TEST_GPIO = 12

print(f"Opening gpiochip{GPIO_CHIP}...")
h = lgpio.gpiochip_open(GPIO_CHIP)
if h < 0:
    print(f"FAIL: gpiochip_open returned {h}")
    print("  → Try running with sudo")
    print("  → Or check: ls -la /dev/gpiochip*")
    sys.exit(1)
print(f"  OK (handle={h})")

print(f"Claiming GPIO{TEST_GPIO} as output...")
rc = lgpio.gpio_claim_output(h, TEST_GPIO, 0)
if rc < 0:
    print(f"FAIL: gpio_claim_output returned {rc}")
    lgpio.gpiochip_close(h)
    sys.exit(1)
print(f"  OK")

print(f"Starting PWM on GPIO{TEST_GPIO} at 50% / 1000 Hz for 5 seconds...")
rc = lgpio.tx_pwm(h, TEST_GPIO, 1000, 50.0)
if rc < 0:
    print(f"FAIL: tx_pwm returned {rc}")
    lgpio.gpiochip_close(h)
    sys.exit(1)
print(f"  OK — you should see activity on GPIO{TEST_GPIO} (Board pin 32) now")

time.sleep(5)

lgpio.tx_pwm(h, TEST_GPIO, 0, 0)
lgpio.gpio_write(h, TEST_GPIO, 0)
lgpio.gpiochip_close(h)
print("Done.")
