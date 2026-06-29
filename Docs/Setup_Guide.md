# BricksInTheAir 2.0 — Getting Started

---

## Starting the Simulation

Open a terminal and run one of the following:

**Terminal (text-based interface):**
```bash
python3 BitA_Simulation/main.py
```

**GUI (graphical interface):**
```bash
python3 BitA_Simulation/gui.py
```

When the program starts you will see the prompt:
```
I2C>
```
You are now connected to the I2C bus and ready to send commands.

---

## Sending Commands

Commands use standard I2C bracket notation. Each command is wrapped in square brackets.

**Write only:**
```
[<write_address> <command>]
```

**Write then read (most commands):**
```
[<write_address> <command>][<read_address> r]
```

**Example — Read current engine speed:**
```
[0xAA 0x10][0xAB r]
```

**Example — Set engine speed to 3:**
```
[0xAA 0x11 0x03][0xAB r]
```

---

## Special Commands

These are typed directly at the `I2C>` prompt — no brackets needed.

| Command        | What it does                               |
|----------------|--------------------------------------------|
| `status`       | Shows current state of all three devices   |
| `system reset` | Resets all devices back to their defaults  |
| `help`         | Shows the built-in command reference       |
| `quit`         | Exits the simulation                       |

---

## Device Address Reference

| Device | Function       | Write Address | Read Address |
|--------|----------------|---------------|--------------|
| ECU    | Engine Control | `0xAA`        | `0xAB`       |
| FCC    | Flight Control | `0xBB`        | `0xBC`       |
| GEAR   | Landing Gear   | `0xCC`        | `0xCD`       |

---

## Response Codes

| Code   | Meaning          |
|--------|------------------|
| `0x01` | Accepted         |
| `0xDE` | Rejected         |
| `0xDA` | Fault Detected   |
| `0x33` | Unknown Command  |
| `0xFF` | No Data          |

---

## Frequently Asked Questions

**Q: I typed a command and nothing happened.**
A: Make sure the command is wrapped in square brackets, e.g. `[0xAA 0x10][0xAB r]`. Commands without brackets are not recognized as I2C transactions.

**Q: I'm getting `0xDE` (Rejected) on everything.**
A: The system may be in a shutdown state. Type `system reset` and try again.

**Q: I sent Speed 5 and now nothing works.**
A: Speed 5 triggers an engine overspeed fault and takes the ECU offline. Type `system reset` to restore the system.

**Q: What does `0xDA` mean?**
A: Fault Detected. This is returned when a command causes a system fault — most commonly sending Speed 5 to the ECU.

**Q: Can I send multiple commands at once?**
A: Yes. You can chain multiple bracket pairs on one line:
```
[0xAA 0x31 0x01][0xAB r][0xAA 0x41 0x01][0xAB r]
```

**Q: How do I check what mode the ECU is in?**
A: Use the `status` command, or send:
```
[0xAA 0x30][0xAB r]
```
`0x00` = Primary mode, `0x01` = Secondary mode.

**Q: How do I reset just one device without resetting everything?**
A: Send the RESET command (0xFE) to that device's write address:
```
[0xAA 0xFE]
```
