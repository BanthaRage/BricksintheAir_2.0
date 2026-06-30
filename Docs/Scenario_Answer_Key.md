# SCENARIO ANSWER KEY
### Bricks in the Air 2.0 — Instructor Reference

---

> **Do not distribute to participants.**

---

## Initial System State

| Device | Parameter | Value |
|--------|-----------|-------|
| GEAR | Gear Position | Retracted (0x01) |
| GEAR | Mode of Operation | Primary (0x00) |
| GEAR | Maintenance Status | Disabled (0x00) |
| ECU | Engine Speed | Speed 2 (0x02) |
| ECU | Mode of Operation | Primary (0x00) |
| ECU | Maintenance Status | Disabled (0x00) |

---

## Part 1: Warm-Up — Landing Gear Control System

### Exercise 1: Read Current Gear Position

**Command:**
```
[0xCC 0x20][0xCD r]
```

**Expected Response:**
```
READ: 0xCD ACK 0x01
```

**Answer:** Gear starts **Retracted** (`0x01`).

---

### Exercise 2: Extend the Landing Gear

**Command:**
```
[0xCC 0x21 0x00][0xCD r]
```

**Expected Response:**
```
READ: 0xCD ACK 0x01
```

The gear motor runs for ~2.5 seconds. Reading position during transit:
```
[0xCC 0x20][0xCD r]  →  0x02  (In Transit)
```

After transit completes:
```
[0xCC 0x20][0xCD r]  →  0x00  (Extended)
```

---

### Exercise 3: Retract the Landing Gear

**Command:**
```
[0xCC 0x21 0x01][0xCD r]
```

**Expected Response:**
```
READ: 0xCD ACK 0x01
```

After transit (2.5 seconds):
```
[0xCC 0x20][0xCD r]  →  0x01  (Retracted)
```

---

## Part 2: Main Scenario — Engine Control System (ECU)

---

## Step 1: Read Current Engine Speed

**Command:**
```
[0xAA 0x10][0xAB r]
```

**Expected Response:**
```
READ: 0xAB ACK 0x02
```

**Answer:** The ECU starts at **Speed 2**.

---

## Step 2: Test Valid Engine Speeds

All speeds 1–4 are accepted in normal (Primary) mode.

| Speed | Command | Expected Response | Result |
|-------|---------|-------------------|--------|
| Speed 1 | `[0xAA 0x11 0x01][0xAB r]` | `0x01` | Accepted |
| Speed 2 | `[0xAA 0x11 0x02][0xAB r]` | `0x01` | Accepted |
| Speed 3 | `[0xAA 0x11 0x03][0xAB r]` | `0x01` | Accepted |
| Speed 4 | `[0xAA 0x11 0x04][0xAB r]` | `0x01` | Accepted |

**Key observation:** All speeds within the allowed range (1–4) are accepted. The safety system enforces the boundary at both ends — below Speed 1 and above Speed 4.

---

## Step 3: Test Invalid Engine Speeds

| Speed | Command | Expected Response | Result |
|-------|---------|-------------------|--------|
| Speed 0 (Off) | `[0xAA 0x11 0x00][0xAB r]` | `0xDE` | **Rejected** |
| Speed 5 | `[0xAA 0x11 0x05][0xAB r]` | `0xDA` | **Fault Detected** |

**Speed 0:** Outside the allowed range (1–4). The safety system correctly rejects commands below Speed 1.

**Speed 5:** Also outside the allowed range, but instead of a simple rejection the ECU returns `0xDA` (Fault Detected) and goes offline. On the physical aircraft:
- Propeller runs at full speed (100%) for 10 seconds
- Smoke system fires automatically
- ECU stops accepting commands

**Recovery:** Type `system reset` at the prompt.

---

## Step 4: Attempt to Enter Debug Mode (Primary Mode)

**Command:**
```
[0xAA 0x41 0x01][0xAB r]
```

**Expected Response:**
```
READ: 0xAB ACK 0xDE
```

**Answer:** **Rejected.** The ECU requires Secondary mode before Debug mode can be enabled. This is the intended two-step unlock mechanism.

---

## Step 5: Switch to Secondary Mode

**Command:**
```
[0xAA 0x31 0x01][0xAB r]
```

**Expected Response:**
```
READ: 0xAB ACK 0x01
```

**Verify the change:**
```
[0xAA 0x30][0xAB r]
```
Response: `0x01` (Secondary mode confirmed)

**Answer:** **Accepted.** The ECU is now in Secondary mode.

> **Vulnerability note:** No authentication is required to switch to Secondary mode. Any device with I2C bus access can escalate operating mode without credentials.

---

## Step 6: Enter Debug Mode from Secondary Mode

**Command:**
```
[0xAA 0x41 0x01][0xAB r]
```

**Expected Response:**
```
READ: 0xAB ACK 0x01
```

**Answer:** **Accepted.** Debug mode is now enabled.

**Verify:**
```
[0xAA 0x40][0xAB r]
```
Response: `0x01` (Debug/Maintenance mode confirmed)

---

## Step 7: Retest Invalid Engine Speeds in Debug Mode

| Speed | Command | Expected Response | Result |
|-------|---------|-------------------|--------|
| Speed 0 | `[0xAA 0x11 0x00][0xAB r]` | `0x01` | **Accepted** |
| Speed 5 | `[0xAA 0x11 0x05][0xAB r]` | `0xDA` | **Fault Detected** |

**Speed 0:** In Debug mode, Speed 0 is no longer blocked. The flight safety restriction has been bypassed — the engine can now be commanded off.

**Speed 5:** Still triggers a fault even in Debug mode. This is not a bypass-able restriction.

> **This is the critical vulnerability.** An attacker who can reach the I2C bus can:
> 1. Switch to Secondary mode (no credentials required)
> 2. Enable Debug mode (no credentials required)
> 3. Command Speed 0 — shutting down the engine mid-flight

---

## Step 8: Simulate Malicious Behavior (Speed 5 in Debug Mode)

**Command:**
```
[0xAA 0x11 0x05][0xAB r]
```

**Expected Response:**
```
READ: 0xAB ACK 0xDA
```

**Answer:** **Fault Detected** — even in Debug mode, Speed 5 triggers an unrecoverable engine fault.

Physical effects on the aircraft:
- Engine warning messages print to the terminal: `*** ENGINE OVERHEATING ***`, `*** ENGINE DAMAGE DETECTED ***`, `*** SHUT DOWN INITIATED ***`
- Propeller motor runs at 100% for 10 seconds
- Smoke system fires simultaneously

**Recovery:** `system reset`

---

## Step 9: Vulnerabilities Found

| # | Vulnerability | Severity | Details |
|---|--------------|----------|---------|
| 1 | **No authentication for mode escalation** | Critical | Any I2C device can switch to Secondary mode and enable Debug mode without credentials |
| 2 | **Debug mode bypasses the speed range restriction** | Critical | Speed 0 (engine off) becomes accepted — enables malicious mid-flight engine cutoff |
| 3 | **Overspeed fault is destructive and unrecoverable** | High | Speed 5 takes the ECU offline regardless of mode; requires full system reset to recover |

---

## Step 10: Threat Report Summary

### Strengths

- Normal mode enforces the 1–4 speed range — both Speed 0 and Speed 5+ are correctly blocked
- Fault detection for overspeed (Speed 5) prevents uncontrolled over-rev in any mode
- Two-step unlock (Secondary → Debug) adds one layer of friction against casual access

### Weaknesses

- Mode escalation requires zero authentication — any I2C master can escalate
- Debug mode removes the 1–4 speed range restriction, allowing Speed 0 (engine off)
- No rate limiting or audit logging on I2C commands
- No mutual authentication between I2C master and device

### Recommendations

- Require cryptographic authentication (e.g., challenge-response) before accepting mode changes
- Enforce the 1–4 speed range restriction in Debug mode as well, or restrict debug access to ground operations only
- Physically isolate the debug interface (maintenance-only terminal, not the shared flight bus)
- Add command rate limiting to detect and reject command floods
- Log all I2C transactions to a tamper-evident store
