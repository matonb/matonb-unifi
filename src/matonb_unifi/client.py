"""HTTP client for the UniFi Network API."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

from matonb_unifi.exceptions import (
    UnifiAPIError,
    UnifiAuthError,
    UnifiConnectionError,
    UnifiError,
)
from matonb_unifi.models import Port, PortOverride, UnifiDevice, UnifiSta

if TYPE_CHECKING:
    import sys
    from collections.abc import Iterable

    if sys.version_info >= (3, 11):
        from typing import Self
    else:
        from typing_extensions import Self

logger = logging.getLogger(__name__)

_MODERN_LOGIN = "/api/auth/login"
_LEGACY_LOGIN = "/api/login"
_MODERN_LOGOUT = "/api/auth/logout"
_LEGACY_LOGOUT = "/api/logout"


class UnifiClient:
    """
    HTTP client for the UniFi Network API.

    Supports API-key auth (modern UDM/UniFi OS) and username/password
    auth (legacy standalone controllers).

    TLS certificates are verified by default. Controllers with self-signed
    certificates need ``verify_ssl=False`` (an informed opt-out).
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        site: str = "default",
        verify_ssl: bool = True,
        legacy: bool = False,
        timeout: float = 30.0,
    ) -> None:
        if not api_key and not (username and password):
            msg = "Provide either api_key or both username and password"
            raise ValueError(msg)

        self._site = site
        self._legacy = legacy
        self._username = username
        self._password = password
        self._logged_in = False

        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-KEY"] = api_key

        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            verify=verify_ssl,
            timeout=timeout,
        )

    def __enter__(self) -> Self:
        if self._username:
            self.login()
        return self

    def __exit__(self, *_: object) -> None:
        if self._logged_in:
            self.logout()
        self.close()

    def close(self) -> None:
        self._http.close()

    def login(self) -> None:
        url = _LEGACY_LOGIN if self._legacy else _MODERN_LOGIN
        try:
            resp = self._http.post(
                url, json={"username": self._username, "password": self._password}
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            msg = f"Login failed (HTTP {exc.response.status_code})"
            raise UnifiAuthError(msg) from exc
        except httpx.RequestError as exc:
            msg = f"Could not reach the UniFi controller: {exc}"
            raise UnifiConnectionError(msg) from exc
        token = resp.cookies.get("TOKEN")
        if token:
            self._http.headers["X-Auth-Token"] = token
        self._logged_in = True

    def logout(self) -> None:
        url = _LEGACY_LOGOUT if self._legacy else _MODERN_LOGOUT
        try:
            self._http.post(url)
        except httpx.HTTPError:
            logger.debug("Logout request failed", exc_info=True)
        self._logged_in = False

    def get_clients(self) -> list[UnifiSta]:
        """Return all connected client stations."""
        return [
            UnifiSta(
                mac=item.get("mac", ""),
                ip=item.get("last_ip") or item.get("fixed_ip") or None,
                hostname=item.get("hostname", ""),
                name=item.get("name", ""),
            )
            for item in self._get("stat/sta")
        ]

    def get_devices(self) -> list[UnifiDevice]:
        """Return all UniFi network devices."""
        devices = []
        for item in self._get("stat/device"):
            overrides = [
                PortOverride(port_idx=o["port_idx"], poe_mode=o.get("poe_mode", "auto"))
                for o in item.get("port_overrides", [])
                if "port_idx" in o
            ]
            ports = [
                Port(
                    port_idx=p["port_idx"],
                    name=p.get("name", ""),
                    poe_mode=p.get("poe_mode", ""),
                    poe_enable=bool(p.get("poe_enable", False)),
                )
                for p in item.get("port_table", [])
                if "port_idx" in p
            ]
            devices.append(
                UnifiDevice(
                    id=item.get("_id", ""),
                    mac=item.get("mac", ""),
                    name=item.get("name")
                    or item.get("hostname")
                    or item.get("mac", "unknown"),
                    device_type=item.get("type", ""),
                    model=item.get("model") or "Generic",
                    ip=item.get("ip") or None,
                    port_overrides=overrides,
                    ports=ports,
                )
            )
        return devices

    def find_device(self, identifier: str) -> UnifiDevice | None:
        """Find a device by name or MAC address (case-insensitive).

        The MAC may be given with ``:`` or ``-`` separators. Returns ``None``
        if no device matches.
        """
        name = identifier.strip().lower()
        mac = name.replace("-", ":")
        for device in self.get_devices():
            if device.mac.lower() == mac or device.name.lower() == name:
                return device
        return None

    def set_port_poe(
        self,
        device: UnifiDevice | str,
        port_modes: dict[int, str],
        current_overrides: list[dict[str, Any]] | list[PortOverride] | None = None,
    ) -> None:
        """Set PoE mode for one or more ports in a single API call.

        ``device`` may be a :class:`UnifiDevice` or a bare device id. Existing
        overrides are merged so untouched ports are left as-is; pass
        ``current_overrides`` (dicts or :class:`PortOverride`) to supply them
        explicitly, otherwise they are taken from ``device`` (or re-fetched
        when only an id is given).
        """
        device_id = device.id if isinstance(device, UnifiDevice) else device
        source = self._resolve_overrides(device, current_overrides)
        overrides = [
            {"port_idx": o.port_idx, "poe_mode": o.poe_mode}
            if isinstance(o, PortOverride)
            else dict(o)
            for o in source
        ]
        for port_idx, poe_mode in port_modes.items():
            for override in overrides:
                if override.get("port_idx") == port_idx:
                    override["poe_mode"] = poe_mode
                    break
            else:
                overrides.append({"port_idx": port_idx, "poe_mode": poe_mode})

        self._send(
            "PUT",
            f"rest/device/{device_id}",
            json={"port_overrides": overrides},
        )

    def cycle_port_poe(
        self,
        device: UnifiDevice | str,
        port_idxs: Iterable[int],
        *,
        delay: float = 5.0,
        restore_mode: str = "auto",
    ) -> None:
        """Power-cycle PoE on one or more ports: turn off, wait, restore.

        ``delay`` seconds elapse between the off and the restore. The restore
        re-fetches the device so it merges against the post-off overrides.
        """
        ports = list(port_idxs)
        device_id = device.id if isinstance(device, UnifiDevice) else device
        self.set_port_poe(device, dict.fromkeys(ports, "off"))
        time.sleep(delay)
        self.set_port_poe(device_id, dict.fromkeys(ports, restore_mode))

    # ------------------------------------------------------------------

    def _resolve_overrides(
        self,
        device: UnifiDevice | str,
        current_overrides: list[dict[str, Any]] | list[PortOverride] | None,
    ) -> list[dict[str, Any]] | list[PortOverride]:
        if current_overrides is not None:
            return current_overrides
        if isinstance(device, UnifiDevice):
            return device.port_overrides
        for candidate in self.get_devices():
            if candidate.id == device:
                return candidate.port_overrides
        msg = f"Device not found: {device}"
        raise UnifiError(msg)

    def _api_path(self, path: str) -> str:
        if self._legacy:
            return f"/api/s/{self._site}/{path}"
        return f"/proxy/network/api/s/{self._site}/{path}"

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Send an authenticated API request, translating transport errors."""
        try:
            resp = self._http.request(method, self._api_path(path), **kwargs)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                msg = f"Not authorised (HTTP {status})"
                raise UnifiAuthError(msg) from exc
            msg = f"UniFi API returned HTTP {status}"
            raise UnifiAPIError(msg, status_code=status) from exc
        except httpx.RequestError as exc:
            msg = f"Could not reach the UniFi controller: {exc}"
            raise UnifiConnectionError(msg) from exc
        return resp

    def _get(self, path: str) -> list[dict[str, Any]]:
        resp = self._send("GET", path)
        return resp.json().get("data", [])  # type: ignore[no-any-return]
