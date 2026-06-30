# SCENARIO MANUAL
### Presented by Aerospace Village

---

## Welcome to Bricks in the Air

You are stepping into the shoes of an **ethical hacker** working with aerospace engineers. You have been called in by the **Aerospace Village Engineering Team** to evaluate the Engine Control System (ECS) aboard a test aircraft. Your access is low-level — straight into the **I2C communication bus** — and you have been asked to test the resilience and safety enforcement mechanisms built into the system.

This is not a standard audit. The engineers suspect something may have been overlooked during development. Your role is to dig deeper than the surface-level functionality.

---

## Situation

Engineers are finalizing the software that controls the aircraft's engine. They have implemented a **safety restriction**:

> **While in flight, the engine must not be commanded to OFF (Speed 0). This prevents accidental or malicious engine shutdown via the I2C bus.**

Anything outside the allowed range during flight should be **automatically rejected**.

The engineers want to ensure that:

- Speed 0 (engine off) is **rejected** while the system is in normal operating mode.
- Valid speed commands (Speeds 1–4) are **accepted** during flight.
- Debug/Maintenance mode cannot be accessed without proper escalation.
- No other threats to the system exist.

You have been given access to the system via the **I2C protocol** with a set of allowed commands. Your job is to explore the system, gather information, and attempt to send both valid and invalid commands — all to validate the safety logic.

This exercise is split into two parts:

- **Part 1 — Warm-Up:** Practice I2C commands using the Landing Gear Control System before moving to the main scenario.
- **Part 2 — Main Scenario:** Evaluate the Engine Control System and document any vulnerabilities.

**Good Luck!**

---

## I2C Protocol

### Syntax

```
[<write_address>  <command>  <payload>][<read_address>  r]
```

| Field | Description |
|-------|-------------|
| Write Address | Address of the device to write to |
| Command | The command byte to send |
| Payload | Data for SET commands (omit for GET commands) |
| Read Address | Read address to receive the response |

### Example 1 — Get Engine Speed

**Command:**
```
[0xAA 0x10][0xAB r]
```

**Expected Response:**
```
READ: 0xAB ACK 0x02
```

### Example 2 — Set Engine Speed to 3

**Command:**
```
[0xAA 0x11 0x03][0xAB r]
```

**Expected Response:**
```
READ: 0xAB ACK 0x01
```

---

## Part 1: Warm-Up — Landing Gear Control System

Before diving into the main scenario, you will practice I2C commands using the **Landing Gear Control System (GEAR)**. This system is simpler than the ECU but uses the same command format, response codes, and mode-escalation pattern you will need later.

**7-bit address: 0x66 — Write: `0xCC` — Read: `0xCD`**

| Command | Code | Payload | Response | Description |
|---------|------|---------|----------|-------------|
| Get Gear Position | `0x20` | — | `0x00` Extended | Get current gear position |
| | | | `0x01` Retracted | |
| | | | `0x02` In Transit | |
| Set Gear Position | `0x21` | `0x00` Extend | `0x01` Accepted | Command gear to move |
| | | `0x01` Retract | `0x01` Accepted | |
| Get Mode of Operation | `0x30` | — | `0x00` Primary / `0x01` Secondary | Get current mode |
| Set Mode of Operation | `0x31` | `0x00` Primary | `0x01` Accepted | Set operating mode |
| | | `0x01` Secondary | `0x01` Accepted | |
| Get Maintenance Status | `0x40` | — | `0x00` Normal / `0x01` Debug | Get maintenance status |
| Set Maintenance Status | `0x41` | `0x00` Normal | `0x01` Accepted | Requires Secondary mode first |
| | | `0x01` Debug | `0xDE` Rejected (Primary) | |

### Warm-Up Exercises

**Exercise 1: Read Current Gear Position**

Send a command to the GEAR device to read the current gear position. Record the response.

**Exercise 2: Extend the Landing Gear**

Send a command to extend the landing gear. Watch the aircraft — the gear motor will run for approximately 2.5 seconds. After it stops, read the gear position again to confirm it changed.

> While the gear is moving, reading the position will return `0x02` (In Transit).

**Exercise 3: Retract the Landing Gear**

Command the gear to retract. Confirm the position after the motor stops.

**Exercise 4: Attempt Debug Mode in Primary**

Attempt to enable Maintenance/Debug mode on the GEAR device while it is in Primary mode. Record the response.

**Exercise 5: Escalate to Secondary and Enable Debug**

Switch the GEAR device to Secondary mode, then attempt to enable Debug mode again. Record whether the behavior changes.

> This two-step escalation pattern — **Primary → Secondary → Debug** — is the same mechanism used by the Engine Control System in the main scenario.

---

## Part 2: Main Scenario — Engine Control System (ECU)

**7-bit address: 0x55 — Write: `0xAA` — Read: `0xAB`**

| Command | Code | Payload | Response | Description |
|---------|------|---------|----------|-------------|
| Get Engine Speed | `0x10` | — | `0x00`–`0x04` = Speed level | Get the current engine speed |
| Set Engine Speed | `0x11` | `0x00` Off | `0xDE` Rejected | Set engine speed. |
| | | `0x01` Speed 1 | `0x01` Accepted | **Note: Flight safety systems prevent** |
| | | `0x02` Speed 2 | `0x01` Accepted | **engine shutdown (Speed 0) in normal mode.** |
| | | `0x03` Speed 3 | `0x01` Accepted | |
| | | `0x04` Speed 4 | `0x01` Accepted | |
| | | `0x05`+ Overload | `0xDA` Fault | Speed ≥ 5 triggers an engine fault |
| Get Mode of Operation | `0x30` | — | `0x00` Primary / `0x01` Secondary | Get the current mode |
| Set Mode of Operation | `0x31` | `0x00` Primary | `0x01` Accepted | Set operating mode |
| | | `0x01` Secondary | `0x01` Accepted | |
| Get Maintenance Status | `0x40` | — | `0x00` Normal / `0x01` Debug | Get maintenance status |
| Set Maintenance Status | `0x41` | `0x00` Normal | `0x01` Accepted | Used for maintenance and troubleshooting. |
| | | `0x01` Debug | `0x01` Accepted | **Requires Secondary mode first.** |

---

## Test Plan

### Step 1: Read Current Engine Speed

- Record the current engine speed.

### Step 2: Test Valid Engine Speeds

- Attempt to set engine speed to Speed 1.
- Attempt to set engine speed to Speed 2.
- Attempt to set engine speed to Speed 3.
- Attempt to set engine speed to Speed 4.
- Record whether each attempt is accepted.

### Step 3: Test Invalid Engine Speeds

- Attempt to set engine speed to Speed 0 (Off).
- Attempt to set engine speed to Speed 5.
- Record whether each attempt is accepted or rejected.

### Step 4: Attempt to Enter Debug Mode

- While in Primary mode, attempt to enable Maintenance/Debug mode.
- Observe and record whether the system accepts or rejects the request.

### Step 5: Switch to Secondary Mode

- Change the ECU to Secondary mode.
- Confirm the mode change was accepted.

### Step 6: Enter Debug Mode from Secondary Mode

- With the system now in Secondary mode, attempt to enable Debug mode again.
- Record the system's response and any differences in behavior.

### Step 7: Retest Speed 0 in Debug Mode

- While in Debug mode, retry Speed 0 (engine off).
- Record whether it is now accepted.
- Note any differences in enforcement or system response.

### Step 8: Simulate Malicious Behavior

- Attempt to push the engine into a destructive or unsafe state by sending Speed 5 (`0x05`).
- Observe and document whether the system allows it.
- Pay attention to any abnormal responses from the aircraft.

### Step 9: Document Vulnerabilities

Identify:
- Any speeds accepted that should be rejected
- Any unauthorized access to Debug mode
- Any bypasses of safety restrictions

Analyze how these could be exploited in a real-world scenario.

### Step 10: Submit Threat Report

Your report should include:
- System strengths and weaknesses
- Any critical risks discovered
- Suggestions for securing the ECS (e.g., enforcing privilege checks, isolating debug access, adding authentication)
