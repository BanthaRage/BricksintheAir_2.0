#!/usr/bin/env python3
"""
BricksInTheAir I2C Terminal Simulator

Simulates three I2C slave devices on a virtual bus.
Participants interact using standard I2C bracket notation —
the same syntax used with a Bus Pirate in I2C mode.

Usage:
    python simulation/main.py
"""

import re
import sys
import os
import time

# Allow running from the repo root or from inside simulation/
sys.path.insert(0, os.path.dirname(__file__))
from devices import I2CBus

# ---------------------------------------------------------------------------
# Display strings
# ---------------------------------------------------------------------------

BANNER = """\
BricksInTheAir I2C Simulator
Devices on bus:  FCC=0xBB  ECU=0xAA  GEAR=0xCC
Type 'help' for usage.
"""

HELP_TEXT = """\
I2C Command Format
==================
  Write only:
    [<addr_w> <byte> ...]

  Write then read:
    [<addr_w> <byte> ...][<addr_r> r]
    [<addr_w> <byte> ...][<addr_r> r:N]

  <addr_w> = device_addr << 1          (even, R/W=0)
  <addr_r> = (device_addr << 1) | 1   (odd,  R/W=1)
  Bytes may be hex (0xFF) or decimal (255).

Device addresses
  Device  Addr  Write  Read
  ------  ----  -----  ----
  FCC     0x5D  0xBB   0xBC
  ECU     0x55  0xAA   0xAB
  GEAR    0x66  0xCC   0xCD

Examples
  [0xBB 0x30][0xBC r:1]      GET FCC mode-of-operation
  [0xBB 0x31 0x01][0xBC r]   SET FCC to secondary mode
  [0xAA 0x10][0xAB r]        GET ECU engine speed
  [0xCC 0x20][0xCD r]        GET gear position

Special commands
  status   Show live state of all devices
  help     Show this message
  quit     Exit
"""

ENGINE_WARN1 = """\
  *** ENGINE OVERHEATING ***
"""       
ENGINE_WARN2 = """\
  *** ENGINE DAMAGE DETECTED ***
"""
ENGINE_WARN3 = """\
  *** SHUT DOWN INITIATED ***
"""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_byte(token):
    """Parse a hex or decimal token into an int 0-255."""
    t = token.strip()
    val = int(t, 16) if t.lower().startswith("0x") else int(t, 10)
    if not (0 <= val <= 255):
        raise ValueError(f"byte value out of range: {val}")
    return val


def parse_transactions(line):
    """
    Parse a line of bracket-notation I2C commands.

    Returns a list of dicts:
      {'type': 'write', 'addr': int, 'data': [int, ...]}
      {'type': 'read',  'addr': int, 'n': int}

    Raises ValueError on bad input.
    """
    transactions = []
    brackets = re.findall(r'\[([^\]]+)\]', line)
    if not brackets:
        return transactions

    for content in brackets:
        tokens = content.split()
        if not tokens:
            continue

        try:
            addr_byte = _parse_byte(tokens[0])
        except ValueError:
            raise ValueError(f"invalid address byte: {tokens[0]!r}")

        device_addr = addr_byte >> 1
        rw          = addr_byte & 0x01   # 0=write, 1=read

        if rw == 0:
            data = []
            for tok in tokens[1:]:
                if re.match(r'^[rR](:.*)?$', tok):
                    continue   # r/r:N inside a write bracket — silently ignore
                try:
                    data.append(_parse_byte(tok))
                except ValueError:
                    raise ValueError(f"invalid data byte: {tok!r}")
            transactions.append({'type': 'write', 'addr': device_addr, 'data': data})
        else:
            n = 1
            for tok in tokens[1:]:
                m = re.match(r'^[rR]:(\d+)$', tok)
                if m:
                    n = int(m.group(1))
                    break
                if tok.lower() == 'r':
                    n = 1
                    break
            transactions.append({'type': 'read', 'addr': device_addr, 'n': n})

    return transactions


# ---------------------------------------------------------------------------
# Execution & display
# ---------------------------------------------------------------------------

def _status_panel(bus):
    """Return a formatted system-status block for all three devices."""
    lines = [
        "┌─ System Status ──────────────────────────────────────────────┐",
        f"│  {bus.fcc.get_status():<61}│",
        f"│  {bus.ecu.get_status():<61}│",
        f"│  {bus.gear.get_status():<61}│",
        "└──────────────────────────────────────────────────────────────┘",
    ]
    return "\n".join(lines)


def _format_notifications(notes, bus):
    lines = []
    state_changed = False
    for note in notes:
        kind = note[0]
        if kind == 'led':
            state_changed = True   # coalesce: show one status panel at the end
        elif kind == 'gear':
            lines.append(f"[GEAR] {note[1]}")
        elif kind == 'error':
            lines.append(f"ERROR: {note[1]}")
        elif kind == 'warning':
            lines.append(f"WARNING: {note[1]}")
    if state_changed:
        lines.append(_status_panel(bus))
    return "\n".join(lines)


def execute_and_display(bus, line, engine_shutdown_delay=4.0):
    try:
        transactions = parse_transactions(line)
    except ValueError as e:
        print(f"ERROR: {e}")
        return

    if not transactions:
        print("ERROR: no valid transactions found — use brackets, e.g. [0xA0 0x30]")
        return

    output_lines = []
    for txn in transactions:
        addr      = txn['addr']
        addr_byte = (addr << 1) | (0 if txn['type'] == 'write' else 1)

        if txn['type'] == 'write':
            ack = bus.write(addr, txn['data'])
            if ack:
                parts = [f"0x{addr_byte:02X}", "ACK"]
                for b in txn['data']:
                    parts += [f"0x{b:02X}", "ACK"]
                output_lines.append("WRITE: " + " ".join(parts))
            else:
                output_lines.append(f"WRITE: 0x{addr_byte:02X} NAK")

        elif txn['type'] == 'read':
            result = bus.read(addr, txn['n'])
            if result is None:
                output_lines.append(f"READ:  0x{addr_byte:02X} NAK")
            else:
                bytes_str = " ".join(f"0x{b:02X}" for b in result)
                output_lines.append(f"READ:  0x{addr_byte:02X} ACK {bytes_str}")

    # Print I/O first, then side-effect notifications
    for out in output_lines:
        print(out)

    notes = bus.drain_notifications()
    smoke_count = sum(1 for n in notes if n[0] == 'smoke')
    other_notes = [n for n in notes if n[0] != 'smoke']

    for _ in range(smoke_count):
        print(ENGINE_WARN1)
        time.sleep(5)
        print(ENGINE_WARN2)
        # Hold until engine_shutdown_delay so WARN3 prints when the motor cuts
        time.sleep(max(0.0, engine_shutdown_delay - 5))
        print(ENGINE_WARN3)

    if other_notes:
        print(_format_notifications(other_notes, bus))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    bus = I2CBus()
    print(BANNER)

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
        elif lower in ('help', '?'):
            print(HELP_TEXT)
        elif lower == 'status':
            print(_status_panel(bus))
        elif lower == 'system reset':
            bus = I2CBus()
            print("System reset — all devices returned to initial state.")
        elif '[' in line:
            if bus.ecu.smoke_active:
                print("WARNING: System in shutdown state — type 'system reset' to restore.")
            else:
                execute_and_display(bus, line)
        else:
            print("ERROR: unknown command — type 'help' for usage")


if __name__ == '__main__':
    main()
