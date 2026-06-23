#!/usr/bin/env python3
"""
BricksInTheAir — Raspberry Pi 5 entry point

Runs the full simulation with live GPIO output.
Use this script on the Raspberry Pi 5 instead of main.py or gui.py.

    python simulation/opi_main.py          # terminal REPL
    python simulation/opi_main.py --gui    # tkinter GUI
"""

import argparse
import logging
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from devices      import I2CBus, GEAR_RETRACTED, GEAR_TRANSIT_DELAY_S
from gpio_driver  import GPIODriver
from gpio_bridge  import GPIOBridge, OVERSPEED_RUNON_S

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def build_bus() -> I2CBus:
    driver = GPIODriver()
    driver.setup()
    bus    = I2CBus()
    bridge = GPIOBridge(bus, driver)
    bus.bridge = bridge
    bridge.update()   # sync initial device state (ECU speed 2 → propeller at 40%)

    # Retract gear on startup — confirms GPIO pins are live
    print("Retracting landing gear...")
    driver.gear_up(100.0)
    time.sleep(GEAR_TRANSIT_DELAY_S)
    driver.gear_stop()

    return bus, driver


def run_repl(bus):
    """Terminal REPL — same interface as main.py."""
    import main as m
    m.bus = bus
    print(m.BANNER)
    while True:
        try:
            line = input("I2C> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        lower = line.lower()
        if lower in ('quit', 'exit', 'q'):
            break
        elif lower == 'stop':
            bus.fcc.emergency_stop = True
            bus.fcc.smoke_active   = False
            bus.bridge.update()
            print("EMERGENCY STOP — all outputs cut. Send [0xBB 0xFE] or 'system reset' to restore.")
        elif lower in ('help', '?'):
            print(m.HELP_TEXT)
        elif lower == 'status':
            print(m._status_panel(bus))
        elif lower == 'system reset':
            bus.fcc  = type(bus.fcc)()
            bus.ecu  = type(bus.ecu)()
            bus.gear = type(bus.gear)()
            bus._devices = {
                bus.fcc.ADDRESS:  bus.fcc,
                bus.ecu.ADDRESS:  bus.ecu,
                bus.gear.ADDRESS: bus.gear,
            }
            bus.bridge._last_speed        = -1
            bus.bridge._last_gear         = -1
            bus.bridge._last_smoke_active = False
            bus.bridge._last_smoke_popped = False
            bus.bridge._last_emergency    = False
            bus.bridge._last_ecu_smoke    = False
            bus.bridge._overspeed_cutoff  = None
            bus.bridge.update()
            print("System reset — all devices returned to initial state.")
        elif '[' in line:
            if bus.ecu.smoke_active:
                print("WARNING: System in shutdown state — type 'system reset' to restore.")
            else:
                m.execute_and_display(bus, line, engine_shutdown_delay=OVERSPEED_RUNON_S)
                bus.bridge.update()
        else:
            print("ERROR: unknown command — type 'help' for usage")


def run_gui(bus):
    """tkinter GUI with GPIO bridge active."""
    import gui
    app = gui.App(bus=bus)
    app.mainloop()


def main():
    parser = argparse.ArgumentParser(description="BricksInTheAir OPi runner")
    parser.add_argument("--gui", action="store_true", help="Launch tkinter GUI")
    args = parser.parse_args()

    bus, driver = build_bus()
    try:
        if args.gui:
            run_gui(bus)
        else:
            run_repl(bus)
    finally:
        if bus.gear.gear_position != GEAR_RETRACTED:
            print("Parking landing gear...")
            driver.gear_up(100.0)
            time.sleep(GEAR_TRANSIT_DELAY_S)
        driver.cleanup()


if __name__ == "__main__":
    main()
