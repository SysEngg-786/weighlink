# ==============================================================================
# weighlink/controller/fill_controller_gui.py
# Industrial Automation Control Panel — GUI with integrated compliance pipeline.
#
# Data flow:
#   Serial Reader → Protocol Parser → WeighmentRecord → Tolerance Engine
#   → Audit Logger → Webhook Pusher → UI Update
#
# The fill-control logic (proportional motor speed) is preserved exactly
# from the original proven display.py. The only structural change is that
# serial reading, parsing, compliance, and integration are now handled
# by dedicated modules — this file owns only the GUI and fill logic.
# ==============================================================================

import json
import os
import tkinter as tk
from tkinter import ttk

from listener.serial_reader import SerialReader
from compliance.weighment import WeighmentRecord
from compliance.tolerance_engine import ToleranceEngine
from compliance.audit_logger import AuditLogger
from integration.webhook_pusher import WebhookPusher


class ScaleControllerApp:
    """
    Industrial fill-controller GUI with integrated compliance pipeline.
    
    Reads weight data from a serial instrument via SerialReader,
    evaluates tolerance, logs to audit trail, pushes to webhook,
    and drives a proportional fill-control UI — all in real time.
    """

    def __init__(self, root, app_config_path="config/app_config.json"):
        self.root = root
        self.root.title("WeighLink - Industrial Automation Control Panel")
        self.root.geometry("600x500")
        self.root.configure(bg="#1e1e1e")

        # Load application config for GUI settings
        with open(app_config_path, 'r') as f:
            self._app_config = json.load(f)

        gui_cfg = self._app_config.get("gui", {})
        compliance_cfg = self._app_config.get("compliance", {})

        # --- Initialize pipeline components ---

        # Serial reader (handles port, parsing, background thread)
        self._reader = SerialReader(app_config_path)

        # Compliance: tolerance engine
        tolerance_profile = compliance_cfg.get("tolerance_profile", "demo_product")
        tolerance_path = os.path.join(
            "config", "tolerances", f"{tolerance_profile}.json"
        )
        self._tolerance_engine = ToleranceEngine(tolerance_path)

        # Compliance: audit logger
        log_dir = compliance_cfg.get("audit_log_dir", "data/audit_log")
        self._audit_logger = AuditLogger(log_dir)

        # Integration: webhook pusher
        self._webhook_pusher = WebhookPusher(app_config_path)

        # Operator and lot — defaults from config, updatable at runtime
        self._operator_id = compliance_cfg.get("default_operator_id", "OP_UNSET")
        self._lot_ref = compliance_cfg.get("default_lot_ref", "LOT_UNSET")

        # State variables
        self.current_weight = 0.000
        self.target_weight = gui_cfg.get("default_target_weight", 10.0)
        self._target_min = gui_cfg.get("target_weight_min", 1.0)
        self._target_max = gui_cfg.get("target_weight_max", 30.0)

        # Configure dark theme styles
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('.', background='#1e1e1e', foreground='#ffffff')
        self.style.configure('TLabel', background='#1e1e1e', foreground='#ffffff', font=('Arial', 11))
        self.style.configure('TButton', background='#333333', foreground='#ffffff', font=('Arial', 10, 'bold'))
        self.style.map('TButton', background=[('active', '#454545')])

        self._create_widgets()

    def _create_widgets(self):
        """Build the GUI layout — status bar, readout, controls, compliance info."""

        # --- 1. Connection Status Bar ---
        self.status_frame = tk.Frame(self.root, bg="#2d2d2d", height=40)
        self.status_frame.pack(fill=tk.X, side=tk.TOP)

        port_name = self._reader.port_name
        self.lbl_status = tk.Label(
            self.status_frame,
            text=f"Disconnected ({port_name})",
            fg="#ff6b6b", bg="#2d2d2d", font=('Arial', 11, 'bold')
        )
        self.lbl_status.pack(side=tk.LEFT, padx=15, pady=8)

        self.btn_connect = ttk.Button(
            self.status_frame, text="Connect System",
            command=self._toggle_connection
        )
        self.btn_connect.pack(side=tk.RIGHT, padx=15, pady=5)

        # --- 2. Main Live Readout Display ---
        self.display_frame = tk.Frame(self.root, bg="#111111", bd=2, relief=tk.SOLID)
        self.display_frame.pack(fill=tk.X, padx=20, pady=15)

        self.lbl_weight = tk.Label(
            self.display_frame, text="000.000",
            fg="#00ff66", bg="#111111", font=('Consolas', 48, 'bold')
        )
        self.lbl_weight.pack(pady=10)

        self.lbl_meta = tk.Label(
            self.display_frame, text="UNIT: GRAMS  |  STATUS: IDLE",
            fg="#888888", bg="#111111", font=('Arial', 10, 'bold')
        )
        self.lbl_meta.pack(pady=5)

        # --- 3. Automation Control Target Settings ---
        self.control_frame = tk.LabelFrame(
            self.root, text=" Target Mass Controls ",
            bg="#1e1e1e", fg="#ffffff", font=('Arial', 10, 'bold')
        )
        self.control_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        # Target input slider
        tk.Label(self.control_frame, text="Set Target Fill Weight (g):").grid(
            row=0, column=0, padx=15, pady=10, sticky='w'
        )
        self.slider_target = tk.Scale(
            self.control_frame,
            from_=self._target_min, to=self._target_max,
            orient=tk.HORIZONTAL, resolution=0.1,
            bg="#1e1e1e", fg="#ffffff", highlightthickness=0,
            troughcolor="#333333", activebackground="#00ff66",
            command=self._update_target
        )
        self.slider_target.set(self.target_weight)
        self.slider_target.grid(row=0, column=1, padx=15, pady=10, sticky='ew')

        # Motor feedback bar
        tk.Label(self.control_frame, text="Automation Motor Feedback:").grid(
            row=1, column=0, padx=15, pady=10, sticky='w'
        )
        self.progress_motor = ttk.Progressbar(
            self.control_frame, orient=tk.HORIZONTAL, length=200, mode='determinate'
        )
        self.progress_motor.grid(row=1, column=1, padx=15, pady=10, sticky='ew')

        self.lbl_motor_status = tk.Label(
            self.control_frame, text="Motor: OFF (0%)", fg="#ff6b6b"
        )
        self.lbl_motor_status.grid(row=1, column=2, padx=15, pady=10)

        # Tare button
        self.btn_tare = ttk.Button(
            self.control_frame, text="Zero / Tare Scale (Send 'Z')",
            command=self._send_tare_command, state=tk.DISABLED
        )
        self.btn_tare.grid(row=2, column=0, columnspan=3, pady=10, padx=15, sticky='ew')

        self.control_frame.grid_columnconfigure(1, weight=1)

        # --- 4. Compliance Status Bar ---
        self.compliance_frame = tk.Frame(self.root, bg="#2d2d2d", height=30)
        self.compliance_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_compliance = tk.Label(
            self.compliance_frame,
            text=(
                f"Tolerance: {self._tolerance_engine.profile_name} | "
                f"Log: {os.path.basename(self._audit_logger.log_path)} | "
                f"Webhook: {'ON' if self._webhook_pusher.is_enabled else 'OFF'} | "
                f"Records: 0"
            ),
            fg="#888888", bg="#2d2d2d", font=('Arial', 9)
        )
        self.lbl_compliance.pack(side=tk.LEFT, padx=15, pady=5)

    def _update_target(self, val):
        """Slider callback — update the fill target weight."""
        self.target_weight = float(val)

    def _toggle_connection(self):
        """Connect or disconnect the serial reader."""
        if not self._reader.is_connected:
            try:
                # Register the pipeline callback before connecting
                self._reader.on_reading(self._on_reading)
                self._reader.connect()

                self.btn_connect.configure(text="Disconnect System")
                self.btn_tare.configure(state=tk.NORMAL)
                self.lbl_status.configure(
                    text=f"Hardware Linked ({self._reader.port_name})",
                    fg="#00ff66"
                )
            except Exception as e:
                self.lbl_status.configure(text="Connection Failed!", fg="#ff6b6b")
                print(f"[GUI] Connection Error: {e}")
        else:
            self._reader.disconnect()
            self.btn_connect.configure(text="Connect System")
            self.btn_tare.configure(state=tk.DISABLED)
            self.lbl_status.configure(
                text=f"Disconnected ({self._reader.port_name})",
                fg="#ff6b6b"
            )
            self.progress_motor['value'] = 0
            self.lbl_motor_status.configure(text="Motor: OFF (0%)", fg="#ff6b6b")

    def _send_tare_command(self):
        """Send tare/zero command to the connected instrument."""
        self._reader.send_command('Z')
        print("[GUI] Tare command sent to instrument.")

    def _on_reading(self, reading):
        """
        Pipeline callback — fires on every parsed serial reading.
        
        This is called from the SerialReader's background thread.
        Compliance processing happens here; UI update is dispatched
        to the main Tkinter thread via root.after().
        
        Pipeline:
          reading dict → WeighmentRecord → tolerance check
          → audit log → webhook push → UI update
        """
        # Create a compliant weighment record from the raw reading
        record = WeighmentRecord.from_reading(
            reading,
            operator_id=self._operator_id,
            lot_ref=self._lot_ref
        )

        # Run tolerance evaluation
        self._tolerance_engine.evaluate(record)

        # Write to audit log (only stable readings get meaningful records,
        # but we log all readings for complete traceability)
        self._audit_logger.log(record)

        # Push to webhook (pusher internally checks if enabled)
        if record.is_stable:
            self._webhook_pusher.push(record)

        # Update the current weight for fill-control logic
        self.current_weight = record.weight

        # Dispatch UI update to the main Tkinter thread
        self.root.after(0, self._update_ui, record)

    def _update_ui(self, record):
        """
        UI render — updates weight display, stability status, motor feedback,
        and compliance status bar. Called on the main Tkinter thread.
        
        Fill-control logic (proportional motor speed) is preserved exactly
        from the original proven display.py.
        """
        # 1. Update primary readout panel
        self.lbl_weight.configure(text=f"{record.weight:07.3f}")

        if record.is_stable:
            status_text = "STABLE"
            status_color = "#00ff66"
        else:
            status_text = "UNSTABLE / SETTLING"
            status_color = "#ffcc00"

        # Add tolerance result to status line for stable readings
        tol_text = ""
        if record.is_stable and record.tolerance_result != "NO_RULE":
            tol_text = f"  |  TOL: {record.tolerance_result}"
            if record.tolerance_result == "FAIL":
                status_color = "#ff3333"

        self.lbl_meta.configure(
            text=f"UNIT: {record.unit.upper()}  |  STATUS: {status_text}{tol_text}",
            fg=status_color
        )

        # 2. Closed-loop fill-control logic (unchanged from original)
        remaining_mass = self.target_weight - record.weight

        if remaining_mass <= 0:
            # Target met or overfilled — kill actuators
            motor_speed = 0
            motor_desc = "Motor: TARGET REACHED (0%)"
            motor_color = "#555555"
        elif remaining_mass > 2.0:
            # Far from target — full bulk flow
            motor_speed = 100
            motor_desc = "Motor: BULK FILLING (100%)"
            motor_color = "#ff3333"
        else:
            # Approaching target — linear ramp-down to micro-trickle
            motor_speed = int((remaining_mass / 2.0) * 100)
            motor_speed = max(10, motor_speed)
            motor_desc = f"Motor: MICRO-TRICKLE ({motor_speed}%)"
            motor_color = "#ffcc00"

        self.progress_motor['value'] = motor_speed
        self.lbl_motor_status.configure(text=motor_desc, fg=motor_color)

        # 3. Update compliance status bar
        self.lbl_compliance.configure(
            text=(
                f"Tolerance: {self._tolerance_engine.profile_name} | "
                f"Log: {os.path.basename(self._audit_logger.log_path)} | "
                f"Webhook: {'ON' if self._webhook_pusher.is_enabled else 'OFF'} | "
                f"Records: {self._audit_logger.record_count}"
            )
        )


def main():
    """Entry point — launch the WeighLink controller GUI."""
    root = tk.Tk()
    app = ScaleControllerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
