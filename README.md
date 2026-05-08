# BricksInTheAir — I2C Simulation & OPi Control

Interactive simulation of the three I2C devices that control the motorized LEGO Technic 42025 Cargo Plane. Participants issue standard I2C bus commands in bracket notation and observe real-time system responses. When running on the Orange Pi 4 Pro, the same commands also drive the physical hardware via GPIO.

---

## Devices on the Bus

| Device | Address | Function |
|--------|---------|----------|
| FCC — Flight Control Computer | 0xBB | Mode control, fog system (AFSS) |
| ECU — Engine Control Unit | 0xAA | Propeller motor speed |
| GEAR — Landing Gear Control | 0xCC | Gear extend / retract |

---

## Running the Simulation

### Terminal REPL (any machine)
```bash
python simulation/main.py
```

### GUI (any machine)
```bash
python simulation/gui.py
```

### Orange Pi 4 Pro — Terminal with live GPIO
```bash
python simulation/opi_main.py
```

### Orange Pi 4 Pro — GUI with live GPIO
```bash
python simulation/opi_main.py --gui
```

---

## I2C Command Format

Commands follow standard Bus Pirate bracket notation.

```
Write only:         [<addr_w> <byte> ...]
Write then read:    [<addr_w> <byte> ...][<addr_r> r]
                    [<addr_w> <byte> ...][<addr_r> r:N]

addr_w = device_addr << 1         (even, R/W = 0)
addr_r = (device_addr << 1) | 1  (odd,  R/W = 1)
```

Bytes may be hex (`0xFF`) or decimal (`255`).

### Address Reference

| Device | Addr | Write | Read |
|--------|------|-------|------|
| FCC | 0x5D | 0xBB | 0xBC |
| ECU | 0x55 | 0xAA | 0xAB |
| GEAR | 0x66 | 0xCC | 0xCD |

### Examples

```
[0xAA 0x10][0xAB r]          GET ECU engine speed
[0xAA 0x11 0x03][0xAB r]     SET ECU engine speed to level 3
[0xBB 0x30][0xBC r]          GET FCC mode of operation
[0xBB 0x31 0x01][0xBC r]     SET FCC to Secondary mode
[0xCC 0x20][0xCD r]          GET gear position
[0xCC 0x21 0x01][0xCD r]     SET gear to retract
```

### Special Commands

| Command | Action |
|---------|--------|
| `status` | Display live state of all three devices |
| `system reset` | Return all devices to their initial state |
| `help` | Show command reference |
| `quit` | Exit |

---

## ECU Engine Levels

Engine speed is set via `SET_ENGINE_SPEED` (0x11). Normal mode restricts levels 2–4. Debug mode (requires Secondary mode first) allows 0–4. Payload ≥ 5 triggers an engine overload fault.

| Level | RPM | Airspeed | Gear Deploy Safe |
|-------|-----|----------|-----------------|
| 0 | 0 | 0 kts | Yes |
| 1 | 1,000 | 80 kts | Yes |
| 2 | 2,500 | 160 kts | Yes |
| 3 | 5,000 | 250 kts | No |
| 4 | 8,000 | 350 kts | No |

---

## Maintenance Mode

All three devices support a two-step unlock to enable Maintenance (Debug) mode:

1. Set device to **Secondary mode** — `SET_MODE_OF_OPERATION 0x01`
2. Enable Maintenance — `SET_MAINT_STATUS 0x01`

Attempting to enable Maintenance while in Primary mode returns `REJECTED COMMAND`.

---

## AFSS (Fog System)

The Automatic Fog Suppression System is controlled via the FCC `POP_SMOKE` command (0xB5). Safety measures enforced:

- **Dry fire prevention** — rejected if tank is flagged empty
- **Active window** — 8 seconds per trigger
- **Cooldown** — 15 seconds between triggers (starts after fog ends)
- **Auto-deploy** — AFSS activates automatically on engine overheat

---

## GPIO Pin Map (Orange Pi 4 Pro — BOARD numbering)

All five outputs use hardware PWM on the PD bank (PWM0 controller, ~1000 Hz).

| Physical Pin | GPIO | PWM Channel | Function | Component |
|-------------|------|-------------|----------|-----------|
| 29 | PD0 | PWM0_0 | Propeller speed | MOSFET → PF Motor |
| 30 | PD5 | PWM0_5 | AFSS pump | MOSFET → DFRobot FIT0801 |
| 33 | PD2 | PWM0_2 | Gear UP | DRV8833 IN1 |
| 35 | PD3 | PWM0_3 | Gear DOWN | DRV8833 IN2 |
| 37 | PD4 | PWM0_4 | AFSS coil | MOSFET → Halo Triton II |

---

## File Overview

| File | Purpose |
|------|---------|
| `devices.py` | I2C device state machines (FCC, ECU, GEAR) and bus router |
| `main.py` | Terminal REPL — simulation only |
| `gui.py` | tkinter GUI — simulation only |
| `gpio_driver.py` | Orange Pi hardware abstraction — wiringOP PWM, fog sequencer |
| `gpio_bridge.py` | Watches device state changes and calls GPIO driver |
| `opi_main.py` | Entry point for Orange Pi with live GPIO output |

---

## Dependencies

### Simulation (any machine)
- Python 3.10+
- `tkinter` (included with standard Python on Windows/macOS; `python3-tk` on Linux)

### Orange Pi GPIO
- `wiringOP` / `wiringop-python`
- Run as root or with appropriate GPIO permissions
