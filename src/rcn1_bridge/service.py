from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum

from .config import BridgeConfig
from .mapping import ControlMapper
from .model import NEUTRAL_PHYSICAL, MappedControls, PhysicalControls, RawControls
from .output import GamepadOutput
from .ports import PortCandidate, list_candidates
from .transport import Rcn1Transport, TransportError, TransportStats, probe_port

LOG = logging.getLogger(__name__)


class ServiceState(str, Enum):
    STOPPED = "stopped"
    SEARCHING = "searching"
    CONNECTING = "connecting"
    RUNNING = "running"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ServiceSnapshot:
    state: ServiceState = ServiceState.STOPPED
    message: str = "Stopped"
    port: str | None = None
    raw: RawControls | None = None
    mapped: MappedControls | None = None
    physical: PhysicalControls = NEUTRAL_PHYSICAL
    stats: TransportStats | None = None
    output_reports: int = 0
    connected_at: float | None = None


class BridgeService:
    def __init__(
        self,
        config: BridgeConfig,
        output: GamepadOutput,
        *,
        on_update: Callable[[ServiceSnapshot], None] | None = None,
    ) -> None:
        self.config = config
        self.output = output
        self.mapper = ControlMapper(config)
        self.on_update = on_update
        self._snapshot = ServiceSnapshot()
        self._snapshot_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._output_reports = 0
        self._last_report: MappedControls | None = None

    @property
    def snapshot(self) -> ServiceSnapshot:
        with self._snapshot_lock:
            return self._snapshot

    def _publish(self, **changes: object) -> None:
        with self._snapshot_lock:
            self._snapshot = replace(self._snapshot, **changes)
            snapshot = self._snapshot
        if self.on_update:
            try:
                self.on_update(snapshot)
            except Exception:
                LOG.exception("status callback failed")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, name="rcn1-bridge", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout)
        self.output.neutralize()

    def close(self) -> None:
        self.stop()
        self.output.close()

    def _choose_port(self) -> PortCandidate | None:
        if self.config.port:
            return PortCandidate(
                self.config.port,
                "Explicitly configured port",
                "",
                None,
                None,
                1000,
                "explicit configuration",
            )
        candidates = list_candidates(include_unknown=self.config.probe_unknown_ports)
        for candidate in candidates:
            # A recognized protocol interface is already sufficiently specific.
            if candidate.score >= 100:
                return candidate
            # Changed names/firmware are accepted only after a valid CRC-backed response.
            if (candidate.score >= 20 or self.config.probe_unknown_ports) and probe_port(
                candidate.device,
                baud_rate=self.config.baud_rate,
                timeout=self.config.response_timeout_seconds,
            ):
                return candidate
        return None

    def run(self) -> None:
        self._output_reports = 0
        try:
            while not self._stop.is_set():
                self._publish(
                    state=ServiceState.SEARCHING, message="Looking for a DJI protocol port"
                )
                try:
                    candidate = self._choose_port()
                except Exception as exc:
                    self._publish(state=ServiceState.ERROR, message=str(exc), port=None)
                    if self._stop.wait(self.config.reconnect_seconds):
                        break
                    continue
                if candidate is None:
                    self.output.neutralize()
                    self._publish(
                        state=ServiceState.RECONNECTING,
                        message="No compatible DJI protocol port found",
                        port=None,
                    )
                    if self._stop.wait(self.config.reconnect_seconds):
                        break
                    continue
                self._run_connected(candidate)
                if not self._stop.is_set():
                    self.output.neutralize()
                    self.mapper.reset()
                    self._last_report = None
                    if self._stop.wait(self.config.reconnect_seconds):
                        break
        finally:
            self.output.neutralize()
            self._publish(state=ServiceState.STOPPED, message="Stopped", port=None)

    def _run_connected(self, candidate: PortCandidate) -> None:
        self._publish(
            state=ServiceState.CONNECTING,
            message=f"Opening {candidate.device} ({candidate.reason})",
            port=candidate.device,
        )
        transport = Rcn1Transport(
            candidate.device,
            baud_rate=self.config.baud_rate,
            response_timeout=self.config.response_timeout_seconds,
        )
        try:
            transport.open()
            transport.enable_simulator_mode()
            connected_at = time.time()
            consecutive_timeouts = 0
            button_timeouts = 0
            controls_since_buttons = self.config.button_poll_interval
            physical = NEUTRAL_PHYSICAL
            buttons_supported = True
            while not self._stop.is_set():
                raw = transport.poll()
                if raw is None:
                    consecutive_timeouts += 1
                    if consecutive_timeouts * self.config.response_timeout_seconds >= (
                        self.config.stale_neutral_seconds
                    ):
                        self.output.neutralize()
                    if consecutive_timeouts >= 5:
                        raise TransportError("controller stopped answering validated polls")
                    continue
                consecutive_timeouts = 0
                controls_since_buttons += 1
                if buttons_supported and controls_since_buttons >= self.config.button_poll_interval:
                    controls_since_buttons = 0
                    new_physical = transport.poll_buttons()
                    if new_physical is None:
                        button_timeouts += 1
                        if button_timeouts >= 3:
                            buttons_supported = False
                            physical = NEUTRAL_PHYSICAL
                    else:
                        button_timeouts = 0
                        physical = new_physical
                mapped = self.mapper.map(raw, physical)
                should_report = not (
                    self.config.suppress_duplicate_reports and mapped == self._last_report
                )
                if should_report:
                    self.output.update(mapped)
                    self._last_report = mapped
                    self._output_reports += 1
                self._publish(
                    state=ServiceState.RUNNING,
                    message=f"Connected to {candidate.description}",
                    port=candidate.device,
                    raw=raw,
                    mapped=mapped,
                    physical=physical,
                    stats=replace(transport.stats),
                    output_reports=self._output_reports,
                    connected_at=connected_at,
                )
        except TransportError as exc:
            self._publish(
                state=ServiceState.RECONNECTING,
                message=f"{exc}; reconnecting",
                port=candidate.device,
                stats=replace(transport.stats),
            )
        finally:
            transport.close()
