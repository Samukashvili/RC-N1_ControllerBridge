from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PortCandidate:
    device: str
    description: str
    hardware_id: str
    vid: int | None
    pid: int | None
    score: int
    reason: str


def _port_score(port: Any) -> tuple[int, list[str]]:
    description = (getattr(port, "description", "") or "").casefold()
    hardware_id = (getattr(port, "hwid", "") or "").casefold()
    vid = getattr(port, "vid", None)
    score = 0
    reasons: list[str] = []
    if "for debug" in description or "debug" in description and "vcom" in description:
        return -1000, ["debug interface excluded"]
    if "for protocol" in description:
        score += 100
        reasons.append("protocol interface name")
    if "dji" in description or "device usb vcom" in description:
        score += 25
        reasons.append("DJI/VCOM description")
    if vid == 0x2CA3 or "vid:pid=2ca3:" in hardware_id:
        score += 20
        reasons.append("DJI USB vendor ID")
    if "usb" in description or "usb" in hardware_id:
        score += 5
        reasons.append("USB serial device")
    return score, reasons


def rank_ports(ports: Iterable[Any], *, include_unknown: bool = False) -> list[PortCandidate]:
    candidates: list[PortCandidate] = []
    for port in ports:
        score, reasons = _port_score(port)
        if score < 0 or (score == 0 and not include_unknown):
            continue
        device = getattr(port, "device", None) or getattr(port, "name", None)
        if not device:
            continue
        candidates.append(
            PortCandidate(
                device=device,
                description=getattr(port, "description", "") or "Unknown serial device",
                hardware_id=getattr(port, "hwid", "") or "",
                vid=getattr(port, "vid", None),
                pid=getattr(port, "pid", None),
                score=score,
                reason=", ".join(reasons) if reasons else "explicit unknown-port probing enabled",
            )
        )
    return sorted(candidates, key=lambda item: (-item.score, item.device.casefold()))


def list_candidates(*, include_unknown: bool = False) -> list[PortCandidate]:
    try:
        from serial.tools import list_ports
    except ImportError as exc:
        raise RuntimeError("pyserial is not installed; run the setup script first") from exc
    return rank_ports(list_ports.comports(include_links=True), include_unknown=include_unknown)
