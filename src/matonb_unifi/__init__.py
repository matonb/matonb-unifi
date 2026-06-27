"""Typed Python client for the UniFi Network API."""

from matonb_unifi.client import UnifiClient
from matonb_unifi.exceptions import (
    UnifiAPIError,
    UnifiAuthError,
    UnifiConnectionError,
    UnifiError,
)
from matonb_unifi.models import Port, PortOverride, UnifiDevice, UnifiSta

__version__ = "0.0.0"

__all__ = [
    "Port",
    "PortOverride",
    "UnifiAPIError",
    "UnifiAuthError",
    "UnifiClient",
    "UnifiConnectionError",
    "UnifiDevice",
    "UnifiError",
    "UnifiSta",
]
