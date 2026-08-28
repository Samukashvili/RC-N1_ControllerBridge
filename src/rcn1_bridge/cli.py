from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

from . import __version__
from .calibration import apply_calibration, capture_calibration
from .config import BridgeConfig, load_config, save_config
from .output import create_output
from .ports import list_candidates
from .service import BridgeService, ServiceSnapshot, ServiceState
from .transport import Rcn1Transport, probe_port


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rcn1-bridge",
        description="Translate DJI RC-N1 controls into a virtual Xbox 360 controller.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, help="configuration JSON path")
    parser.add_argument("--verbose", action="store_true", help="show diagnostic logs")
    commands = parser.add_subparsers(dest="command")

    scan = commands.add_parser("scan", help="list ranked serial-port candidates")
    scan.add_argument("--probe", action="store_true", help="probe candidates for valid DJI replies")
    scan.add_argument(
        "--include-unknown",
        action="store_true",
        help="include non-DJI serial ports (use carefully)",
    )

    run = commands.add_parser("run", help="run the low-latency Xbox bridge")
    run.add_argument("--port", help="override automatic serial-port selection")
    run.add_argument("--output", choices=("xbox", "none"), default="xbox")
    run.add_argument("--seconds", type=float, help="stop automatically after this many seconds")

    diagnose = commands.add_parser("diagnose", help="read and validate controls without a gamepad")
    diagnose.add_argument("--port", help="override automatic serial-port selection")
    diagnose.add_argument("--seconds", type=float, default=10.0)

    calibrate = commands.add_parser("calibrate", help="capture stick centers and full ranges")
    calibrate.add_argument("--port", help="override automatic serial-port selection")
    calibrate.add_argument("--center-seconds", type=float, default=2.0)
    calibrate.add_argument("--range-seconds", type=float, default=10.0)

    commands.add_parser("init-config", help="write a documented default configuration")
    commands.add_parser("gui", help="open the desktop interface")
    return parser


def _load(args: argparse.Namespace) -> BridgeConfig:
    config = load_config(args.config)
    port = getattr(args, "port", None)
    if port:
        config.port = port
    return config


def _scan(args: argparse.Namespace) -> int:
    candidates = list_candidates(include_unknown=args.include_unknown)
    if not candidates:
        print("No candidate serial ports found.")
        return 1
    print("Score  Port   Probe  Description / reason")
    for item in candidates:
        result = "-"
        if args.probe:
            result = "yes" if probe_port(item.device) else "no"
        print(f"{item.score:>5}  {item.device:<6} {result:<5}  {item.description} ({item.reason})")
    return 0


class _ConsoleReporter:
    def __init__(self, *, controls: bool) -> None:
        self.controls = controls
        self._last_state: ServiceState | None = None
        self._last_physical = None
        self._last_print = 0.0

    def __call__(self, snapshot: ServiceSnapshot) -> None:
        now = time.monotonic()
        state_changed = snapshot.state != self._last_state
        physical_changed = snapshot.physical != self._last_physical
        if not state_changed and not physical_changed and now - self._last_print < 0.5:
            return
        self._last_state = snapshot.state
        self._last_physical = snapshot.physical
        self._last_print = now
        if self.controls and snapshot.raw and snapshot.stats:
            raw = snapshot.raw
            stats = snapshot.stats
            physical = snapshot.physical
            active = (
                ",".join(
                    name
                    for name, pressed in (
                        ("Fn", physical.fn),
                        ("Record", physical.record),
                        ("Photo", physical.photo),
                        ("RTH", physical.rth),
                    )
                    if pressed
                )
                or "-"
            )
            print(
                f"\r{snapshot.state.value:<12} {snapshot.port or '-':<6} "
                f"LX {raw.left_x:4d} LY {raw.left_y:4d} "
                f"RX {raw.right_x:4d} RY {raw.right_y:4d} CAM {raw.camera:4d}  "
                f"MODE {physical.mode.value:<6} BTN {active:<12} RAW {physical.raw_bits:04X} "
                f"{stats.controls_received:6d} packets  {stats.last_response_ms:5.1f} ms",
                end="",
                flush=True,
            )
        elif state_changed:
            print(f"[{snapshot.state.value}] {snapshot.message}")


def _run_service(config: BridgeConfig, output_kind: str, duration: float | None) -> int:
    try:
        output = create_output(output_kind)
    except (RuntimeError, ValueError) as exc:
        print(f"Output error: {exc}", file=sys.stderr)
        return 2
    reporter = _ConsoleReporter(controls=output_kind == "none")
    service = BridgeService(config, output, on_update=reporter)
    stop = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    previous_sigint = signal.signal(signal.SIGINT, request_stop)
    try:
        service.start()
        started = time.monotonic()
        while not stop.wait(0.1):
            if duration is not None and time.monotonic() - started >= duration:
                break
        print()
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        service.close()
    snapshot = service.snapshot
    if snapshot.stats:
        stats = snapshot.stats
        print(
            f"Validated {stats.controls_received} control packets; "
            f"average response {stats.average_response_ms:.2f} ms; "
            f"extended status {stats.buttons_received}/{stats.button_polls_sent}; "
            f"CRC/framing failures {stats.invalid_frames}."
        )
        return 0 if stats.controls_received else 1
    return 1


def _find_port(config: BridgeConfig) -> str:
    if config.port:
        return config.port
    candidates = list_candidates(include_unknown=config.probe_unknown_ports)
    for item in candidates:
        if item.score >= 100 or probe_port(
            item.device,
            baud_rate=config.baud_rate,
            timeout=config.response_timeout_seconds,
        ):
            return item.device
    raise RuntimeError("no compatible DJI protocol port found")


def _calibrate(args: argparse.Namespace, config: BridgeConfig) -> int:
    try:
        port = _find_port(config)
        print(f"Using {port}.")
        input("Release both sticks and the camera wheel, then press Enter...")
        with Rcn1Transport(
            port,
            baud_rate=config.baud_rate,
            response_timeout=config.response_timeout_seconds,
        ) as transport:
            transport.enable_simulator_mode()

            last_phase = ""

            def progress(phase: str, fraction: float) -> None:
                nonlocal last_phase
                if phase != last_phase:
                    print(
                        "Hold everything centered..."
                        if phase == "center"
                        else "Move both sticks and wheel repeatedly to every full endpoint..."
                    )
                    last_phase = phase
                print(f"\r{phase.capitalize():<7} {fraction:6.1%}", end="", flush=True)

            values = capture_calibration(
                transport,
                center_seconds=args.center_seconds,
                range_seconds=args.range_seconds,
                on_phase=progress,
            )
        print()
        apply_calibration(config, values)
        path = save_config(config, args.config)
        for name, triplet in values.items():
            print(f"{name:<8}: min {triplet[0]:4d}, center {triplet[1]:4d}, max {triplet[2]:4d}")
        print(f"Saved calibration to {path}")
        return 0
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Calibration failed: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    command = args.command or "gui"
    try:
        if command == "scan":
            return _scan(args)
        if command == "init-config":
            path = save_config(BridgeConfig(), args.config)
            print(f"Created {path}")
            return 0
        config = _load(args)
        if command == "run":
            duration = max(0.1, args.seconds) if args.seconds is not None else None
            return _run_service(config, args.output, duration)
        if command == "diagnose":
            return _run_service(config, "none", max(0.1, args.seconds))
        if command == "calibrate":
            return _calibrate(args, config)
        if command == "gui":
            from .gui import run_gui

            return run_gui(config, args.config)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    parser.error(f"unknown command {command}")
    return 2
