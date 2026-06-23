#!/usr/bin/env python3
"""
BricksInTheAir I2C Simulator — Tkinter GUI

Two-pane layout:
  Left  — scrollable I2C output log + command entry (with history)
  Right — live status board for FCC, ECU, GEAR

Usage:
    python simulation/gui.py
"""

import tkinter as tk
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from devices import (
    I2CBus,
    PRI_OPERATION_MODE, MAINT_STATUS_DISABLED,
    GEAR_EXTENDED, GEAR_RETRACTED, GEAR_IN_TRANSIT, GEAR_TRANSIT_DELAY_S,
)
from main import parse_transactions, BANNER, HELP_TEXT, ENGINE_WARN1, ENGINE_WARN2, ENGINE_WARN3


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

class Theme:
    BG       = "#1e1e1e"
    BG_PANEL = "#252526"
    BG_INPUT = "#3c3c3c"
    FG       = "#d4d4d4"
    FG_DIM   = "#858585"
    ACCENT   = "#569cd6"
    GREEN    = "#4ec994"
    YELLOW   = "#dcdcaa"
    RED      = "#f44747"
    CYAN     = "#9cdcfe"
    BORDER   = "#3c3c3c"

    FONT_MONO  = ("Courier New", 11)
    FONT_SANS  = ("Segoe UI",     9)
    FONT_BOLD  = ("Segoe UI",     9, "bold")
    FONT_TITLE = ("Segoe UI",    10, "bold")


# ---------------------------------------------------------------------------
# StatusPanel — one device card in the right pane
# ---------------------------------------------------------------------------

class StatusPanel(tk.LabelFrame):
    """Live status card for a single I2C device."""

    def __init__(self, parent, title, **kw):
        super().__init__(
            parent,
            text=f"  {title}  ",
            fg=Theme.FG,
            bg=Theme.BG_PANEL,
            font=Theme.FONT_TITLE,
            bd=1,
            relief="solid",
            padx=10,
            pady=6,
            **kw,
        )
        self._rows   = {}       # key -> tk.Label (value widget)
        self._canvas = None
        self._dot    = None
        self._build_indicator_row()

    def _build_indicator_row(self):
        row = tk.Frame(self, bg=Theme.BG_PANEL)
        row.pack(fill="x", pady=(0, 4))

        tk.Label(row, text="LED", width=11, anchor="w",
                 fg=Theme.FG_DIM, bg=Theme.BG_PANEL,
                 font=Theme.FONT_SANS).pack(side="left")

        self._canvas = tk.Canvas(row, width=14, height=14,
                                 bg=Theme.BG_PANEL, highlightthickness=0)
        self._canvas.pack(side="left", padx=(2, 0))
        self._dot = self._canvas.create_oval(2, 2, 12, 12,
                                             fill=Theme.FG_DIM, outline="")

    def add_row(self, key, label):
        row = tk.Frame(self, bg=Theme.BG_PANEL)
        row.pack(fill="x", pady=1)

        tk.Label(row, text=label, width=11, anchor="w",
                 fg=Theme.FG_DIM, bg=Theme.BG_PANEL,
                 font=Theme.FONT_SANS).pack(side="left")

        val = tk.Label(row, text="—", anchor="w",
                       fg=Theme.FG, bg=Theme.BG_PANEL,
                       font=Theme.FONT_MONO)
        val.pack(side="left")
        self._rows[key] = val

    def set_indicator(self, color):
        self._canvas.itemconfig(self._dot, fill=color)

    def set_row(self, key, text, color=None):
        self._rows[key].config(text=text, fg=color or Theme.FG)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self, bus=None):
        super().__init__()
        self.title("BricksInTheAir — I2C Simulator")
        self.configure(bg=Theme.BG)
        self.minsize(900, 550)
        if self.tk.call("tk", "windowingsystem") == "win32":
            self.state("zoomed")
        else:
            self.attributes("-zoomed", True)

        self.bus       = bus if bus is not None else I2CBus()
        self._history  = []
        self._hist_pos = -1

        self._build_ui()
        self._log(BANNER.strip(), "dim")
        self._refresh_all_panels()
        self.after(250, self._poll_transit)
        self.after(100, self._equalize_panes)  # set 50/50 split after render

    # ── Layout ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._paned = tk.PanedWindow(self, orient="horizontal",
                                     bg=Theme.BORDER, sashwidth=5,
                                     sashrelief="flat", bd=0)
        self._paned.pack(fill="both", expand=True, padx=6, pady=6)

        self._paned.add(self._build_log_pane(self._paned),    minsize=400)
        self._paned.add(self._build_status_pane(self._paned), minsize=400)

    def _equalize_panes(self):
        self.update_idletasks()
        self._paned.sash_place(0, self.winfo_width() // 2, 0)

    def _build_log_pane(self, parent):
        frame = tk.Frame(parent, bg=Theme.BG)

        # Header label
        tk.Label(frame, text="I2C Terminal", fg=Theme.FG_DIM,
                 bg=Theme.BG, font=Theme.FONT_BOLD).pack(anchor="w", pady=(0, 3))

        # Input bar — must be packed BEFORE the text widget so that
        # the expanding Text doesn't push it out of the visible area.
        input_bar = tk.Frame(frame, bg=Theme.BG)
        input_bar.pack(side="bottom", fill="x", pady=(4, 0))

        tk.Label(input_bar, text="I2C>", fg=Theme.ACCENT,
                 bg=Theme.BG, font=Theme.FONT_MONO).pack(side="left", padx=(0, 4))

        self._entry = tk.Entry(input_bar, font=Theme.FONT_MONO,
                               bg=Theme.BG_INPUT, fg=Theme.FG,
                               insertbackground=Theme.FG,
                               relief="flat", bd=4)
        self._entry.pack(side="left", fill="x", expand=True)
        self._entry.bind("<Return>", self._on_submit)
        self._entry.bind("<Up>",     self._history_up)
        self._entry.bind("<Down>",   self._history_down)
        self.after(100, self._entry.focus_force)

        # Output text widget — packed after input bar so it fills remaining space
        self._output = tk.Text(
            frame,
            font=Theme.FONT_MONO,
            bg=Theme.BG,
            fg=Theme.FG,
            insertbackground=Theme.FG,
            state="disabled",
            relief="flat",
            bd=0,
            wrap="word",
            padx=4,
            pady=4,
        )
        scrollbar = tk.Scrollbar(frame, command=self._output.yview,
                                 bg=Theme.BG_PANEL, troughcolor=Theme.BG,
                                 relief="flat", bd=0)
        self._output.config(yscrollcommand=scrollbar.set)

        # Register color tags
        self._output.tag_config("dim",     foreground=Theme.FG_DIM)
        self._output.tag_config("prompt",  foreground=Theme.ACCENT)
        self._output.tag_config("write",   foreground=Theme.GREEN)
        self._output.tag_config("read",    foreground=Theme.CYAN)
        self._output.tag_config("error",   foreground=Theme.RED)
        self._output.tag_config("smoke",   foreground=Theme.RED)
        self._output.tag_config("gear",    foreground=Theme.YELLOW)
        self._output.tag_config("warning", foreground=Theme.YELLOW)

        scrollbar.pack(side="right", fill="y")
        self._output.pack(side="left", fill="both", expand=True)

        return frame

    def _build_status_pane(self, parent):
        outer = tk.Frame(parent, bg=Theme.BG)

        tk.Label(outer, text="System Status", fg=Theme.FG_DIM,
                 bg=Theme.BG, font=Theme.FONT_BOLD).pack(anchor="w", pady=(0, 3))

        inner = tk.Frame(outer, bg=Theme.BG)
        inner.pack(fill="both", expand=True)

        self._fcc_panel = StatusPanel(inner, "FLIGHT CONTROL COMPUTER  (0xBB)")
        self._fcc_panel.pack(fill="x", pady=(0, 6))
        self._fcc_panel.add_row("mode",  "Mode")
        self._fcc_panel.add_row("maint", "Maintenance")

        self._ecu_panel = StatusPanel(inner, "ENGINE CONTROL UNIT  (0xAA)")
        self._ecu_panel.pack(fill="x", pady=(0, 6))
        self._ecu_panel.add_row("mode",     "Mode")
        self._ecu_panel.add_row("maint",    "Maintenance")
        self._ecu_panel.add_row("level",    "Engine Level")
        self._ecu_panel.add_row("rpm",      "RPM")
        self._ecu_panel.add_row("airspeed", "Airspeed")
        self._ecu_panel.add_row("gearsafe", "Gear Safe")

        self._gear_panel = StatusPanel(inner, "LANDING GEAR CONTROL  (0xCC)")
        self._gear_panel.pack(fill="x", pady=(0, 6))
        self._gear_panel.add_row("mode",  "Mode")
        self._gear_panel.add_row("maint", "Maintenance")
        self._gear_panel.add_row("pos",   "Position")

        self._safety_panel = StatusPanel(inner, "SAFETY SYSTEMS")
        self._safety_panel.pack(fill="x", pady=(0, 6))
        self._safety_panel.add_row("afss",         "AFSS")
        self._safety_panel.add_row("afss_tank",    "AFSS Tank")
        self._safety_panel.add_row("afss_cooldown","AFSS Cooldown")

        return outer

    # ── Status refresh ───────────────────────────────────────────────────────

    @staticmethod
    def _led_color(device):
        g, y, r = device._led
        if r: return Theme.RED
        if y: return Theme.YELLOW
        if g: return Theme.GREEN
        return Theme.FG_DIM

    def _refresh_all_panels(self):
        self._refresh_fcc()
        self._refresh_ecu()
        self._refresh_gear()
        self._refresh_safety()

    def _refresh_fcc(self):
        fcc = self.bus.fcc
        self._fcc_panel.set_indicator(self._led_color(fcc))

        mode_text  = "SEC" if fcc.operation_mode != PRI_OPERATION_MODE else "PRI"
        mode_color = Theme.YELLOW if fcc.operation_mode != PRI_OPERATION_MODE else Theme.GREEN
        self._fcc_panel.set_row("mode", mode_text, mode_color)

        maint_text  = "ENABLED"  if fcc.maint_status != MAINT_STATUS_DISABLED else "DISABLED"
        maint_color = Theme.RED if fcc.maint_status != MAINT_STATUS_DISABLED else Theme.FG
        self._fcc_panel.set_row("maint", maint_text, maint_color)

    def _refresh_safety(self):
        fcc = self.bus.fcc

        if fcc.smoke_active and fcc._smoke_start_time is not None:
            remaining  = max(0.0, fcc.SMOKE_DURATION_S - (time.time() - fcc._smoke_start_time))
            afss_text  = f"ACTIVE  ({remaining:.1f}s)"
            afss_color = Theme.RED
        elif fcc.smoke_popped:
            afss_text  = "COMPLETE"
            afss_color = Theme.FG_DIM
        else:
            afss_text  = "READY"
            afss_color = Theme.GREEN
        self._safety_panel.set_row("afss", afss_text, afss_color)

        tank_text  = "EMPTY" if fcc.tank_empty else "READY"
        tank_color = Theme.RED if fcc.tank_empty else Theme.GREEN
        self._safety_panel.set_row("afss_tank", tank_text, tank_color)

        if fcc._last_smoke_time is not None:
            remaining = fcc.SMOKE_COOLDOWN_S - (time.time() - fcc._last_smoke_time)
            if remaining > 0:
                self._safety_panel.set_row("afss_cooldown", f"{remaining:.0f}s remaining", Theme.YELLOW)
            else:
                self._safety_panel.set_row("afss_cooldown", "READY", Theme.GREEN)
        else:
            self._safety_panel.set_row("afss_cooldown", "READY", Theme.GREEN)

    def _refresh_ecu(self):
        ecu = self.bus.ecu

        if ecu.smoke_active:
            self._ecu_panel.set_indicator(Theme.FG_DIM)
            for key in ("mode", "maint", "level", "rpm", "airspeed", "gearsafe"):
                self._ecu_panel.set_row(key, "OFFLINE", Theme.RED)
            return

        self._ecu_panel.set_indicator(self._led_color(ecu))

        mode_text  = "SEC" if ecu.operation_mode != PRI_OPERATION_MODE else "PRI"
        mode_color = Theme.YELLOW if ecu.operation_mode != PRI_OPERATION_MODE else Theme.GREEN
        self._ecu_panel.set_row("mode", mode_text, mode_color)

        maint_text  = "ENABLED"  if ecu.maint_status != MAINT_STATUS_DISABLED else "DISABLED"
        maint_color = Theme.RED if ecu.maint_status != MAINT_STATUS_DISABLED else Theme.FG
        self._ecu_panel.set_row("maint", maint_text, maint_color)

        rpm, knots, gear_safe = ecu.SPEED_DATA.get(ecu.engine_speed, (0, 0, True))
        level_color = Theme.GREEN if ecu.engine_speed > 0 else Theme.FG_DIM
        self._ecu_panel.set_row("level",    str(ecu.engine_speed), level_color)
        self._ecu_panel.set_row("rpm",      f"{rpm}", level_color)
        self._ecu_panel.set_row("airspeed", f"{knots} kts", level_color)

        safe_color = Theme.GREEN if gear_safe else Theme.RED
        safe_text  = "YES" if gear_safe else "NO"
        self._ecu_panel.set_row("gearsafe", safe_text, safe_color)

    def _refresh_gear(self):
        gear = self.bus.gear
        self._gear_panel.set_indicator(self._led_color(gear))

        mode_text  = "SEC" if gear.operation_mode != PRI_OPERATION_MODE else "PRI"
        mode_color = Theme.YELLOW if gear.operation_mode != PRI_OPERATION_MODE else Theme.GREEN
        self._gear_panel.set_row("mode", mode_text, mode_color)

        maint_text  = "ENABLED"  if gear.maint_status != MAINT_STATUS_DISABLED else "DISABLED"
        maint_color = Theme.RED if gear.maint_status != MAINT_STATUS_DISABLED else Theme.FG
        self._gear_panel.set_row("maint", maint_text, maint_color)

        pos_text  = {GEAR_EXTENDED: "EXTENDED", GEAR_RETRACTED: "RETRACTED",
                     GEAR_IN_TRANSIT: "IN_TRANSIT"}.get(gear.gear_position,
                                                         f"0x{gear.gear_position:02X}")
        pos_color = {GEAR_EXTENDED: Theme.GREEN, GEAR_RETRACTED: Theme.RED,
                     GEAR_IN_TRANSIT: Theme.YELLOW}.get(gear.gear_position, Theme.FG_DIM)

        if gear.gear_position == GEAR_IN_TRANSIT and gear._transit_start is not None:
            remaining = max(0.0, GEAR_TRANSIT_DELAY_S - (time.time() - gear._transit_start))
            pos_text += f"  ({remaining:.1f}s)"

        self._gear_panel.set_row("pos", pos_text, pos_color)

    # ── Gear transit polling ─────────────────────────────────────────────────

    def _poll_transit(self):
        self.bus.gear._check_transit()
        self.bus.fcc._check_smoke()
        notes = self.bus.drain_notifications()
        if notes:
            self._handle_notifications(notes)
        self._refresh_gear()    # keep gear transit countdown live
        self._refresh_safety()  # keep AFSS active/cooldown countdown live
        self.after(250, self._poll_transit)

    # ── Command handling ─────────────────────────────────────────────────────

    def _on_submit(self, event=None):
        line = self._entry.get().strip()
        self._entry.delete(0, "end")
        if not line:
            return

        self._history.append(line)
        self._hist_pos = -1
        self._log(f"I2C> {line}", "prompt")
        self._dispatch(line)

    def _dispatch(self, line):
        lower = line.lower()
        if lower in ("quit", "exit", "q"):
            self.destroy()
        elif lower in ("help", "?"):
            self._log(HELP_TEXT.strip(), "dim")
        elif lower == "status":
            self._refresh_all_panels()
            self._log("Status refreshed.", "dim")
        elif lower == "system reset":
            self._reset_system()
        elif "[" in line:
            self._execute(line)
        else:
            self._log("ERROR: unknown command — type 'help' for usage", "error")

    def _reset_system(self):
        bus = self.bus
        bus.fcc  = type(bus.fcc)()
        bus.ecu  = type(bus.ecu)()
        bus.gear = type(bus.gear)()
        bus._devices = {
            bus.fcc.ADDRESS:  bus.fcc,
            bus.ecu.ADDRESS:  bus.ecu,
            bus.gear.ADDRESS: bus.gear,
        }
        if bus.bridge is not None:
            bus.bridge._last_speed        = -1
            bus.bridge._last_gear         = -1
            bus.bridge._last_smoke_active = False
            bus.bridge._last_smoke_popped = False
            bus.bridge._last_emergency    = False
            bus.bridge._last_ecu_smoke    = False
            bus.bridge._overspeed_cutoff  = None
            bus.bridge.update()
        self._refresh_all_panels()
        self._log("System reset — all devices returned to initial state.", "dim")

    def _execute(self, line):
        try:
            transactions = parse_transactions(line)
        except ValueError as e:
            self._log(f"ERROR: {e}", "error")
            return

        if not transactions:
            self._log("ERROR: no valid transactions found — use brackets, e.g. [0xA0 0x30]",
                      "error")
            return

        for txn in transactions:
            addr      = txn["addr"]
            addr_byte = (addr << 1) | (0 if txn["type"] == "write" else 1)

            if txn["type"] == "write":
                ack = self.bus.write(addr, txn["data"])
                if ack:
                    parts = [f"0x{addr_byte:02X}", "ACK"]
                    for b in txn["data"]:
                        parts += [f"0x{b:02X}", "ACK"]
                    self._log("WRITE: " + " ".join(parts), "write")
                else:
                    self._log(f"WRITE: 0x{addr_byte:02X} NAK", "error")

            elif txn["type"] == "read":
                result = self.bus.read(addr, txn["n"])
                if result is None:
                    self._log(f"READ:  0x{addr_byte:02X} NAK", "error")
                else:
                    bytes_str = " ".join(f"0x{b:02X}" for b in result)
                    self._log(f"READ:  0x{addr_byte:02X} ACK {bytes_str}", "read")

        notes = self.bus.drain_notifications()
        self._handle_notifications(notes)
        self._refresh_all_panels()

    def _handle_notifications(self, notes):
        for note in notes:
            if note[0] == "smoke":
                self._log(ENGINE_WARN1, "smoke")
                self.after(2000, lambda: self._log(ENGINE_WARN2, "smoke"))
                self.after(4000, lambda: self._log(ENGINE_WARN3, "smoke"))
                # Auto-deploy AFSS if not already running
                fcc = self.bus.fcc
                if not fcc.smoke_active:
                    fcc.smoke_popped      = True
                    fcc.smoke_active      = True
                    fcc._smoke_start_time = time.time()
                    self._refresh_safety()
            elif note[0] == "gear":
                self._log(f"[GEAR] {note[1]}", "gear")
            elif note[0] == "error":
                self._log(f"ERROR: {note[1]}", "error")
            elif note[0] == "warning":
                self._log(f"WARNING: {note[1]}", "warning")
            # 'led' changes are reflected silently via _refresh_all_panels

    # ── Output log ───────────────────────────────────────────────────────────

    def _log(self, text, tag=None):
        self._output.config(state="normal")
        if tag:
            self._output.insert("end", text + "\n", tag)
        else:
            self._output.insert("end", text + "\n")
        self._output.see("end")
        self._output.config(state="disabled")

    # ── Command history ──────────────────────────────────────────────────────

    def _history_up(self, event=None):
        if not self._history:
            return
        self._hist_pos = min(self._hist_pos + 1, len(self._history) - 1)
        self._entry.delete(0, "end")
        self._entry.insert(0, self._history[-(self._hist_pos + 1)])

    def _history_down(self, event=None):
        if self._hist_pos <= 0:
            self._hist_pos = -1
            self._entry.delete(0, "end")
            return
        self._hist_pos -= 1
        self._entry.delete(0, "end")
        self._entry.insert(0, self._history[-(self._hist_pos + 1)])


# ---------------------------------------------------------------------------

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
