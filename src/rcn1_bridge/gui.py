from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .calibration import apply_calibration, capture_calibration
from .config import BUTTON_CHOICES, BridgeConfig, save_config
from .output import create_output
from .ports import list_candidates
from .service import BridgeService, ServiceSnapshot, ServiceState
from .transport import Rcn1Transport


class BridgeWindow:
    BG = "#11151b"
    PANEL = "#1a2029"
    PANEL_2 = "#222a35"
    TEXT = "#edf2f7"
    MUTED = "#9ba8b8"
    ACCENT = "#49d3a3"
    WARNING = "#f0b35a"
    ERROR = "#ff6b72"

    def __init__(self, config: BridgeConfig, config_path: Path | None) -> None:
        self.config = config
        self.config_path = config_path
        self.root = tk.Tk()
        self.root.title("RC N1 Bridge")
        self.root.geometry("820x740")
        self.root.minsize(720, 710)
        self.root.configure(bg=self.BG)
        self.service: BridgeService | None = None
        self._latest = ServiceSnapshot()
        self._calibrating = False
        self._port_by_label: dict[str, str | None] = {"Automatic (recommended)": None}
        self._build_style()
        self._build()
        self._refresh_ports()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(80, self._render)

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Panel.TFrame", background=self.PANEL)
        style.configure("Sub.TFrame", background=self.PANEL_2)
        style.configure(
            "Title.TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI Semibold", 22)
        )
        style.configure("Subtitle.TLabel", background=self.BG, foreground=self.MUTED)
        style.configure("Panel.TLabel", background=self.PANEL, foreground=self.TEXT)
        style.configure("Muted.TLabel", background=self.PANEL, foreground=self.MUTED)
        style.configure(
            "Value.TLabel",
            background=self.PANEL,
            foreground=self.ACCENT,
            font=("Cascadia Mono", 10, "bold"),
        )
        style.configure(
            "Accent.TButton",
            background=self.ACCENT,
            foreground="#08130f",
            font=("Segoe UI Semibold", 10),
            padding=(18, 9),
            borderwidth=0,
        )
        style.map("Accent.TButton", background=[("active", "#6ee1b8"), ("disabled", "#45645b")])
        style.configure(
            "Secondary.TButton",
            background=self.PANEL_2,
            foreground=self.TEXT,
            padding=(14, 8),
            borderwidth=0,
        )
        style.map("Secondary.TButton", background=[("active", "#303b49")])
        style.configure(
            "Axis.Horizontal.TProgressbar",
            troughcolor="#0c1015",
            background=self.ACCENT,
            borderwidth=0,
            thickness=12,
        )
        style.configure(
            "TCombobox",
            fieldbackground=self.PANEL_2,
            background=self.PANEL_2,
            foreground=self.TEXT,
            arrowcolor=self.TEXT,
        )
        style.configure(
            "TEntry", fieldbackground=self.PANEL_2, foreground=self.TEXT, insertcolor=self.TEXT
        )
        style.configure("TCheckbutton", background=self.PANEL, foreground=self.TEXT)
        style.map("TCheckbutton", background=[("active", self.PANEL)])

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=24)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x")
        title = ttk.Frame(header)
        title.pack(side="left")
        ttk.Label(title, text="RC N1 Bridge", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title,
            text="DJI control input → low-latency virtual Xbox controller",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        self.start_button = ttk.Button(
            header, text="Start bridge", style="Accent.TButton", command=self._toggle
        )
        self.start_button.pack(side="right", padx=(10, 0))

        status_panel = ttk.Frame(outer, style="Panel.TFrame", padding=16)
        status_panel.pack(fill="x", pady=(22, 12))
        self.status_dot = tk.Canvas(
            status_panel, width=12, height=12, bg=self.PANEL, highlightthickness=0
        )
        self.status_dot.pack(side="left", padx=(0, 10))
        self.status_oval = self.status_dot.create_oval(1, 1, 11, 11, fill=self.MUTED, outline="")
        self.status_text = ttk.Label(status_panel, text="Stopped", style="Panel.TLabel")
        self.status_text.pack(side="left")
        self.port_text = ttk.Label(status_panel, text="No port", style="Muted.TLabel")
        self.port_text.pack(side="right")

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, style="Panel.TFrame", padding=18)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right = ttk.Frame(body, style="Panel.TFrame", padding=18)
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))

        ttk.Label(
            left, text="Live controls", style="Panel.TLabel", font=("Segoe UI Semibold", 12)
        ).pack(anchor="w", pady=(0, 12))
        self.axis_widgets: dict[str, tuple[ttk.Progressbar, ttk.Label]] = {}
        for name, label in (
            ("left_x", "Left horizontal"),
            ("left_y", "Left vertical"),
            ("right_x", "Right horizontal"),
            ("right_y", "Right vertical"),
            ("camera", "Camera wheel"),
        ):
            row = ttk.Frame(left, style="Panel.TFrame")
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=label, style="Muted.TLabel", width=17).pack(side="left")
            bar = ttk.Progressbar(row, maximum=200, value=100, style="Axis.Horizontal.TProgressbar")
            bar.pack(side="left", fill="x", expand=True, padx=(4, 9))
            value = ttk.Label(row, text="+0.000", style="Value.TLabel", width=7)
            value.pack(side="right")
            self.axis_widgets[name] = (bar, value)

        metrics = ttk.Frame(left, style="Sub.TFrame", padding=12)
        metrics.pack(fill="x", pady=(16, 0))
        self.packet_label = ttk.Label(
            metrics, text="Packets  0", background=self.PANEL_2, foreground=self.MUTED
        )
        self.packet_label.pack(side="left")
        self.latency_label = ttk.Label(
            metrics, text="Response  —", background=self.PANEL_2, foreground=self.MUTED
        )
        self.latency_label.pack(side="right")
        self.physical_label = ttk.Label(
            left,
            text="Mode —  •  Buttons —",
            style="Muted.TLabel",
            wraplength=320,
        )
        self.physical_label.pack(anchor="w", pady=(12, 0))

        ttk.Label(
            right, text="Connection", style="Panel.TLabel", font=("Segoe UI Semibold", 12)
        ).pack(anchor="w")
        ttk.Label(right, text="Protocol port", style="Muted.TLabel").pack(anchor="w", pady=(14, 4))
        port_row = ttk.Frame(right, style="Panel.TFrame")
        port_row.pack(fill="x")
        self.port_var = tk.StringVar(value="Automatic (recommended)")
        self.port_combo = ttk.Combobox(port_row, textvariable=self.port_var, state="readonly")
        self.port_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(
            port_row, text="Refresh", style="Secondary.TButton", command=self._refresh_ports
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            right, text="Input tuning", style="Panel.TLabel", font=("Segoe UI Semibold", 12)
        ).pack(anchor="w", pady=(24, 8))
        settings = ttk.Frame(right, style="Panel.TFrame")
        settings.pack(fill="x")
        self.deadzone_var = tk.StringVar(value=f"{self.config.axes['left_x'].deadzone:.3f}")
        self.expo_var = tk.StringVar(value=f"{self.config.axes['left_x'].expo:.3f}")
        self.smoothing_var = tk.StringVar(value=f"{self.config.smoothing:.3f}")
        self.anti_deadzone_enabled_var = tk.BooleanVar(
            value=self.config.anti_deadzone_enabled
        )
        self.anti_deadzone_var = tk.StringVar(value=f"{self.config.anti_deadzone:.3f}")
        self._setting_row(settings, "Dead zone", self.deadzone_var)
        self._setting_row(settings, "Expo", self.expo_var)
        self._setting_row(settings, "Smoothing", self.smoothing_var)
        anti_row = ttk.Frame(settings, style="Panel.TFrame")
        anti_row.pack(fill="x", pady=4)
        ttk.Checkbutton(
            anti_row,
            text="Enable anti-deadzone",
            variable=self.anti_deadzone_enabled_var,
        ).pack(side="left")
        ttk.Entry(
            anti_row,
            textvariable=self.anti_deadzone_var,
            width=8,
            justify="right",
        ).pack(side="right")

        actions = ttk.Frame(right, style="Panel.TFrame")
        actions.pack(fill="x", pady=(22, 0))
        ttk.Button(
            actions, text="Save settings", style="Secondary.TButton", command=self._save_settings
        ).pack(side="left")
        self.calibrate_button = ttk.Button(
            actions, text="Calibrate", style="Secondary.TButton", command=self._start_calibration
        )
        self.calibrate_button.pack(side="right")
        ttk.Button(
            right,
            text="Control mappings",
            style="Secondary.TButton",
            command=self._open_mappings,
        ).pack(fill="x", pady=(10, 0))
        ttk.Label(
            right,
            text="Axis directions and every button binding are configurable. "
            "Anti-deadzone values around 0.25–0.26 compensate for large game deadzones. "
            "Output is neutralized on disconnect.",
            style="Muted.TLabel",
            wraplength=300,
        ).pack(anchor="w", pady=(18, 0))

    def _setting_row(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, style="Muted.TLabel").pack(side="left")
        ttk.Entry(row, textvariable=variable, width=8, justify="right").pack(side="right")

    def _refresh_ports(self) -> None:
        selected_device = (
            self._port_by_label.get(self.port_var.get()) if hasattr(self, "port_var") else None
        )
        labels = ["Automatic (recommended)"]
        self._port_by_label = {labels[0]: None}
        try:
            for item in list_candidates(include_unknown=False):
                label = f"{item.device} — {item.description}"
                labels.append(label)
                self._port_by_label[label] = item.device
        except RuntimeError:
            pass
        if hasattr(self, "port_combo"):
            self.port_combo["values"] = labels
            matching = next(
                (
                    label
                    for label, device in self._port_by_label.items()
                    if device == selected_device
                ),
                labels[0],
            )
            self.port_var.set(matching)

    def _read_settings(self) -> None:
        deadzone = float(self.deadzone_var.get())
        expo = float(self.expo_var.get())
        smoothing = float(self.smoothing_var.get())
        anti_deadzone = float(self.anti_deadzone_var.get())
        for name in ("left_x", "left_y", "right_x", "right_y"):
            self.config.axes[name].deadzone = deadzone
            self.config.axes[name].expo = expo
        self.config.smoothing = smoothing
        self.config.anti_deadzone_enabled = self.anti_deadzone_enabled_var.get()
        self.config.anti_deadzone = anti_deadzone
        self.config.port = self._port_by_label.get(self.port_var.get())
        self.config.validate()

    def _save_settings(self) -> bool:
        try:
            self._read_settings()
            path = save_config(self.config, self.config_path)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid settings", str(exc), parent=self.root)
            return False
        self.status_text.configure(text=f"Settings saved to {path}")
        return True

    def _open_mappings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Control mappings")
        dialog.geometry("520x700")
        dialog.resizable(False, False)
        dialog.configure(bg=self.BG)
        dialog.transient(self.root)
        dialog.grab_set()

        outer = ttk.Frame(dialog, padding=22)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer, text="Axis directions", style="Title.TLabel", font=("Segoe UI Semibold", 16)
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text="Toggle only the directions that feel reversed in your simulator.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        invert_vars: dict[str, tk.BooleanVar] = {}
        axis_labels = (
            ("left_x", "Left horizontal"),
            ("left_y", "Left vertical"),
            ("right_x", "Right horizontal"),
            ("right_y", "Right vertical"),
            ("camera", "Camera wheel"),
        )
        axis_panel = ttk.Frame(outer, style="Panel.TFrame", padding=12)
        axis_panel.pack(fill="x")
        for name, label in axis_labels:
            variable = tk.BooleanVar(value=self.config.axes[name].invert)
            invert_vars[name] = variable
            ttk.Checkbutton(axis_panel, text=f"Invert {label}", variable=variable).pack(
                anchor="w", pady=2
            )

        ttk.Label(
            outer, text="Xbox button bindings", style="Panel.TLabel", font=("Segoe UI Semibold", 12)
        ).pack(anchor="w", pady=(18, 2))
        ttk.Label(
            outer,
            text="Disabled is safest until you bind an action inside the game.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        display_choices = ("Disabled",) + BUTTON_CHOICES[1:]
        binding_vars: dict[str, tk.StringVar] = {}
        bindings = (
            ("camera_left_button", "Camera wheel left"),
            ("camera_right_button", "Camera wheel right"),
            ("fn_button", "Fn"),
            ("record_button", "Record"),
            ("photo_button", "Photo / shutter"),
            ("rth_button", "Return to home"),
            ("mode_cine_button", "Mode: Cine"),
            ("mode_normal_button", "Mode: Normal"),
            ("mode_sport_button", "Mode: Sport"),
        )
        binding_panel = ttk.Frame(outer, style="Panel.TFrame", padding=12)
        binding_panel.pack(fill="x")
        for field, label in bindings:
            row = ttk.Frame(binding_panel, style="Panel.TFrame")
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, style="Muted.TLabel").pack(side="left")
            current = getattr(self.config, field)
            variable = tk.StringVar(value="Disabled" if current == "NONE" else current)
            binding_vars[field] = variable
            ttk.Combobox(
                row,
                textvariable=variable,
                values=display_choices,
                state="readonly",
                width=14,
            ).pack(side="right")

        def save() -> None:
            for name, variable in invert_vars.items():
                self.config.axes[name].invert = variable.get()
            for field, variable in binding_vars.items():
                value = variable.get()
                setattr(self.config, field, "NONE" if value == "Disabled" else value)
            try:
                path = save_config(self.config, self.config_path)
            except (ValueError, OSError) as exc:
                messagebox.showerror("Invalid mappings", str(exc), parent=dialog)
                return
            self.status_text.configure(text=f"Mappings saved to {path}")
            dialog.destroy()

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(16, 0))
        ttk.Button(buttons, text="Cancel", style="Secondary.TButton", command=dialog.destroy).pack(
            side="left"
        )
        ttk.Button(buttons, text="Save mappings", style="Accent.TButton", command=save).pack(
            side="right"
        )

    def _toggle(self) -> None:
        if self.service:
            service, self.service = self.service, None
            service.close()
            self.start_button.configure(text="Start bridge")
            return
        if not self._save_settings():
            return
        try:
            output = create_output("xbox")
        except (RuntimeError, ValueError) as exc:
            messagebox.showerror("Virtual controller unavailable", str(exc), parent=self.root)
            return
        self.service = BridgeService(self.config, output, on_update=self._receive)
        self.service.start()
        self.start_button.configure(text="Stop bridge")

    def _receive(self, snapshot: ServiceSnapshot) -> None:
        self._latest = snapshot

    def _render(self) -> None:
        snapshot = self._latest
        colors = {
            ServiceState.RUNNING: self.ACCENT,
            ServiceState.ERROR: self.ERROR,
            ServiceState.RECONNECTING: self.WARNING,
            ServiceState.CONNECTING: self.WARNING,
            ServiceState.SEARCHING: self.MUTED,
            ServiceState.STOPPED: self.MUTED,
        }
        self.status_dot.itemconfigure(self.status_oval, fill=colors[snapshot.state])
        self.status_text.configure(text=snapshot.message)
        self.port_text.configure(text=snapshot.port or "Automatic")
        if snapshot.mapped:
            for name, (bar, label) in self.axis_widgets.items():
                value = getattr(snapshot.mapped, name)
                bar.configure(value=(value + 1.0) * 100.0)
                label.configure(text=f"{value:+.3f}")
        if snapshot.stats:
            self.packet_label.configure(text=f"Packets  {snapshot.stats.controls_received:,}")
            self.latency_label.configure(text=f"Response  {snapshot.stats.last_response_ms:.1f} ms")
        physical = snapshot.physical
        active = (
            ", ".join(
                name
                for name, pressed in (
                    ("Fn", physical.fn),
                    ("Record", physical.record),
                    ("Photo", physical.photo),
                    ("RTH", physical.rth),
                )
                if pressed
            )
            or "—"
        )
        self.physical_label.configure(
            text=(
                f"Mode {physical.mode.value}  •  Buttons {active}  •  "
                f"Raw 0x{physical.raw_bits:04X}"
            )
        )
        self.root.after(80, self._render)

    def _start_calibration(self) -> None:
        if self._calibrating:
            return
        if self.service:
            self._toggle()
        if not self._save_settings():
            return
        if not messagebox.askokcancel(
            "Calibrate controller",
            "First keep both sticks and the camera wheel released. After two seconds, "
            "move every axis repeatedly to both full endpoints for ten seconds.",
            parent=self.root,
        ):
            return
        self._calibrating = True
        self.calibrate_button.configure(state="disabled")
        threading.Thread(
            target=self._calibration_worker, name="rcn1-calibration", daemon=True
        ).start()

    def _calibration_worker(self) -> None:
        try:
            port = self.config.port
            if not port:
                candidates = list_candidates(include_unknown=self.config.probe_unknown_ports)
                if not candidates:
                    raise RuntimeError("no candidate DJI protocol port found")
                port = candidates[0].device
            with Rcn1Transport(
                port,
                baud_rate=self.config.baud_rate,
                response_timeout=self.config.response_timeout_seconds,
            ) as transport:
                transport.enable_simulator_mode()

                def progress(phase: str, fraction: float) -> None:
                    verb = (
                        "Keep controls centered"
                        if phase == "center"
                        else "Move every control to full endpoints"
                    )
                    self._latest = ServiceSnapshot(
                        state=ServiceState.CONNECTING,
                        message=f"{verb} — {fraction:.0%}",
                        port=port,
                    )

                values = capture_calibration(transport, on_phase=progress)
            apply_calibration(self.config, values)
            save_config(self.config, self.config_path)
            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Calibration complete", "New centers and ranges were saved.", parent=self.root
                ),
            )
        except Exception as exc:
            detail = str(exc)
            self.root.after(
                0, lambda: messagebox.showerror("Calibration failed", detail, parent=self.root)
            )
        finally:
            self._latest = ServiceSnapshot()
            self._calibrating = False
            self.root.after(0, lambda: self.calibrate_button.configure(state="normal"))

    def _close(self) -> None:
        if self.service:
            self.service.close()
            self.service = None
        self.root.destroy()

    def run(self) -> int:
        self.root.mainloop()
        return 0


def run_gui(config: BridgeConfig, config_path: Path | None = None) -> int:
    return BridgeWindow(config, config_path).run()
