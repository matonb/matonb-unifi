"""Typed data models returned by :class:`matonb_unifi.UnifiClient`."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UnifiSta:
    """A wireless or wired client station connected to the network."""

    mac: str
    ip: str | None = None
    hostname: str = ""
    name: str = ""


@dataclass
class PortOverride:
    port_idx: int
    poe_mode: str = "auto"


@dataclass
class Port:
    """A physical port from a device's ``port_table`` (live status)."""

    port_idx: int
    name: str = ""
    poe_mode: str = ""
    poe_enable: bool = False


@dataclass
class UnifiDevice:
    """A UniFi infrastructure device: switch, AP, gateway, or UDM."""

    id: str
    mac: str
    name: str
    device_type: str
    model: str = "Generic"
    ip: str | None = None
    port_overrides: list[PortOverride] = field(default_factory=list)
    ports: list[Port] = field(default_factory=list)

    def current_poe_mode(self, port_idx: int) -> str:
        """Return the effective PoE mode for a port.

        An explicit override wins; otherwise the live ``port_table`` value is
        used. Returns ``"unknown"`` when the port is not present.
        """
        for override in self.port_overrides:
            if override.port_idx == port_idx:
                return override.poe_mode
        for port in self.ports:
            if port.port_idx == port_idx:
                return port.poe_mode or "unknown"
        return "unknown"
