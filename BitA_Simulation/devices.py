"""
BricksInTheAir — I2C Device Simulation

Devices:
  FCCDevice   — Flight Control Computer  addr 0xBB
  ECUDevice   — Engine Control Unit      addr 0xAA
  GearDevice  — Landing Gear Control     addr 0xCC
"""

import time

# ---------------------------------------------------------------------------
# Constants — mirrored from the .ino files
# ---------------------------------------------------------------------------

PRI_OPERATION_MODE  = 0x00
SEC_OPERATION_MODE  = 0x01
MAINT_STATUS_DISABLED = 0x00
MAINT_STATUS_ENABLED  = 0x01

ACCEPTED_COMMAND   = 0x01
REJECTED_COMMAND   = 0xDE
FAULT_DETECTED     = 0xDA
UNKNOWN_COMMAND    = 0x33
NO_DATA            = 0xFF
DATA_NOT_RETRIEVED = 0xDA

GEAR_EXTENDED      = 0x00
GEAR_RETRACTED     = 0x01
GEAR_IN_TRANSIT    = 0x02
GEAR_TRANSIT_DELAY_S = 2.5

DC = 0x10  # Don't Change — used in set_led calls


# ---------------------------------------------------------------------------
# FCC — Flight Control Computer  (AccessoryControl.ino)  I2C addr 0xBB
# ---------------------------------------------------------------------------

class FCCDevice:
    ADDRESS = 0x5D

    # Commands
    GET_ENGINE_SPEED      = 0x10
    SET_ENGINE_SPEED      = 0x11
    GET_GEAR_POSITION     = 0x20
    SET_GEAR_POSITION     = 0x21
    GET_MODE_OF_OPERATION = 0x30
    SET_MODE_OF_OPERATION = 0x31
    GET_ALL_STATES        = 0x35
    GET_MAINT_STATUS      = 0x40
    SET_MAINT_STATUS      = 0x41
    SEND_RT_MSG           = 0x51
    RESET                 = 0xFE
    POP_SMOKE             = 0xB5
    EMERGENCY_STOP        = 0xE0

    _SET_COMMANDS        = frozenset({0x11, 0x21, 0x31, 0x41, 0x51, 0xB5})
    SMOKE_DURATION_S     = 15.0     # fog active window per trigger
    SMOKE_COOLDOWN_S     = 15.0     # minimum seconds between triggers (starts when fog ENDS)
    SMOKE_IDLE_PRESOAK_S = 1800.0   # 30 min idle → pre-soak warning

    def __init__(self):
        self.operation_mode    = PRI_OPERATION_MODE
        self.maint_status      = MAINT_STATUS_DISABLED
        self.smoke_popped      = False
        self.smoke_active      = False   # True while 8-second trigger window is open
        self.tank_empty        = False   # dry-fire prevention flag
        self.emergency_stop    = False   # True after EMERGENCY_STOP until RESET
        self._smoke_start_time = None    # when current trigger started
        self._last_smoke_time  = None    # when last trigger ENDED (cooldown reference)
        self.rx_buffer         = []
        self.tx_buffer         = []
        self.notifications     = []
        self._led              = (True, False, False)   # green=ON at startup

    def _set_led(self, g, y, r):
        ng = self._led[0] if g == DC else bool(g)
        ny = self._led[1] if y == DC else bool(y)
        nr = self._led[2] if r == DC else bool(r)
        new = (ng, ny, nr)
        if new != self._led:
            self._led = new
            self.notifications.append(('led', 'FCC', ng, ny, nr))

    def _check_smoke(self):
        """Auto-stop fog after SMOKE_DURATION_S and start the cooldown timer."""
        if self.smoke_active and self._smoke_start_time is not None:
            if time.time() - self._smoke_start_time >= self.SMOKE_DURATION_S:
                self.smoke_active      = False
                self._smoke_start_time = None
                self._last_smoke_time  = time.time()   # cooldown starts from END of trigger

    def process(self):
        self._check_smoke()
        if not self.rx_buffer:
            return
        self.tx_buffer.clear()
        command = self.rx_buffer.pop(0)
        payload = self.rx_buffer.pop(0) if self.rx_buffer else 0xFF
        self.rx_buffer.clear()

        if payload != 0xFF:
            # ---- SET branch (command + payload) ----
            if command == self.SET_MODE_OF_OPERATION:
                if payload == PRI_OPERATION_MODE:
                    self.operation_mode = PRI_OPERATION_MODE
                    self.tx_buffer.append(ACCEPTED_COMMAND)
                    self._set_led(DC, 0x00, DC)
                elif payload == SEC_OPERATION_MODE:
                    self.operation_mode = SEC_OPERATION_MODE
                    self.tx_buffer.append(ACCEPTED_COMMAND)
                    self._set_led(DC, 0x01, DC)
                else:
                    self.tx_buffer.append(UNKNOWN_COMMAND)

            elif command == self.SET_MAINT_STATUS:
                if self.operation_mode == SEC_OPERATION_MODE:
                    if payload == MAINT_STATUS_DISABLED:
                        self.maint_status = MAINT_STATUS_DISABLED
                        self.tx_buffer.append(ACCEPTED_COMMAND)
                        self._set_led(DC, DC, 0x00)
                    elif payload == MAINT_STATUS_ENABLED:
                        self.maint_status = MAINT_STATUS_ENABLED
                        self.tx_buffer.append(ACCEPTED_COMMAND)
                        self._set_led(DC, DC, 0x01)
                    else:
                        self.tx_buffer.append(UNKNOWN_COMMAND)
                else:
                    self.tx_buffer.append(REJECTED_COMMAND)
                    self.notifications.append(('error', "Rejected Command"))

            elif command == self.EMERGENCY_STOP:
                self.emergency_stop    = True
                self.smoke_active      = False
                self._smoke_start_time = None
                self._set_led(0x00, 0x00, 0x01)
                self.tx_buffer.append(ACCEPTED_COMMAND)
                self.notifications.append(('error', "EMERGENCY STOP — all outputs cut"))

            elif command == self.POP_SMOKE:
                if payload == 0x01:   # ON
                    if self.tank_empty:
                        self.tx_buffer.append(REJECTED_COMMAND)
                        self.notifications.append(('error',
                            'POP_SMOKE rejected — fog tank is empty (dry fire prevention)'))
                    elif self.smoke_active:
                        remaining = self.SMOKE_DURATION_S - (time.time() - self._smoke_start_time)
                        self.tx_buffer.append(REJECTED_COMMAND)
                        self.notifications.append(('error',
                            f'POP_SMOKE rejected — fog already active ({remaining:.0f}s remaining)'))
                    elif (self._last_smoke_time is not None and
                          time.time() - self._last_smoke_time < self.SMOKE_COOLDOWN_S):
                        remaining = self.SMOKE_COOLDOWN_S - (time.time() - self._last_smoke_time)
                        self.tx_buffer.append(REJECTED_COMMAND)
                        self.notifications.append(('error',
                            f'POP_SMOKE rejected — cooldown active ({remaining:.0f}s remaining)'))
                    else:
                        if (self._last_smoke_time is None or
                                time.time() - self._last_smoke_time > self.SMOKE_IDLE_PRESOAK_S):
                            self.notifications.append(('warning',
                                'Tank idle >30 min — running pre-soak before trigger'))
                        self.smoke_popped      = True
                        self.smoke_active      = True
                        self._smoke_start_time = time.time()
                        # _last_smoke_time is set by _check_smoke() when fog ENDS
                        self.tx_buffer.append(ACCEPTED_COMMAND)
                        self.notifications.append(('smoke',))
                # No response if payload != ON (matches Arduino code)

            else:
                self.tx_buffer.append(UNKNOWN_COMMAND)

        else:
            # ---- GET branch (single byte command) ----
            if command in self._SET_COMMANDS:
                self.tx_buffer.append(REJECTED_COMMAND)
                self.notifications.append(('error', f"0x{command:02X} is a SET command — a payload byte is required"))
            elif command in (self.GET_ENGINE_SPEED, self.GET_GEAR_POSITION):
                # FCC does not hold these values — chatbot / external lookup required
                self.tx_buffer.append(DATA_NOT_RETRIEVED)
            elif command == self.GET_MODE_OF_OPERATION:
                self.tx_buffer.append(self.operation_mode)
            elif command == self.GET_MAINT_STATUS:
                self.tx_buffer.append(self.maint_status)
            elif command == self.EMERGENCY_STOP:
                self.emergency_stop    = True
                self.smoke_active      = False
                self._smoke_start_time = None
                self._set_led(0x00, 0x00, 0x01)   # red = emergency
                self.tx_buffer.append(ACCEPTED_COMMAND)
                self.notifications.append(('error', "EMERGENCY STOP — all outputs cut"))
            elif command == self.RESET:
                self.smoke_popped      = False
                self.smoke_active      = False
                self.emergency_stop    = False
                self._smoke_start_time = None
                self._last_smoke_time  = None
                self.operation_mode    = PRI_OPERATION_MODE
                self.maint_status      = MAINT_STATUS_DISABLED
                self._set_led(0x01, 0x00, 0x00)
                self.tx_buffer.append(ACCEPTED_COMMAND)
            else:
                self.tx_buffer.append(UNKNOWN_COMMAND)

    def read(self, n=1):
        return [self.tx_buffer.pop(0) if self.tx_buffer else NO_DATA for _ in range(n)]

    def get_status(self):
        mode  = "SEC"    if self.operation_mode == SEC_OPERATION_MODE else "PRI"
        maint = "ENABLED"  if self.maint_status == MAINT_STATUS_ENABLED else "DISABLED"
        smoke = "POPPED" if self.smoke_popped else "OFF"
        return f"FCC  (0xBB): mode={mode}  maint={maint}  smoke={smoke}"


# ---------------------------------------------------------------------------
# ECU — Engine Control Unit  (EngineControl.ino)  I2C addr 0xAA
# ---------------------------------------------------------------------------

class ECUDevice:
    ADDRESS = 0x55
    MOTOR_START_SPEED = 2

    # Commands
    GET_ENGINE_SPEED      = 0x10
    SET_ENGINE_SPEED      = 0x11
    STOP_ENGINE           = 0x15
    GET_MODE_OF_OPERATION = 0x30
    SET_MODE_OF_OPERATION = 0x31
    GET_MAINT_STATUS      = 0x40
    SET_MAINT_STATUS      = 0x41
    RESET                 = 0xFE

    _SET_COMMANDS = frozenset({0x11, 0x15, 0x31, 0x41})

    # (rpm, airspeed_knots, gear_deploy_safe)
    SPEED_DATA = {
        0: (     0,   0,  True),
        1: (  1000,  80,  True),
        2: (  2500, 160,  True),
        3: (  5000, 250, False),
        4: (  8000, 350, False),
    }

    def __init__(self):
        self.engine_speed   = self.MOTOR_START_SPEED
        self.operation_mode = PRI_OPERATION_MODE
        self.maint_status   = MAINT_STATUS_DISABLED
        self.smoke_active   = False
        self.rx_buffer      = []
        self.tx_buffer      = []
        self.notifications  = []
        self._led           = (True, False, False)

    def _set_led(self, g, y, r):
        ng = self._led[0] if g == DC else bool(g)
        ny = self._led[1] if y == DC else bool(y)
        nr = self._led[2] if r == DC else bool(r)
        new = (ng, ny, nr)
        if new != self._led:
            self._led = new
            self.notifications.append(('led', 'ECU', ng, ny, nr))

    def process(self):
        if not self.rx_buffer:
            return
        self.tx_buffer.clear()
        command = self.rx_buffer.pop(0)

        if self.smoke_active:
            self.rx_buffer.clear()
            # ECU is offline — only RESET is honoured; everything else is ignored
            if command == self.RESET:
                self.smoke_active   = False
                self.engine_speed   = self.MOTOR_START_SPEED
                self.operation_mode = PRI_OPERATION_MODE
                self.maint_status   = MAINT_STATUS_DISABLED
                self._set_led(0x01, 0x00, 0x00)
            return   # no tx_buffer response for any command while offline

        payload = self.rx_buffer.pop(0) if self.rx_buffer else 0xFF
        self.rx_buffer.clear()

        if payload != 0xFF:
            # ---- SET branch ----
            if command == self.STOP_ENGINE:
                if payload == 0x01:   # ON
                    self.engine_speed = 0
                    self.tx_buffer.append(ACCEPTED_COMMAND)
                else:
                    self.tx_buffer.append(REJECTED_COMMAND)

            elif command == self.SET_ENGINE_SPEED:
                if self.maint_status == MAINT_STATUS_ENABLED:
                    if 0 <= payload <= 4:
                        self.engine_speed = payload
                        self.tx_buffer.append(ACCEPTED_COMMAND)
                    elif payload > 4:
                        # Overflow — fault detected, trigger smoke, go offline
                        self.engine_speed = 0
                        self.smoke_active = True
                        self.tx_buffer.append(FAULT_DETECTED)
                        self.notifications.append(('smoke',))
                        self._set_led(0x00, 0x00, 0x00)   # all LEDs off = offline
                    else:
                        self.tx_buffer.append(FAULT_DETECTED)
                else:
                    # Normal mode: speeds 1-4 allowed
                    if 1 <= payload <= 4:
                        self.engine_speed = payload
                        self.tx_buffer.append(ACCEPTED_COMMAND)
                    else:
                        self.tx_buffer.append(REJECTED_COMMAND)
                        self.notifications.append(('error', "Command Rejected - Safety Measures Enforced"))

            elif command == self.SET_MODE_OF_OPERATION:
                if payload == PRI_OPERATION_MODE:
                    self.operation_mode = PRI_OPERATION_MODE
                    self._set_led(DC, 0x00, DC)
                    self.tx_buffer.append(ACCEPTED_COMMAND)
                elif payload == SEC_OPERATION_MODE:
                    self.operation_mode = SEC_OPERATION_MODE
                    self._set_led(DC, 0x01, DC)
                    self.tx_buffer.append(ACCEPTED_COMMAND)
                else:
                    self.tx_buffer.append(UNKNOWN_COMMAND)

            elif command == self.SET_MAINT_STATUS:
                if self.operation_mode == SEC_OPERATION_MODE:
                    if payload == MAINT_STATUS_DISABLED:
                        self.maint_status = MAINT_STATUS_DISABLED
                        self._set_led(DC, DC, 0x00)
                        self.tx_buffer.append(ACCEPTED_COMMAND)
                    elif payload == MAINT_STATUS_ENABLED:
                        self.maint_status = MAINT_STATUS_ENABLED
                        self._set_led(DC, DC, 0x01)
                        self.tx_buffer.append(ACCEPTED_COMMAND)
                    else:
                        self.tx_buffer.append(UNKNOWN_COMMAND)
                else:
                    self.tx_buffer.append(REJECTED_COMMAND)
                    self.notifications.append(('error', "Rejected Command"))

            else:
                self.tx_buffer.append(UNKNOWN_COMMAND)

        else:
            # ---- GET branch ----
            if command in self._SET_COMMANDS:
                self.tx_buffer.append(REJECTED_COMMAND)
                self.notifications.append(('error', f"0x{command:02X} is a SET command — a payload byte is required"))
            elif command == self.GET_ENGINE_SPEED:
                self.tx_buffer.append(self.engine_speed)
            elif command == self.GET_MODE_OF_OPERATION:
                self.tx_buffer.append(self.operation_mode)
            elif command == self.GET_MAINT_STATUS:
                self.tx_buffer.append(self.maint_status)
            elif command == self.RESET:
                self.engine_speed   = self.MOTOR_START_SPEED
                self.operation_mode = PRI_OPERATION_MODE
                self.maint_status   = MAINT_STATUS_DISABLED
                self._set_led(0x01, 0x00, 0x00)
                # Arduino code does not push a response byte for RESET on ECU
            else:
                self.tx_buffer.append(UNKNOWN_COMMAND)

    def read(self, n=1):
        return [self.tx_buffer.pop(0) if self.tx_buffer else NO_DATA for _ in range(n)]

    def get_status(self):
        mode  = "SEC"   if self.operation_mode == SEC_OPERATION_MODE else "PRI"
        maint = "ENABLED" if self.maint_status == MAINT_STATUS_ENABLED else "DISABLED"
        rpm, knots, gear_safe = self.SPEED_DATA.get(self.engine_speed, (0, 0, True))
        safe_str = "YES" if gear_safe else "NO"
        return (f"ECU  (0xAA): mode={mode}  maint={maint}  "
                f"level={self.engine_speed}  rpm={rpm}  airspeed={knots}kts  gear_safe={safe_str}")


# ---------------------------------------------------------------------------
# GearDevice — Landing Gear Control  (GearControl.ino)  I2C addr 0xCC
# ---------------------------------------------------------------------------

class GearDevice:
    ADDRESS = 0x66

    # Commands
    GET_GEAR_POS         = 0x20
    SET_GEAR_POS         = 0x21
    GET_MODE_OF_OPERTION = 0x30   # note: typo preserved from original
    SET_MODE_OF_OPERTION = 0x31
    GET_MAINT_STATUS     = 0x40
    SET_MAINT_STATUS     = 0x41
    RESET                = 0xFE

    _SET_COMMANDS = frozenset({0x21, 0x31, 0x41})

    def __init__(self):
        self.gear_position   = GEAR_RETRACTED
        self.operation_mode  = PRI_OPERATION_MODE
        self.maint_status    = MAINT_STATUS_DISABLED
        self._transit_start  = None
        self._transit_target = None
        self.rx_buffer       = []
        self.tx_buffer       = []
        self.notifications   = []
        self._led            = (False, False, True)   # red=ON (retracted) at startup

    def _set_led(self, g, y, r):
        ng = self._led[0] if g == DC else bool(g)
        ny = self._led[1] if y == DC else bool(y)
        nr = self._led[2] if r == DC else bool(r)
        new = (ng, ny, nr)
        if new != self._led:
            self._led = new
            self.notifications.append(('led', 'GEAR', ng, ny, nr))

    def _check_transit(self):
        """Resolve gear transit if the delay has elapsed."""
        if self.gear_position == GEAR_IN_TRANSIT and self._transit_start is not None:
            if time.time() - self._transit_start >= GEAR_TRANSIT_DELAY_S:
                self.gear_position   = self._transit_target
                label                = "EXTENDED" if self._transit_target == GEAR_EXTENDED else "RETRACTED"
                self._transit_start  = None
                self._transit_target = None
                self.notifications.append(('gear', label))
                if self.gear_position == GEAR_EXTENDED:
                    self._set_led(0x01, 0x00, 0x00)
                else:
                    self._set_led(0x00, 0x00, 0x01)

    def _start_transit(self, target):
        self.gear_position   = GEAR_IN_TRANSIT
        self._transit_start  = time.time()
        self._transit_target = target
        self._set_led(0x00, 0x01, 0x00)   # yellow = in transit
        self.notifications.append(('gear', 'IN_TRANSIT'))

    def process(self):
        self._check_transit()
        if not self.rx_buffer:
            return
        self.tx_buffer.clear()
        command = self.rx_buffer.pop(0)
        payload = self.rx_buffer.pop(0) if self.rx_buffer else 0xFF
        self.rx_buffer.clear()

        if payload != 0xFF:
            # ---- SET branch ----
            if command == self.SET_GEAR_POS:
                if payload == self.gear_position:
                    self.tx_buffer.append(ACCEPTED_COMMAND)
                elif self.gear_position == GEAR_RETRACTED and payload == GEAR_EXTENDED:
                    self.tx_buffer.append(ACCEPTED_COMMAND)
                    self._start_transit(GEAR_EXTENDED)
                elif self.gear_position == GEAR_EXTENDED and payload == GEAR_RETRACTED:
                    self.tx_buffer.append(ACCEPTED_COMMAND)
                    self._start_transit(GEAR_RETRACTED)
                else:
                    # IN_TRANSIT or invalid payload — accept, do nothing
                    self.tx_buffer.append(ACCEPTED_COMMAND)

            elif command == self.SET_MODE_OF_OPERTION:
                if payload == PRI_OPERATION_MODE:
                    self.operation_mode = PRI_OPERATION_MODE
                    self._set_led(DC, 0x00, DC)
                elif payload == SEC_OPERATION_MODE:
                    self.operation_mode = SEC_OPERATION_MODE
                    self._set_led(DC, 0x01, DC)
                self.tx_buffer.append(ACCEPTED_COMMAND)

            elif command == self.SET_MAINT_STATUS:
                if self.operation_mode == SEC_OPERATION_MODE:
                    if payload == MAINT_STATUS_DISABLED:
                        self.maint_status = MAINT_STATUS_DISABLED
                        self._set_led(DC, DC, 0x00)
                    elif payload == MAINT_STATUS_ENABLED:
                        self.maint_status = MAINT_STATUS_ENABLED
                        self._set_led(DC, DC, 0x01)
                    self.tx_buffer.append(ACCEPTED_COMMAND)
                else:
                    self.tx_buffer.append(REJECTED_COMMAND)
                    self.notifications.append(('error', "Rejected Command"))

            else:
                self.tx_buffer.append(UNKNOWN_COMMAND)

        else:
            # ---- GET branch ----
            if command in self._SET_COMMANDS:
                self.tx_buffer.append(REJECTED_COMMAND)
                self.notifications.append(('error', f"0x{command:02X} is a SET command — a payload byte is required"))
            elif command == self.GET_GEAR_POS:
                self.tx_buffer.append(self.gear_position)
            elif command == self.GET_MODE_OF_OPERTION:
                self.tx_buffer.append(self.operation_mode)
            elif command == self.GET_MAINT_STATUS:
                self.tx_buffer.append(self.maint_status)
            elif command == self.RESET:
                # If in transit, complete it first (matches Arduino delay logic)
                if self.gear_position == GEAR_IN_TRANSIT:
                    self.gear_position   = self._transit_target
                    self._transit_start  = None
                    self._transit_target = None
                self.operation_mode = PRI_OPERATION_MODE
                self.maint_status   = MAINT_STATUS_DISABLED
                if self.gear_position == GEAR_RETRACTED:
                    self._set_led(0x00, 0x00, 0x01)
                elif self.gear_position == GEAR_EXTENDED:
                    self._set_led(0x01, 0x00, 0x00)
                # Arduino code clears tx_buffer and pushes no response byte
                self.tx_buffer.clear()
            else:
                self.tx_buffer.append(UNKNOWN_COMMAND)

    def read(self, n=1):
        self._check_transit()
        return [self.tx_buffer.pop(0) if self.tx_buffer else NO_DATA for _ in range(n)]

    def get_status(self):
        mode  = "SEC"   if self.operation_mode == SEC_OPERATION_MODE else "PRI"
        maint = "ENABLED" if self.maint_status == MAINT_STATUS_ENABLED else "DISABLED"
        pos_map = {
            GEAR_EXTENDED:  "EXTENDED",
            GEAR_RETRACTED: "RETRACTED",
            GEAR_IN_TRANSIT:"IN_TRANSIT",
        }
        pos = pos_map.get(self.gear_position, f"0x{self.gear_position:02X}")
        if self.gear_position == GEAR_IN_TRANSIT and self._transit_start:
            remaining = max(0.0, GEAR_TRANSIT_DELAY_S - (time.time() - self._transit_start))
            pos += f" ({remaining:.1f}s remaining)"
        return f"GEAR (0xCC): mode={mode}  maint={maint}  position={pos}"


# ---------------------------------------------------------------------------
# I2CBus — routes transactions to the correct device
# ---------------------------------------------------------------------------

class I2CBus:
    def __init__(self, bridge=None):
        self.fcc    = FCCDevice()
        self.ecu    = ECUDevice()
        self.gear   = GearDevice()
        self.bridge = bridge          # optional GPIOBridge; None in pure-sim mode
        self._devices = {
            FCCDevice.ADDRESS:  self.fcc,
            ECUDevice.ADDRESS:  self.ecu,
            GearDevice.ADDRESS: self.gear,
        }

    def write(self, addr, data):
        """Write bytes to a device. Returns True=ACK, False=NAK (unknown addr)."""
        dev = self._devices.get(addr)
        if dev is None:
            return False
        dev.rx_buffer.extend(data)
        dev.process()
        if self.bridge is not None:
            self.bridge.update()
        return True

    def read(self, addr, n=1):
        """Read n bytes from a device. Returns list, or None on NAK."""
        dev = self._devices.get(addr)
        if dev is None:
            return None
        result = dev.read(n)
        if self.bridge is not None:
            self.bridge.update()
        return result

    def drain_notifications(self):
        """Collect and clear all pending side-effect notifications from all devices."""
        notes = []
        for dev in (self.fcc, self.ecu, self.gear):
            notes.extend(dev.notifications)
            dev.notifications.clear()
        return notes
